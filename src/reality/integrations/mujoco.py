"""Truthful MJCF interchange through the optional MuJoCo runtime.

This adapter is deliberately a scene-geometry bridge, not an MJCF emulator.
MuJoCo compiles the source XML and supplies world-space geom poses. Reality
imports only supported primitive geoms as their exact local bounding boxes;
mesh, plane, height-field, joint, actuator, sensor, and contact semantics are
reported as unsupported rather than guessed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import ceil, cos, isfinite, sin
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import escape

import numpy as np
from numpy.typing import NDArray

from .._models import Bounds, Transform, Vector3, WorldObject
from .._world import World
from .base import (
    IntegrationCapability,
    IntegrationDescriptor,
    IntegrationStatus,
    IntegrationSyncResult,
    IntegrationUnavailableError,
)

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class MuJoCoJointInfo:
    """A joint declared by an MJCF source, in the coordinate frame MuJoCo uses."""

    id: str
    name: str
    kind: str
    body_name: str
    axis: Vector3 | None
    limits: tuple[float, float] | None
    units: str | None
    axis_frame: str | None


@dataclass(frozen=True, slots=True)
class MuJoCoActuatorInfo:
    """A declared actuator and only the control facts exposed by the compiled model."""

    id: str
    name: str
    transmission: str
    target_name: str | None
    control_limits: tuple[float, float] | None


@dataclass(frozen=True, slots=True)
class MuJoCoSensorInfo:
    """A declared sensor; raw MuJoCo type is retained without semantic guessing."""

    id: str
    name: str
    type_code: int
    object_type_code: int
    object_id: int


@dataclass(frozen=True, slots=True)
class MuJoCoSceneInfo:
    """Inspectable source facts from a real compiled MJCF model."""

    source: Path
    units: str
    mujoco_version: str
    body_count: int
    geom_count: int
    joints: tuple[MuJoCoJointInfo, ...]
    actuators: tuple[MuJoCoActuatorInfo, ...]
    sensors: tuple[MuJoCoSensorInfo, ...]


@dataclass(frozen=True, slots=True)
class MuJoCoBodyState:
    """A world-space body pose observed after a local MuJoCo rollout."""

    id: str
    name: str
    transform: Transform


@dataclass(frozen=True, slots=True)
class MuJoCoRolloutResult:
    """Evidence from an isolated local simulation; never a hardware command."""

    seconds: float
    time_step: float
    steps: int
    controls: Mapping[str, float]
    bodies: tuple[MuJoCoBodyState, ...]
    sensor_readings: Mapping[str, tuple[float, ...]]
    final_contact_count: int
    mujoco_version: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "controls", MappingProxyType(dict(self.controls)))
        object.__setattr__(self, "sensor_readings", MappingProxyType(dict(self.sensor_readings)))
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


class MuJoCoSceneIntegration:
    """Import/export supported primitive geometry using real MuJoCo MJCF parsing."""

    _descriptor = IntegrationDescriptor(
        name="mujoco-mjcf",
        version="1",
        runtime="MuJoCo MJCF",
        capabilities=frozenset(
            {
                IntegrationCapability.IMPORT_SCENE,
                IntegrationCapability.EXPORT_SCENE,
                IntegrationCapability.READ_TRANSFORMS,
                IntegrationCapability.WRITE_TRANSFORMS,
            }
        ),
        documentation_url="https://mujoco.readthedocs.io/en/stable/XMLreference.html",
    )

    @property
    def descriptor(self) -> IntegrationDescriptor:
        return self._descriptor

    def status(self) -> IntegrationStatus:
        try:
            mujoco = _mujoco()
        except IntegrationUnavailableError as error:
            return IntegrationStatus(
                descriptor=self.descriptor,
                available=False,
                reason=str(error),
                runtime_version=None,
            )
        return IntegrationStatus(
            descriptor=self.descriptor,
            available=True,
            reason="optional MuJoCo runtime is importable",
            runtime_version=str(mujoco.__version__),
        )

    def inspect_scene(self, source: Path) -> MuJoCoSceneInfo:
        """Compile MJCF and expose declared joints, actuators, and sensors.

        This reads facts from MuJoCo's compiled model. It does not imply that
        every listed item can be represented by the current ``World`` API.
        """
        mujoco, model = _compile_mjcf(source)
        joints = tuple(_joint_info(mujoco, model, joint_id) for joint_id in range(model.njnt))
        actuators = tuple(
            _actuator_info(mujoco, model, actuator_id) for actuator_id in range(model.nu)
        )
        sensors = tuple(
            _sensor_info(mujoco, model, sensor_id) for sensor_id in range(model.nsensor)
        )
        return MuJoCoSceneInfo(
            source=source,
            units="m",
            mujoco_version=mujoco.__version__,
            body_count=int(model.nbody),
            geom_count=int(model.ngeom),
            joints=joints,
            actuators=actuators,
            sensors=sensors,
        )

    def rollout(
        self,
        source: Path,
        *,
        controls: Mapping[str, float] | None = None,
        seconds: float,
        time_step: float = 1.0 / 240.0,
    ) -> MuJoCoRolloutResult:
        """Run a bounded, isolated MJCF simulation with validated controls.

        ``controls`` maps declared MuJoCo actuator names to scalar values. The
        source MJCF on disk is never modified, and this method cannot send a
        command to physical hardware.
        """
        if not isfinite(seconds) or seconds < 0.0:
            raise ValueError("seconds must be finite and non-negative")
        if not isfinite(time_step) or time_step <= 0.0:
            raise ValueError("time_step must be finite and positive")
        mujoco, model = _compile_mjcf(source)
        model.opt.timestep = time_step
        control_values = _validated_controls(mujoco, model, controls or {})
        data = mujoco.MjData(model)
        for actuator_id, value in control_values.items():
            data.ctrl[actuator_id] = value
        steps = int(ceil(seconds / time_step)) if seconds else 0
        for _ in range(steps):
            mujoco.mj_step(model, data)
        if steps == 0:
            mujoco.mj_forward(model, data)
        bodies = tuple(
            _body_state(mujoco, model, data, body_id) for body_id in range(1, model.nbody)
        )
        sensor_readings = _sensor_readings(mujoco, model, data)
        control_names = {
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_id)
            or f"actuator-{actuator_id}": value
            for actuator_id, value in control_values.items()
        }
        return MuJoCoRolloutResult(
            seconds=seconds,
            time_step=time_step,
            steps=steps,
            controls=control_names,
            bodies=bodies,
            sensor_readings=sensor_readings,
            final_contact_count=int(data.ncon),
            mujoco_version=mujoco.__version__,
            evidence={
                "execution": "isolated local MuJoCo simulation",
                "hardware_commanded": False,
                "source_modified": False,
                "control_validation": "declared actuator names and MuJoCo ctrlrange",
            },
        )

    def import_world(self, source: Path) -> tuple[World, IntegrationSyncResult]:
        """Compile an MJCF source and import its supported primitive geoms."""
        mujoco, model = _compile_mjcf(source)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)

        objects: list[WorldObject] = []
        skipped: list[str] = []
        for geom_id in range(model.ngeom):
            local_bounds = _primitive_bounds(
                mujoco, int(model.geom_type[geom_id]), model.geom_size[geom_id]
            )
            geom_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
            name = geom_name or f"geom-{geom_id}"
            if local_bounds is None:
                skipped.append(f"{name}: unsupported MuJoCo geom type")
                continue
            matrix: NDArray[np.float64] = np.eye(4, dtype=np.float64)
            matrix[:3, :3] = np.asarray(data.geom_xmat[geom_id], dtype=np.float64).reshape(3, 3)
            matrix[:3, 3] = np.asarray(data.geom_xpos[geom_id], dtype=np.float64)
            try:
                transform = Transform.from_matrix(matrix)
            except ValueError as error:
                skipped.append(f"{name}: unsupported non-rigid geom transform ({error})")
                continue
            objects.append(
                WorldObject(
                    name=name,
                    id=f"mujoco-geom-{geom_id}",
                    local_bounds=local_bounds,
                    transform=transform,
                )
            )
        world = World(objects, units="m")
        ids = tuple(object_.id for object_ in world.objects)
        warnings = tuple(
            [
                "MJCF joints, actuators, sensors, contacts, material, and collision settings "
                "are not represented by this geometry interchange.",
            ]
            + skipped
        )
        return world, IntegrationSyncResult(
            integration=self.descriptor,
            direction="import",
            object_ids=ids,
            changed_object_ids=ids,
            reason="compiled MJCF with MuJoCo and imported supported primitive geom bounds",
            warnings=warnings,
            evidence={
                "mujoco_version": mujoco.__version__,
                "source_geom_count": int(model.ngeom),
                "imported_geom_count": len(objects),
                "skipped_geom_count": len(skipped),
                "units": "m",
            },
        )

    def export_world(self, world: World, destination: Path) -> IntegrationSyncResult:
        """Write a valid MJCF scene containing one oriented box per Reality object.

        A ``WorldObject`` may reference a mesh or CAD solid. The output is an
        intentionally declared bounding-box representation, so it must not be
        used as an exact collision or appearance export.
        """
        if world.units != "m":
            raise ValueError(
                "MuJoCo MJCF export requires a world expressed in metres; "
                "convert units explicitly before exporting"
            )
        mujoco = _mujoco()
        lines = [
            '<mujoco model="reality-export">',
            '<compiler angle="radian"/>',
            "<worldbody>",
        ]
        for index, object_ in enumerate(world.objects):
            center, half = _box_geometry(object_)
            position = " ".join(_number(value) for value in object_.position)
            quaternion = " ".join(_number(value) for value in _quaternion(object_.rotation))
            center_text = " ".join(_number(value) for value in center)
            size = " ".join(_number(value) for value in half)
            name = escape(f"{object_.name}-{index}", {'"': "&quot;"})
            lines.extend(
                [
                    f'<body name="reality_body_{index}" pos="{position}" quat="{quaternion}">',
                    (f'<geom name="{name}" type="box" pos="{center_text}" size="{size}"/>'),
                    "</body>",
                ]
            )
        lines.extend(["</worldbody>", "</mujoco>"])
        try:
            destination.write_text("".join(lines), encoding="utf-8")
            # Compile the precise file that was written before claiming success.
            model = mujoco.MjModel.from_xml_path(str(destination))
        except Exception as error:
            raise ValueError(
                f"could not write or compile MJCF scene {destination}: {error}"
            ) from error
        ids = tuple(object_.id for object_ in world.objects)
        return IntegrationSyncResult(
            integration=self.descriptor,
            direction="export",
            object_ids=ids,
            changed_object_ids=ids,
            reason="wrote and compiled MJCF with one oriented bounding-box geom per Reality object",
            warnings=(
                "This export replaces source mesh/CAD geometry and physical material semantics "
                "with object bounding boxes.",
            ),
            evidence={
                "mujoco_version": mujoco.__version__,
                "compiled_geom_count": int(model.ngeom),
                "representation": "oriented bounding boxes",
                "units": world.units,
            },
        )


def _mujoco() -> Any:
    try:
        import mujoco
    except ImportError as error:
        raise IntegrationUnavailableError(
            "MuJoCo MJCF integration requires reality[physics] or mujoco."
        ) from error
    return mujoco


def _compile_mjcf(source: Path) -> tuple[Any, Any]:
    mujoco = _mujoco()
    try:
        return mujoco, mujoco.MjModel.from_xml_path(str(source))
    except Exception as error:  # MuJoCo exposes several parser exception types.
        raise ValueError(f"MuJoCo could not compile MJCF scene {source}: {error}") from error


def _validated_controls(mujoco: Any, model: Any, controls: Mapping[str, float]) -> dict[int, float]:
    named_ids = {
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_id)
        or f"actuator-{actuator_id}": actuator_id
        for actuator_id in range(model.nu)
    }
    unknown = sorted(set(controls) - set(named_ids))
    if unknown:
        raise ValueError(f"controls reference unknown MJCF actuators: {unknown!r}")
    resolved: dict[int, float] = {}
    for name, raw_value in controls.items():
        value = float(raw_value)
        if not isfinite(value):
            raise ValueError(f"control {name!r} must be finite")
        actuator_id = named_ids[name]
        if bool(model.actuator_ctrllimited[actuator_id]):
            minimum, maximum = (float(value) for value in model.actuator_ctrlrange[actuator_id])
            if not minimum <= value <= maximum:
                raise ValueError(
                    f"control {name!r}={value:g} exceeds declared ctrlrange "
                    f"[{minimum:g}, {maximum:g}]"
                )
        resolved[actuator_id] = value
    return resolved


def _body_state(mujoco: Any, model: Any, data: Any, body_id: int) -> MuJoCoBodyState:
    matrix: NDArray[np.float64] = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = np.asarray(data.xmat[body_id], dtype=np.float64).reshape(3, 3)
    matrix[:3, 3] = np.asarray(data.xpos[body_id], dtype=np.float64)
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or f"body-{body_id}"
    return MuJoCoBodyState(
        id=f"mujoco-body-{body_id}",
        name=name,
        transform=Transform.from_matrix(matrix),
    )


def _sensor_readings(mujoco: Any, model: Any, data: Any) -> dict[str, tuple[float, ...]]:
    readings: dict[str, tuple[float, ...]] = {}
    for sensor_id in range(model.nsensor):
        name = (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_SENSOR, sensor_id) or f"sensor-{sensor_id}"
        )
        address = int(model.sensor_adr[sensor_id])
        dimension = int(model.sensor_dim[sensor_id])
        readings[name] = tuple(
            float(value) for value in data.sensordata[address : address + dimension]
        )
    return readings


def _joint_info(mujoco: Any, model: Any, joint_id: int) -> MuJoCoJointInfo:
    joint_type = int(model.jnt_type[joint_id])
    enum = mujoco.mjtJoint
    if joint_type == int(enum.mjJNT_HINGE):
        kind, units, axis_frame = "hinge", "rad", "joint-local"
        axis: Vector3 | None = tuple(float(value) for value in model.jnt_axis[joint_id])  # type: ignore[assignment]
    elif joint_type == int(enum.mjJNT_SLIDE):
        kind, units, axis_frame = "slide", "m", "joint-local"
        axis = tuple(float(value) for value in model.jnt_axis[joint_id])  # type: ignore[assignment]
    elif joint_type == int(enum.mjJNT_BALL):
        kind, units, axis_frame, axis = "ball", "rad", None, None
    elif joint_type == int(enum.mjJNT_FREE):
        kind, units, axis_frame, axis = "free", None, None, None
    else:
        kind, units, axis_frame, axis = f"unknown:{joint_type}", None, None, None
    limits = (
        (float(model.jnt_range[joint_id][0]), float(model.jnt_range[joint_id][1]))
        if bool(model.jnt_limited[joint_id])
        else None
    )
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id) or f"joint-{joint_id}"
    body_id = int(model.jnt_bodyid[joint_id])
    body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or f"body-{body_id}"
    return MuJoCoJointInfo(
        id=f"mujoco-joint-{joint_id}",
        name=name,
        kind=kind,
        body_name=body_name,
        axis=axis,
        limits=limits,
        units=units,
        axis_frame=axis_frame,
    )


def _actuator_info(mujoco: Any, model: Any, actuator_id: int) -> MuJoCoActuatorInfo:
    transmission_type = int(model.actuator_trntype[actuator_id])
    transmission = _transmission_name(mujoco, transmission_type)
    target_id = int(model.actuator_trnid[actuator_id][0])
    target_name: str | None = None
    if transmission_type in {
        int(mujoco.mjtTrn.mjTRN_JOINT),
        int(mujoco.mjtTrn.mjTRN_JOINTINPARENT),
    }:
        target_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, target_id)
    name = (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_id)
        or f"actuator-{actuator_id}"
    )
    limits = (
        (
            float(model.actuator_ctrlrange[actuator_id][0]),
            float(model.actuator_ctrlrange[actuator_id][1]),
        )
        if bool(model.actuator_ctrllimited[actuator_id])
        else None
    )
    return MuJoCoActuatorInfo(
        id=f"mujoco-actuator-{actuator_id}",
        name=name,
        transmission=transmission,
        target_name=target_name,
        control_limits=limits,
    )


def _sensor_info(mujoco: Any, model: Any, sensor_id: int) -> MuJoCoSensorInfo:
    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_SENSOR, sensor_id) or f"sensor-{sensor_id}"
    return MuJoCoSensorInfo(
        id=f"mujoco-sensor-{sensor_id}",
        name=name,
        type_code=int(model.sensor_type[sensor_id]),
        object_type_code=int(model.sensor_objtype[sensor_id]),
        object_id=int(model.sensor_objid[sensor_id]),
    )


def _transmission_name(mujoco: Any, transmission_type: int) -> str:
    enum = mujoco.mjtTrn
    known = {
        int(enum.mjTRN_BODY): "body",
        int(enum.mjTRN_JOINT): "joint",
        int(enum.mjTRN_JOINTINPARENT): "joint-in-parent",
        int(enum.mjTRN_SITE): "site",
        int(enum.mjTRN_SLIDERCRANK): "slider-crank",
        int(enum.mjTRN_SO3): "so3",
        int(enum.mjTRN_TENDON): "tendon",
        int(enum.mjTRN_UNDEFINED): "undefined",
    }
    return known.get(transmission_type, f"unknown:{transmission_type}")


def _primitive_bounds(
    mujoco: Any, geom_type: int, size: NDArray[np.floating[Any]]
) -> Bounds | None:
    """Return a primitive's exact local AABB, or ``None`` if it is not supported."""
    enum = mujoco.mjtGeom
    values = tuple(float(value) for value in size)
    if geom_type in {int(enum.mjGEOM_BOX), int(enum.mjGEOM_ELLIPSOID)}:
        half = values
    elif geom_type == int(enum.mjGEOM_SPHERE):
        half = (values[0], values[0], values[0])
    elif geom_type == int(enum.mjGEOM_CYLINDER):
        half = (values[0], values[0], values[1])
    elif geom_type == int(enum.mjGEOM_CAPSULE):
        half = (values[0], values[0], values[0] + values[1])
    else:
        return None
    return Bounds(tuple(-value for value in half), half)  # type: ignore[arg-type]


def _box_geometry(object_: WorldObject) -> tuple[Vector3, Vector3]:
    center = tuple(object_.local_bounds.center[axis] * object_.scale[axis] for axis in range(3))
    half = tuple(
        max(abs(object_.local_bounds.extents[axis] * object_.scale[axis]) / 2.0, 1e-6)
        for axis in range(3)
    )
    return center, half  # type: ignore[return-value]


def _quaternion(rotation: Vector3) -> tuple[float, float, float, float]:
    """Return MuJoCo's scalar-first quaternion for Reality XYZ Euler angles."""
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


def _number(value: float) -> str:
    return f"{value:.17g}"
