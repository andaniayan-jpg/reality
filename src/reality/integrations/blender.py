"""Optional Blender active-scene integration.

This module has no import-time Blender dependency.  When imported by Blender it
uses its actual ``bpy`` scene data; when imported in ordinary Python it reports
that the runtime is unavailable.  It intentionally does not call Blender file
operators, execute scene scripts, or claim a lossless ``.blend`` interchange.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .._models import Bounds, Transform, Vector3, WorldObject
from .._world import World
from .base import (
    IntegrationCapability,
    IntegrationDescriptor,
    IntegrationStatus,
    IntegrationSyncResult,
    IntegrationUnavailableError,
)


@dataclass(frozen=True, slots=True)
class BlenderTransformChange:
    """One previewed object transform, addressed by a Reality object ID."""

    object_id: str
    object_name: str
    before: Transform
    after: Transform


@dataclass(frozen=True, slots=True)
class BlenderTransformPreview:
    """Non-mutating transform write plan for the current Blender scene."""

    changes: tuple[BlenderTransformChange, ...]
    units: str
    reason: str


class BlenderSceneIntegration:
    """Read Blender mesh objects and apply only a confirmed transform preview.

    ``read_active_scene`` reads evaluated object bounds from Blender's active
    scene. ``preview_transforms`` never mutates Blender. ``apply_transforms``
    requires an explicit ``confirmed=True`` and rolls earlier writes back if a
    later write fails. Mesh topology, modifiers, animation, materials,
    collections, and constraints remain Blender-owned and are reported as
    outside this initial bridge's scope.
    """

    _descriptor = IntegrationDescriptor(
        name="blender-active-scene",
        version="1",
        runtime="Blender bpy",
        capabilities=frozenset(
            {
                IntegrationCapability.READ_TRANSFORMS,
                IntegrationCapability.WRITE_TRANSFORMS,
                IntegrationCapability.READ_MESHES,
                IntegrationCapability.READ_HIERARCHY,
                IntegrationCapability.RENDER_PREVIEW,
            }
        ),
        documentation_url="https://docs.blender.org/api/current/bpy.html",
    )

    @property
    def descriptor(self) -> IntegrationDescriptor:
        return self._descriptor

    def status(self) -> IntegrationStatus:
        try:
            bpy = _bpy()
        except IntegrationUnavailableError as error:
            return IntegrationStatus(
                descriptor=self.descriptor,
                available=False,
                reason=str(error),
            )
        return IntegrationStatus(
            descriptor=self.descriptor,
            available=True,
            reason="Blender bpy runtime is importable",
            runtime_version=str(getattr(bpy.app, "version_string", "unknown")),
        )

    def read_active_scene(self) -> tuple[World, IntegrationSyncResult]:
        """Read supported mesh objects from Blender's current active scene."""
        bpy = _bpy()
        objects: list[WorldObject] = []
        skipped: list[str] = []
        for object_ in bpy.context.scene.objects:
            if object_.type != "MESH":
                skipped.append(f"{object_.name}: unsupported Blender type {object_.type}")
                continue
            try:
                objects.append(_world_object(object_))
            except (TypeError, ValueError) as error:
                skipped.append(f"{object_.name}: {error}")
        world = World(objects, units="m")
        ids = tuple(object_.id for object_ in objects)
        return world, IntegrationSyncResult(
            integration=self.descriptor,
            direction="import",
            object_ids=ids,
            changed_object_ids=ids,
            reason="read mesh-object bounds and transforms from Blender active scene",
            warnings=tuple(skipped)
            + (
                "Blender scene units are represented as metres only when the scene unit scale is "
                "1; this adapter records no implicit coordinate conversion.",
            ),
            evidence={
                "scene_name": str(bpy.context.scene.name),
                "mesh_object_count": len(objects),
                "skipped_object_count": len(skipped),
                "scene_unit_system": str(bpy.context.scene.unit_settings.system),
                "scene_scale_length": float(bpy.context.scene.unit_settings.scale_length),
            },
        )

    def preview_transforms(self, world: World) -> BlenderTransformPreview:
        """Plan transform writes by matching Reality IDs to current mesh objects."""
        bpy = _bpy()
        by_id = {
            _blender_id(object_): object_
            for object_ in bpy.context.scene.objects
            if object_.type == "MESH"
        }
        changes: list[BlenderTransformChange] = []
        missing: list[str] = []
        for object_ in world.objects:
            blender_object = by_id.get(object_.id)
            if blender_object is None:
                missing.append(f"{object_.id} ({object_.name})")
                continue
            before = _transform(blender_object)
            if before != object_.transform:
                changes.append(
                    BlenderTransformChange(
                        object_id=object_.id,
                        object_name=str(blender_object.name),
                        before=before,
                        after=object_.transform,
                    )
                )
        if missing:
            raise ValueError(
                "Blender scene has no mesh object for Reality IDs: " + ", ".join(missing)
            )
        return BlenderTransformPreview(
            changes=tuple(changes),
            units=world.units,
            reason=(
                "preview only; call apply_transforms(..., confirmed=True) to write Blender state"
            ),
        )

    def apply_transforms(
        self,
        preview: BlenderTransformPreview,
        *,
        confirmed: bool = False,
    ) -> IntegrationSyncResult:
        """Apply a previously inspected plan after explicit confirmation.

        On a write error, values already changed by this call are restored.
        This does not guarantee rollback against concurrent user edits in
        Blender; callers should review and apply on the main thread.
        """
        if not confirmed:
            raise PermissionError("Blender writes require confirmed=True after preview review")
        bpy = _bpy()
        objects = {
            _blender_id(object_): object_
            for object_ in bpy.context.scene.objects
            if object_.type == "MESH"
        }
        applied: list[tuple[Any, Transform]] = []
        try:
            for change in preview.changes:
                object_ = objects.get(change.object_id)
                if object_ is None:
                    raise ValueError(f"Blender object disappeared before apply: {change.object_id}")
                if _transform(object_) != change.before:
                    raise ValueError(
                        f"Blender object changed after preview: {change.object_id}; "
                        "generate a new preview"
                    )
                _set_transform(object_, change.after)
                applied.append((object_, change.before))
        except Exception:
            for object_, before in reversed(applied):
                _set_transform(object_, before)
            raise
        return IntegrationSyncResult(
            integration=self.descriptor,
            direction="export",
            object_ids=tuple(change.object_id for change in preview.changes),
            changed_object_ids=tuple(change.object_id for change in preview.changes),
            reason="applied explicitly confirmed Blender transform preview",
            warnings=(
                "Only location, XYZ Euler rotation, and scale were written; mesh data was not "
                "changed.",
            ),
            evidence={
                "preview_change_count": len(preview.changes),
                "rollback_on_write_error": True,
            },
        )

    def import_world(self, source: Path) -> tuple[World, IntegrationSyncResult]:
        """Refuse file-driven loading rather than opening an arbitrary `.blend`."""
        del source
        raise IntegrationUnavailableError(
            "BlenderSceneIntegration reads the active Blender scene; it does not open .blend files"
        )

    def export_world(self, world: World, destination: Path) -> IntegrationSyncResult:
        """Refuse writing `.blend` files; use preview/apply in the active scene."""
        del world, destination
        raise IntegrationUnavailableError(
            "BlenderSceneIntegration writes confirmed transforms in the active Blender scene; "
            "it does not save .blend files"
        )


