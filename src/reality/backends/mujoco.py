"""Headless MuJoCo CPU backend isolated from the public Reality API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import ceil, sqrt

import mujoco  # type: ignore[import-untyped]

from .._models import Transform, Vector3, WorldObject
from .._physics import BodySimulationResult, Contact, SimulationResult
from .base import PhysicsCapabilities


class MuJoCoBackend:
    """Deterministic fixed-step rigid-body simulation using MuJoCo boxes."""

    name = "mujoco-cpu"
    version = mujoco.__version__
    capabilities = PhysicsCapabilities(True, True, True, True, True)

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
        steps = int(ceil(seconds / time_step)) if seconds else 0
        actual_step = seconds / steps if steps else time_step
        model = mujoco.MjModel.from_xml_string(_model_xml(objects, actual_step, gravity))
        data = mujoco.MjData(model)
        dynamic = [object_ for object_ in objects if object_.dynamic]
        body_ids = {
            object_.id: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"body_{index}")
            for index, object_ in enumerate(objects)
            if object_.dynamic
        }
        geom_to_object: dict[int, str | None] = {0: None}
        for index, object_ in enumerate(objects):
            geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"geom_{index}")
            geom_to_object[geom_id] = object_.id
        for step in range(steps):
            elapsed = step * actual_step
            data.xfrc_applied.fill(0.0)
            for object_id, (force, duration) in forces.items():
                if elapsed < duration and object_id in body_ids:
                    data.xfrc_applied[body_ids[object_id], :3] = force
            mujoco.mj_step(model, data)
        contacts = _contacts(data, geom_to_object)
        results: list[BodySimulationResult] = []
        for object_ in dynamic:
            body_id = body_ids[object_.id]
            center = tuple(float(value) for value in data.xpos[body_id])
            offset = tuple(
                object_.position[index] - object_.bounds.center[index] for index in range(3)
            )
            position = tuple(center[index] + offset[index] for index in range(3))
            final = Transform(
                position=position,  # type: ignore[arg-type]
                rotation=object_.rotation,
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
        return SimulationResult(
            backend=self.name,
            backend_version=self.version,
            seconds=seconds,
            time_step=actual_step,
            steps=steps,
            bodies=tuple(results),
            deterministic=True,
            evidence={
                "collision_approximation": "world-axis-aligned boxes",
                "ground_plane": "z=0",
                "integrator": "MuJoCo fixed-step Euler",
            },
        )


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
        center = object_.bounds.center
        half = tuple(max(value / 2.0, 1e-6) for value in object_.bounds.extents)
        friction = f"{object_.friction:.17g} 0.005 0.0001"
        if object_.dynamic:
            lines.extend(
                [
                    (
                        f'<body name="body_{index}" pos="{center[0]:.17g} '
                        f'{center[1]:.17g} {center[2]:.17g}">'
                    ),
                    "<freejoint/>",
                    (
                        f'<geom name="geom_{index}" type="box" size="{half[0]:.17g} '
                        f'{half[1]:.17g} {half[2]:.17g}" mass="{object_.mass:.17g}" '
                        f'friction="{friction}"/>'
                    ),
                    "</body>",
                ]
            )
        else:
            lines.append(
                f'<geom name="geom_{index}" type="box" pos="{center[0]:.17g} '
                f'{center[1]:.17g} {center[2]:.17g}" size="{half[0]:.17g} '
                f'{half[1]:.17g} {half[2]:.17g}" friction="{friction}"/>'
            )
    lines.extend(["</worldbody>", "</mujoco>"])
    return "".join(lines)


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
