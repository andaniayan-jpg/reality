"""Headless MuJoCo CPU backend isolated from the public Reality API."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from math import ceil, cos, sin, sqrt
from time import perf_counter
from typing import TypeAlias

import mujoco
import numpy as np

from .._models import Transform, Vector3, WorldObject
from .._physics import BodySimulationResult, Contact, SimulationResult
from .base import PhysicsCapabilities

_ModelKey: TypeAlias = tuple[object, ...]
_MAX_CACHED_MODELS = 8


class MuJoCoBackend:
    """Deterministic fixed-step rigid-body simulation using oriented box bodies.

    Compiled models are retained for a small number of unchanged scene topologies.
    Dynamic body transforms are written into a fresh ``MjData`` instance each call,
    so cached models cannot leak simulation state between branches or runs.
    """

    name = "mujoco-cpu"
    version = mujoco.__version__
    capabilities = PhysicsCapabilities(True, True, True, True, True)

    def __init__(self) -> None:
        self._models: OrderedDict[_ModelKey, mujoco.MjModel] = OrderedDict()

    def simulate(
        self,
        objects: Sequence[WorldObject],
        *,
        seconds: float,
        time_step: float,
        gravity: Vector3,
        forces: Mapping[str, tuple[Vector3, float]],
    ) -> SimulationResult:
        if seconds < 0.0:
            raise ValueError("seconds must be non-negative")
        if time_step <= 0.0:
            raise ValueError("time_step must be positive")
        _validate_forces(objects, forces)
        steps = int(ceil(seconds / time_step)) if seconds else 0
        actual_step = seconds / steps if steps else time_step
        key = _model_key(objects, actual_step, gravity)
        started = perf_counter()
        model = self._models.get(key)
        model_reused = model is not None
        if model is None:
            model = mujoco.MjModel.from_xml_string(_model_xml(objects, actual_step, gravity))
            self._models[key] = model
            if len(self._models) > _MAX_CACHED_MODELS:
                self._models.popitem(last=False)
        else:
            self._models.move_to_end(key)
        model_seconds = perf_counter() - started

        data = mujoco.MjData(model)
        dynamic = tuple(object_ for object_ in objects if object_.dynamic)
        body_ids = {
            object_.id: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"body_{index}")
            for index, object_ in enumerate(objects)
            if object_.dynamic
        }
        _set_initial_dynamic_state(model, data, dynamic, body_ids)
        geom_to_object: dict[int, str | None] = {0: None}
        for index, object_ in enumerate(objects):
            geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"geom_{index}")
            geom_to_object[geom_id] = object_.id

        stepped_at = perf_counter()
        observed_contacts: dict[tuple[str, str | None], Contact] = {}
        for step in range(steps):
            elapsed = step * actual_step
            data.xfrc_applied.fill(0.0)
            for object_id, (force, duration) in forces.items():
                if elapsed < duration and object_id in body_ids:
                    data.xfrc_applied[body_ids[object_id], :3] = force
            mujoco.mj_step(model, data)
            for contact in _contacts(data, geom_to_object):
                observed_contacts[_contact_key(contact)] = contact
        stepping_seconds = perf_counter() - stepped_at

        contacts = tuple(
            observed_contacts[key] for key in sorted(observed_contacts, key=_contact_sort_key)
        )
        collected_at = perf_counter()
        results: list[BodySimulationResult] = []
        for object_ in dynamic:
            body_id = body_ids[object_.id]
            position = tuple(float(value) for value in data.xpos[body_id])
            rotation = _euler_from_quaternion(data.xquat[body_id])
            final = Transform(
                position=position,  # type: ignore[arg-type]
                rotation=rotation,
                scale=object_.scale,
            )
            velocity = tuple(float(value) for value in data.cvel[body_id][3:6])
            displacement = sqrt(
                sum((final.position[index] - object_.position[index]) ** 2 for index in range(3))
            )
            body_contacts = tuple(
                contact
                for contact in contacts
                if object_.id in {contact.object_a_id, contact.object_b_id}
            )
            results.append(
                BodySimulationResult(
                    object_id=object_.id,
                    object_name=object_.name,
                    initial_transform=object_.transform,
                    final_transform=final,
                    initial_velocity=(0.0, 0.0, 0.0),
                    final_velocity=velocity,  # type: ignore[arg-type]
                    contacts=body_contacts,
                    fell=final.position[2] < object_.position[2] - 1e-4,
                    motion=displacement,
                )
            )
        collection_seconds = perf_counter() - collected_at
        return SimulationResult(
            backend=self.name,
            backend_version=self.version,
            seconds=seconds,
            time_step=actual_step,
            steps=steps,
            bodies=tuple(results),
            deterministic=True,
            evidence={
                "collision_approximation": "oriented boxes from local bounds",
                "ground_plane": "z=0",
                "integrator": "MuJoCo fixed-step Euler",
                "model_reused": model_reused,
                "model_setup_seconds": model_seconds,
                "stepping_seconds": stepping_seconds,
                "contact_collection_seconds": collection_seconds,
                "contacts_observed_over_run": len(contacts),
                "restitution_note": (
                    "MuJoCo contact compliance is not a direct restitution mapping."
                ),
            },
        )


def _model_key(objects: Sequence[WorldObject], step: float, gravity: Vector3) -> _ModelKey:
    """Describe compiled topology while excluding dynamic pose/state."""
    bodies: list[object] = []
    for object_ in objects:
        bodies.append(
            (
                object_.id,
                object_.local_bounds,
                object_.scale,
                object_.physical,
                object_.transform if not object_.dynamic else None,
            )
        )
    return (tuple(bodies), float(step), tuple(float(value) for value in gravity))


def _model_xml(objects: Sequence[WorldObject], step: float, gravity: Vector3) -> str:
    lines = [
        '<mujoco model="reality">',
        (
            f'<option timestep="{step:.17g}" gravity="{gravity[0]:.17g} '
            f'{gravity[1]:.17g} {gravity[2]:.17g}" integrator="Euler"/>'
        ),
        "<worldbody>",
        '<geom name="ground" type="plane" size="1000 1000 0.1" pos="0 0 0"/>',
    ]
    for index, object_ in enumerate(objects):
        local_center, half = _collider_geometry(object_)
        quaternion = _quaternion(object_.rotation)
        friction = f"{object_.friction:.17g} 0.005 0.0001"
        position = " ".join(f"{value:.17g}" for value in object_.position)
        rotation = " ".join(f"{value:.17g}" for value in quaternion)
        center = " ".join(f"{value:.17g}" for value in local_center)
        size = " ".join(f"{value:.17g}" for value in half)
        lines.append(f'<body name="body_{index}" pos="{position}" quat="{rotation}">')
        if object_.dynamic:
            inertia = _inertia(object_.mass, half)
            com = tuple(
                local_center[axis] + object_.center_of_mass[axis] * object_.scale[axis]
                for axis in range(3)
            )
            com_text = " ".join(f"{value:.17g}" for value in com)
            inertia_text = " ".join(f"{value:.17g}" for value in inertia)
            lines.extend(
                [
                    "<freejoint/>",
                    (
                        f'<inertial pos="{com_text}" mass="{object_.mass:.17g}" '
                        f'diaginertia="{inertia_text}"/>'
                    ),
                ]
            )
        lines.append(
            f'<geom name="geom_{index}" type="box" pos="{center}" size="{size}" '
            f'friction="{friction}"/>'
        )
        lines.append("</body>")
    lines.extend(["</worldbody>", "</mujoco>"])
    return "".join(lines)


def _collider_geometry(object_: WorldObject) -> tuple[Vector3, Vector3]:
    center = tuple(object_.local_bounds.center[axis] * object_.scale[axis] for axis in range(3))
    half = tuple(
        max(abs(object_.local_bounds.extents[axis] * object_.scale[axis]) / 2.0, 1e-6)
        for axis in range(3)
    )
    return center, half  # type: ignore[return-value]


def _inertia(mass: float, half: Vector3) -> Vector3:
    dimensions = tuple(2.0 * value for value in half)
    return tuple(
        max(
            mass * (dimensions[(axis + 1) % 3] ** 2 + dimensions[(axis + 2) % 3] ** 2) / 12.0,
            1e-9,
        )
        for axis in range(3)
    )  # type: ignore[return-value]


def _set_initial_dynamic_state(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    objects: Sequence[WorldObject],
    body_ids: Mapping[str, int],
) -> None:
    for object_ in objects:
        body_id = body_ids[object_.id]
        joint_id = int(model.body_jntadr[body_id])
        address = int(model.jnt_qposadr[joint_id])
        data.qpos[address : address + 3] = object_.position
        data.qpos[address + 3 : address + 7] = _quaternion(object_.rotation)
        velocity_address = int(model.jnt_dofadr[joint_id])
        data.qvel[velocity_address : velocity_address + 6] = 0.0
    mujoco.mj_forward(model, data)


def _quaternion(rotation: Vector3) -> tuple[float, float, float, float]:
    """Return MuJoCo's scalar-first quaternion for Reality's XYZ Euler rotation."""
    x, y, z = (angle / 2.0 for angle in rotation)
    cx, sx = cos(x), sin(x)
    cy, sy = cos(y), sin(y)
    cz, sz = cos(z), sin(z)
    return (
        cz * cy * cx + sz * sy * sx,
        cz * cy * sx - sz * sy * cx,
        cz * sy * cx + sz * cy * sx,
        sz * cy * cx - cz * sy * sx,
    )


def _euler_from_quaternion(quaternion: Sequence[float]) -> Vector3:
    w, x, y, z = (float(value) for value in quaternion)
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = rotation
    return Transform.from_matrix(matrix).rotation


def _validate_forces(
    objects: Sequence[WorldObject], forces: Mapping[str, tuple[Vector3, float]]
) -> None:
    dynamic_ids = {object_.id for object_ in objects if object_.dynamic}
    unknown = set(forces) - dynamic_ids
    if unknown:
        raise ValueError(f"forces reference non-dynamic or unknown object ids: {sorted(unknown)!r}")
    for object_id, (force, duration) in forces.items():
        if len(force) != 3 or not all(np.isfinite(value) for value in force):
            raise ValueError(f"force for {object_id!r} must contain three finite values")
        if not np.isfinite(duration) or duration < 0.0:
            raise ValueError(f"force duration for {object_id!r} must be finite and non-negative")


def _contacts(data: mujoco.MjData, geom_to_object: Mapping[int, str | None]) -> tuple[Contact, ...]:
    contacts: list[Contact] = []
    for index in range(data.ncon):
        item = data.contact[index]
        first = geom_to_object.get(int(item.geom1))
        second = geom_to_object.get(int(item.geom2))
        if first is None and second is None:
            continue
        if first is None:
            first, second = second, first
        assert first is not None
        contacts.append(
            Contact(
                object_a_id=first,
                object_b_id=second,
                point=tuple(float(value) for value in item.pos),  # type: ignore[arg-type]
                normal=tuple(float(value) for value in item.frame[:3]),  # type: ignore[arg-type]
                separation=float(item.dist),
            )
        )
    return tuple(contacts)


def _contact_key(contact: Contact) -> tuple[str, str | None]:
    if contact.object_b_id is None:
        return contact.object_a_id, None
    return tuple(sorted((contact.object_a_id, contact.object_b_id)))  # type: ignore[return-value]


def _contact_sort_key(key: tuple[str, str | None]) -> tuple[str, str]:
    return key[0], key[1] or ""