def register_addon() -> None:
    """Register a tiny inspect-only Blender operator in a real Blender session."""
    bpy = _bpy()
    operator = type(
        "REALITY_OT_inspect_active_scene",
        (bpy.types.Operator,),
        {
            "bl_idname": "reality.inspect_active_scene",
            "bl_label": "Inspect Active Scene with Reality",
            "bl_description": "Read mesh bounds/transforms without modifying the Blender scene",
            "execute": _inspect_operator_execute,
        },
    )
    bpy.utils.register_class(operator)


def _inspect_operator_execute(operator: Any, context: Any) -> set[str]:
    del context
    world, result = BlenderSceneIntegration().read_active_scene()
    operator.report({"INFO"}, f"Reality read {len(world.objects)} mesh objects")
    for warning in result.warnings:
        operator.report({"WARNING"}, warning)
    return {"FINISHED"}


def _bpy() -> Any:
    try:
        import bpy
    except ImportError as error:
        raise IntegrationUnavailableError(
            "Blender bpy is unavailable; run this adapter inside a supported Blender Python runtime"
        ) from error
    return bpy


def _blender_id(object_: Any) -> str:
    value = object_.get("reality_id")
    if isinstance(value, str) and value.strip():
        return value
    return f"blender:{object_.name_full}"


def _world_object(object_: Any) -> WorldObject:
    points = tuple(tuple(float(value) for value in corner) for corner in object_.bound_box)
    if len(points) != 8 or any(len(point) != 3 for point in points):
        raise ValueError("mesh object has invalid local bound-box data")
    return WorldObject(
        name=str(object_.name),
        id=_blender_id(object_),
        local_bounds=Bounds(_bound(points, min), _bound(points, max)),
        transform=_transform(object_),
        mesh=object_.data,
    )


def _transform(object_: Any) -> Transform:
    rotation = object_.rotation_euler.to_tuple()
    return Transform(
        position=_vector(object_.location),
        rotation=_vector(rotation),
        scale=_vector(object_.scale),
    )


def _set_transform(object_: Any, transform: Transform) -> None:
    object_.rotation_mode = "XYZ"
    object_.location = transform.position
    object_.rotation_euler = transform.rotation
    object_.scale = transform.scale


def _bound(points: tuple[tuple[float, ...], ...], reducer: Any) -> Vector3:
    values = tuple(float(reducer(point[index] for point in points)) for index in range(3))
    return cast(Vector3, values)


def _vector(values: Any) -> Vector3:
    result = tuple(float(value) for value in values)
    if len(result) != 3:
        raise ValueError("Blender transform must have exactly three components")
    return result


def unregister_addon() -> None:
    """Best-effort unregister of the optional inspect operator."""
    bpy = _bpy()
    operator = getattr(bpy.types, "REALITY_OT_inspect_active_scene", None)
    if operator is not None:
        bpy.utils.unregister_class(operator)


def supported_scene_objects(objects: Iterable[Any]) -> tuple[Any, ...]:
    """Return mesh objects only; exposed for host-side integration diagnostics."""
    return tuple(object_ for object_ in objects if getattr(object_, "type", None) == "MESH")
