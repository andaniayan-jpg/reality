"""Truthful MJCF interchange through the optional MuJoCo runtime.

This adapter is deliberately a scene-geometry bridge, not an MJCF emulator.
MuJoCo compiles the source XML and supplies world-space geom poses. Reality
imports only supported primitive geoms as their exact local bounding boxes;
mesh, plane, height-field, joint, actuator, sensor, and contact semantics are
reported as unsupported rather than guessed.
"""

from __future__ import annotations

from math import cos, sin
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import escape

import numpy as np
from numpy.typing import NDArray

from .._models import Bounds, Transform, Vector3, WorldObject
from .._world import World
from .base import (
    IntegrationCapability,
    IntegrationDescriptor,
    IntegrationSyncResult,
    IntegrationUnavailableError,
)

if TYPE_CHECKING:
    pass


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

    def import_world(self, source: Path) -> tuple[World, IntegrationSyncResult]:
        """Compile an MJCF source and import its supported primitive geoms."""
        mujoco = _mujoco()
        try:
            model = mujoco.MjModel.from_xml_path(str(source))
        except Exception as error:  # MuJoCo exposes several parser exception types.
            raise ValueError(f"MuJoCo could not compile MJCF scene {source}: {error}") from error
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
            matrix = np.eye(4, dtype=np.float64)
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
