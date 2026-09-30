"""Transactional, backend-owned editing for :class:`RealityModel`.

The editor deliberately delegates all geometry mutations to CadQuery/OCP or
Trimesh. It never converts a CAD solid to a mesh merely to perform an edit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from math import radians
from types import MappingProxyType
from typing import Any, Literal, cast

import numpy as np
import trimesh

from ._file_model import ModelAssembly, ModelPart, RealityModel, _model_from_parts
from ._models import Bounds, Transform, Vector3

EditKind = Literal[
    "translate",
    "rotate",
    "scale",
    "offset",
    "delete",
    "rename",
    "union",
    "subtract",
    "intersect",
    "hole",
    "pocket",
    "extrude",
    "fillet",
    "chamfer",
    "shell",
    "merge",
    "split",
    "crop",
    "simplify",
    "repair",
    "normals",
    "select_faces",
    "select_edges",
]


class EditOperationError(ValueError):
    """Raised when an edit cannot be applied without inventing geometry facts."""


@dataclass(frozen=True, slots=True)
class EditOperation:
    """One attempted edit and its measurement evidence."""

    index: int
    operation: str
    target_ids: tuple[str, ...]
    parameters: Mapping[str, object]
    before: Mapping[str, object]
    after: Mapping[str, object] | None
    warnings: tuple[str, ...] = ()
    failure: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "before", MappingProxyType(dict(self.before)))
        if self.after is not None:
            object.__setattr__(self, "after", MappingProxyType(dict(self.after)))


@dataclass(frozen=True, slots=True)
class EditValidation:
    """Post-edit validation without overstating unavailable topology checks."""

    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@dataclass(frozen=True, slots=True)
class EditResult:
    """Committed immutable model plus the complete structured edit history."""

    model: RealityModel
    history: tuple[EditOperation, ...]

    def validate(self) -> EditValidation:
        errors: list[str] = []
        warnings: list[str] = []
        for part in self.model.parts:
            if part.solid is not None:
                if not bool(part.solid.isValid()):
                    errors.append(f"{part.name}: OpenCascade reports an invalid solid")
                if (part.volume or 0.0) <= 1e-12:
                    errors.append(f"{part.name}: solid has zero volume")
                warnings.append(
                    f"{part.name}: exact self-intersection analysis is backend/version dependent."
                )
            elif part.mesh is not None:
                mesh = part.mesh
                if not bool(mesh.is_watertight):
                    warnings.append(f"{part.name}: mesh is not watertight")
                if not bool(mesh.is_winding_consistent):
                    errors.append(f"{part.name}: mesh normals have inconsistent winding")
                if bool(mesh.is_volume) and abs(float(mesh.volume)) <= 1e-12:
                    errors.append(f"{part.name}: mesh has zero volume")
            else:
                errors.append(f"{part.name}: no editable geometry is available")
        referenced = {part.id for part in self.model.parts}
        for assembly in self.model.assemblies:
            missing = set(assembly.part_ids) - referenced
            if missing:
                errors.append(f"{assembly.name}: references missing parts {sorted(missing)!r}")
        return EditValidation(
            valid=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            evidence={"part_count": len(self.model.parts), "history_length": len(self.history)},
        )

    def export(self, path: str) -> str:
        return str(self.model.export(path))


@dataclass(slots=True)
class EditSession:
    """Copy-on-write edit transaction over an immutable imported model."""

    _base: RealityModel
    _parts: tuple[ModelPart, ...] = field(init=False)
    _assemblies: tuple[ModelAssembly, ...] = field(init=False)
    _states: list[tuple[tuple[ModelPart, ...], tuple[ModelAssembly, ...]]] = field(init=False)
    _history: list[EditOperation] = field(default_factory=list, init=False)
    _redo: list[tuple[EditOperation, tuple[ModelPart, ...], tuple[ModelAssembly, ...]]] = field(
        default_factory=list, init=False
    )
    _selections: dict[tuple[str, str], tuple[int, ...]] = field(default_factory=dict, init=False)
    _closed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._parts = self._base.parts
        self._assemblies = self._base.assemblies
        self._states = [(self._parts, self._assemblies)]

    @property
    def history(self) -> tuple[EditOperation, ...]:
        return tuple(self._history)

    def apply(self, operation: EditKind, /, **parameters: object) -> EditSession:
        """Dispatch one named operation for plan-driven or API-backed editing."""
        dispatch: Mapping[str, Any] = {
            "translate": self.translate,
            "rotate": self.rotate,
            "scale": self.scale,
            "offset": self.offset,
            "delete": self.delete,
            "rename": self.rename,
            "union": self.union,
            "subtract": self.subtract,
            "intersect": self.intersect,
            "hole": self.hole,
            "pocket": self.pocket,
            "extrude": self.extrude,
            "fillet": self.fillet,
            "chamfer": self.chamfer,
            "shell": self.shell,
            "merge": self.merge,
            "split": self.split,
            "crop": self.crop,
            "simplify": self.simplify,
            "repair": self.repair,
            "normals": self.normals,
            "select_faces": self.select_faces,
            "select_edges": self.select_edges,
        }
        if operation not in dispatch:
            raise EditOperationError(f"unsupported edit operation {operation!r}")
        dispatch[operation](**parameters)
        return self

    def translate(
        self, target: str, *, x: float = 0.0, y: float = 0.0, z: float = 0.0
    ) -> EditSession:
        delta = (float(x), float(y), float(z))
        return self._replace_geometry(
            "translate", (target,), {"x": x, "y": y, "z": z}, lambda part: _translate(part, delta)
        )

    def rotate(self, target: str, *, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> EditSession:
        angles = (float(x), float(y), float(z))
        return self._replace_geometry(
            "rotate",
            (target,),
            {"x": x, "y": y, "z": z, "units": "degrees"},
            lambda part: _rotate(part, angles),
        )

    def scale(self, target: str, factor: float) -> EditSession:
        if factor <= 0.0:
            raise EditOperationError("scale factor must be positive")
        return self._replace_geometry(
            "scale", (target,), {"factor": factor}, lambda part: _scale(part, float(factor))
        )

    def offset(self, target: str, distance: float, *, tolerance: float = 1e-6) -> EditSession:
        """Offset a CAD solid using OpenCascade's native offset-shape algorithm.

        Positive values expand the solid and negative values offset inward.  The
        operation is intentionally unavailable for mesh parts: creating an
        apparent mesh offset would not preserve B-rep semantics or topology.
        """
        if distance == 0.0:
            raise EditOperationError("offset distance must be non-zero")
        if tolerance <= 0.0:
            raise EditOperationError("offset tolerance must be positive")
        part = self._cad_part(target)
        return self._replace_cad(
            "offset",
            (part,),
            {"distance": distance, "tolerance": tolerance},
            lambda solid: _offset_solid(solid, float(distance), float(tolerance)),
        )

    def delete(self, target: str) -> EditSession:
        part = self._part(target)

        def mutate(
            _: tuple[ModelPart, ...],
        ) -> tuple[tuple[ModelPart, ...], tuple[ModelAssembly, ...]]:
            parts = tuple(item for item in self._parts if item.id != part.id)
            assemblies = tuple(
                replace(
                    assembly,
                    part_ids=tuple(item_id for item_id in assembly.part_ids if item_id != part.id),
                )
                for assembly in self._assemblies
            )
            return parts, assemblies

        return self._transaction("delete", (part,), {}, mutate)

    def rename(self, target: str, name: str) -> EditSession:
        if not name.strip():
            raise EditOperationError("part name must not be empty")
        part = self._part(target)
        if any(item.name == name and item.id != part.id for item in self._parts):
            raise EditOperationError(f"part name {name!r} is already in use")
        return self._replace_geometry(
            "rename", (target,), {"name": name}, lambda item: replace(item, name=name)
        )

    def union(self, target: str, other: str) -> EditSession:
        return self._boolean(
            "union", target, other, lambda first, second: first.fuse(second), remove_other=True
        )

    def subtract(self, target: str, other: str) -> EditSession:
        return self._boolean("subtract", target, other, lambda first, second: first.cut(second))

    def intersect(self, target: str, other: str) -> EditSession:
        return self._boolean(
            "intersect", target, other, lambda first, second: first.intersect(second)
        )

    def hole(
        self,
        target: str,
        *,
        radius: float,
        depth: float,
        x: float = 0.0,
        y: float = 0.0,
        z: float | None = None,
    ) -> EditSession:
        if radius <= 0.0 or depth <= 0.0:
            raise EditOperationError("hole radius and depth must be positive")
        part = self._cad_part(target)

        def cutter(solid: Any) -> Any:
            import cadquery as cq

            start = part.bounds.minimum[2] - 1e-6 if z is None else float(z)
            return (
                cq.Workplane("XY")
                .workplane(offset=start)
                .center(x, y)
                .circle(radius)
                .extrude(depth)
                .val()
            )

        return self._replace_cad(
            "hole",
            (part,),
            {"radius": radius, "depth": depth, "x": x, "y": y, "z": z},
            lambda solid: solid.cut(cutter(solid)),
        )

    def pocket(
        self,
        target: str,
        *,
        width: float,
        height: float,
        depth: float,
        x: float = 0.0,
        y: float = 0.0,
        z: float | None = None,
    ) -> EditSession:
        if min(width, height, depth) <= 0.0:
            raise EditOperationError("pocket width, height, and depth must be positive")
        part = self._cad_part(target)

        def cut(solid: Any) -> Any:
            import cadquery as cq

            start = part.bounds.maximum[2] - depth if z is None else float(z)
            tool = (
                cq.Workplane("XY")
                .workplane(offset=start)
                .center(x, y)
                .box(width, height, depth, centered=(True, True, False))
                .val()
            )
            return solid.cut(tool)

        return self._replace_cad(
            "pocket",
            (part,),
            {"width": width, "height": height, "depth": depth, "x": x, "y": y, "z": z},
            cut,
        )

    def select_faces(self, target: str, indices: Sequence[int]) -> EditSession:
        return self._select("faces", target, indices)

    def select_edges(self, target: str, indices: Sequence[int]) -> EditSession:
        return self._select("edges", target, indices)

    def extrude(
        self, target: str, distance: float, *, face_indices: Sequence[int] | None = None
    ) -> EditSession:
        if distance == 0.0:
            raise EditOperationError("extrusion distance must be non-zero")
        part = self._cad_part(target)
        selected = self._indices(part, "faces", face_indices)
        return self._replace_cad(
            "extrude",
            (part,),
            {"distance": distance, "face_indices": list(selected)},
            lambda solid: _workplane(solid)
            .newObject([solid.Faces()[index] for index in selected])
            .extrude(distance)
            .val(),
        )

    def fillet(
        self, target: str, radius: float, *, edge_indices: Sequence[int] | None = None
    ) -> EditSession:
        if radius <= 0.0:
            raise EditOperationError("fillet radius must be positive")
        part = self._cad_part(target)
        selected = self._indices(part, "edges", edge_indices)
        return self._replace_cad(
            "fillet",
            (part,),
            {"radius": radius, "edge_indices": list(selected)},
            lambda solid: _workplane(solid)
            .newObject([solid.Edges()[index] for index in selected])
            .fillet(radius)
            .val(),
        )

    def chamfer(
        self, target: str, distance: float, *, edge_indices: Sequence[int] | None = None
    ) -> EditSession:
        if distance <= 0.0:
            raise EditOperationError("chamfer distance must be positive")
        part = self._cad_part(target)
        selected = self._indices(part, "edges", edge_indices)
        return self._replace_cad(
            "chamfer",
            (part,),
            {"distance": distance, "edge_indices": list(selected)},
            lambda solid: _workplane(solid)
            .newObject([solid.Edges()[index] for index in selected])
            .chamfer(distance)
            .val(),
        )

    def shell(
        self, target: str, thickness: float, *, face_indices: Sequence[int] | None = None
    ) -> EditSession:
        if thickness == 0.0:
            raise EditOperationError("shell thickness must be non-zero")
        part = self._cad_part(target)
        selected = self._indices(part, "faces", face_indices)
        return self._replace_cad(
            "shell",
            (part,),
            {"thickness": thickness, "face_indices": list(selected)},
            lambda solid: _workplane(solid)
            .newObject([solid.Faces()[index] for index in selected])
            .shell(thickness)
            .val(),
        )

    def merge(self, targets: Sequence[str], *, name: str | None = None) -> EditSession:
        parts = tuple(self._mesh_part(target) for target in targets)
        if len(parts) < 2:
            raise EditOperationError("mesh merge requires at least two parts")
        merged = trimesh.util.concatenate([_world_mesh(part) for part in parts])
        primary = parts[0]
        replacement = _mesh_part(primary, merged, name=name or primary.name)
        return self._replace_many(
            "merge",
            parts,
            {"name": name},
            {primary.id: replacement},
            set(part.id for part in parts[1:]),
        )

    def split(self, target: str) -> EditSession:
        part = self._mesh_part(target)
        components = tuple(_world_mesh(part).split(only_watertight=False))
        if len(components) < 2:
            raise EditOperationError("mesh has no disconnected components to split")
        replacements = {
            f"{part.id}-component-{index}": _mesh_part(
                part, mesh, name=f"{part.name}-{index}", id=f"{part.id}-component-{index}"
            )
            for index, mesh in enumerate(components, start=1)
        }
        return self._replace_many("split", (part,), {}, replacements, {part.id})

    def crop(self, target: str, minimum: Sequence[float], maximum: Sequence[float]) -> EditSession:
        if len(minimum) != 3 or len(maximum) != 3:
            raise EditOperationError("crop bounds must contain three coordinates")
        part = self._mesh_part(target)
        bounds = Bounds(cast(Vector3, tuple(minimum)), cast(Vector3, tuple(maximum)))

        def crop_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
            result = _world_mesh(part)
            for axis in range(3):
                lower = np.zeros(3)
                lower[axis] = bounds.minimum[axis]
                normal = np.zeros(3)
                normal[axis] = 1.0
                result = result.slice_plane(lower, normal, cap=False)
                upper = np.zeros(3)
                upper[axis] = bounds.maximum[axis]
                normal[axis] = -1.0
                result = result.slice_plane(upper, normal, cap=False)
            if result.is_empty:
                raise EditOperationError("crop removed all mesh geometry")
            return result

        return self._replace_geometry(
            "crop",
            (target,),
            {"minimum": list(bounds.minimum), "maximum": list(bounds.maximum)},
            lambda _: _mesh_part(part, crop_mesh(_world_mesh(part))),
        )

    def simplify(self, target: str, face_count: int) -> EditSession:
        if face_count < 4:
            raise EditOperationError("face_count must be at least four")
        part = self._mesh_part(target)
        try:
            simplified = _world_mesh(part).simplify_quadric_decimation(face_count)
        except Exception as error:
            raise EditOperationError(
                "mesh simplification requires Trimesh's optional decimation backend"
            ) from error
        return self._replace_geometry(
            "simplify",
            (target,),
            {"face_count": face_count},
            lambda _: _mesh_part(part, simplified),
        )

    def repair(self, target: str) -> EditSession:
        part = self._mesh_part(target)
        mesh = _world_mesh(part)
        mesh.merge_vertices()
        mesh.remove_unreferenced_vertices()
        trimesh.repair.fill_holes(mesh)
        trimesh.repair.fix_normals(mesh)
        return self._replace_geometry("repair", (target,), {}, lambda _: _mesh_part(part, mesh))

    def normals(self, target: str) -> EditSession:
        part = self._mesh_part(target)
        mesh = _world_mesh(part)
        trimesh.repair.fix_normals(mesh)
        return self._replace_geometry("normals", (target,), {}, lambda _: _mesh_part(part, mesh))

    def undo(self) -> EditSession:
        if not self._history:
            raise EditOperationError("there is no applied edit to undo")
        operation = self._history.pop()
        state = self._states.pop()
        self._redo.append((operation, state[0], state[1]))
        self._parts, self._assemblies = self._states[-1]
        return self

    def redo(self) -> EditSession:
        if not self._redo:
            raise EditOperationError("there is no undone edit to redo")
        operation, parts, assemblies = self._redo.pop()
        self._parts, self._assemblies = parts, assemblies
        self._states.append((parts, assemblies))
        self._history.append(operation)
        return self

    def preview(self) -> RealityModel:
        return self._build_model()

    def commit(self) -> EditResult:
        self._ensure_open()
        self._closed = True
        return EditResult(self._build_model(), tuple(self._history))

    def rollback(self) -> RealityModel:
        self._ensure_open()
        self._closed = True
        self._parts, self._assemblies = self._states[0]
        return self._base

    def _select(
        self, kind: Literal["faces", "edges"], target: str, indices: Sequence[int]
    ) -> EditSession:
        part = self._cad_part(target)
        available = part.faces if kind == "faces" else part.edges
        selected = tuple(int(index) for index in indices)
        if not selected or any(index < 0 or index >= len(available or ()) for index in selected):
            raise EditOperationError(f"{kind} selection contains an impossible reference")
        self._selections[(part.id, kind)] = selected
        return self._transaction(
            f"select_{kind}",
            (part,),
            {"indices": list(selected)},
            lambda _: (self._parts, self._assemblies),
        )

    def _indices(
        self, part: ModelPart, kind: Literal["faces", "edges"], supplied: Sequence[int] | None
    ) -> tuple[int, ...]:
        selected = (
            tuple(int(index) for index in supplied)
            if supplied is not None
            else self._selections.get((part.id, kind), ())
        )
        available = part.faces if kind == "faces" else part.edges
        if not selected:
            raise EditOperationError(f"select {kind} first or provide {kind[:-1]}_indices")
        if any(index < 0 or index >= len(available or ()) for index in selected):
            raise EditOperationError(f"{kind} selection contains an impossible reference")
        return selected

    def _boolean(
        self, operation: str, target: str, other: str, func: Any, *, remove_other: bool = False
    ) -> EditSession:
        first, second = self._cad_part(target), self._cad_part(other)
        replacement = _cad_part(first, func(first.solid, second.solid))
        removed = {second.id} if remove_other else set()
        return self._replace_many(operation, (first, second), {}, {first.id: replacement}, removed)

    def _replace_cad(
        self,
        operation: str,
        targets: Sequence[ModelPart],
        parameters: Mapping[str, object],
        action: Any,
    ) -> EditSession:
        part = targets[0]
        return self._replace_many(
            operation,
            tuple(targets),
            parameters,
            {part.id: _cad_part(part, action(part.solid))},
            set(),
        )

    def _replace_geometry(
        self, operation: str, targets: Sequence[str], parameters: Mapping[str, object], action: Any
    ) -> EditSession:
        part = self._part(targets[0])
        return self._replace_many(operation, (part,), parameters, {part.id: action(part)}, set())

    def _replace_many(
        self,
        operation: str,
        targets: Sequence[ModelPart],
        parameters: Mapping[str, object],
        replacements: Mapping[str, ModelPart],
        removed: set[str],
    ) -> EditSession:
        def mutate(
            _: tuple[ModelPart, ...],
        ) -> tuple[tuple[ModelPart, ...], tuple[ModelAssembly, ...]]:
            parts: list[ModelPart] = []
            for item in self._parts:
                if item.id in removed:
                    continue
                parts.append(replacements.get(item.id, item))
            existing_ids = {item.id for item in self._parts}
            parts.extend(
                item for item_id, item in replacements.items() if item_id not in existing_ids
            )
            assemblies = _assemblies_after_edit(
                self._assemblies, replacements, removed, existing_ids
            )
            return tuple(parts), assemblies

        return self._transaction(operation, tuple(targets), parameters, mutate)

    def _transaction(
        self,
        operation: str,
        targets: Sequence[ModelPart],
        parameters: Mapping[str, object],
        mutate: Any,
    ) -> EditSession:
        self._ensure_open()
        before = _measure(targets)
        try:
            parts, assemblies = mutate(self._parts)
            if not parts:
                raise EditOperationError("an edit may not delete every model part")
            after_targets = tuple(
                item for item in parts if item.id in {target.id for target in targets}
            )
            if not after_targets and operation == "split":
                after_targets = parts
            record = EditOperation(
                len(self._history) + 1,
                operation,
                tuple(target.id for target in targets),
                parameters,
                before,
                _measure(after_targets),
            )
        except Exception as error:
            record = EditOperation(
                len(self._history) + 1,
                operation,
                tuple(target.id for target in targets),
                parameters,
                before,
                None,
                failure=str(error),
            )
            self._history.append(record)
            raise EditOperationError(f"{operation} failed: {error}") from error
        self._parts, self._assemblies = parts, assemblies
        self._states.append((parts, assemblies))
        self._history.append(record)
        self._redo.clear()
        return self

    def _part(self, reference: str) -> ModelPart:
        matches = [part for part in self._parts if part.id == reference or part.name == reference]
        if len(matches) != 1:
            raise EditOperationError(
                f"part reference {reference!r} resolved to {len(matches)} parts"
            )
        return matches[0]

    def _cad_part(self, reference: str) -> ModelPart:
        part = self._part(reference)
        if part.solid is None:
            raise EditOperationError(
                f"{part.name!r} is mesh geometry; this operation requires B-rep CAD"
            )
        return part

    def _mesh_part(self, reference: str) -> ModelPart:
        part = self._part(reference)
        if part._mesh is None:
            raise EditOperationError(
                f"{part.name!r} is B-rep CAD; this operation requires a source mesh"
            )
        return part

    def _build_model(self) -> RealityModel:
        return _model_from_parts(
            self._base.source,
            self._base.format,
            self._base.units,
            self._parts,
            self._assemblies,
            {
                **self._base.metadata,
                "edit_history_length": len(self._history),
                "edited": bool(self._history),
            },
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise EditOperationError("edit session is already committed or rolled back")


def _measure(parts: Sequence[ModelPart]) -> Mapping[str, object]:
    return {
        "part_count": len(parts),
        "volume": sum(part.volume or 0.0 for part in parts),
        "surface_area": sum(part.surface_area or 0.0 for part in parts),
        "bounds": [_bounds_dict(part.bounds) for part in parts],
    }


def _bounds_dict(bounds: Bounds) -> Mapping[str, object]:
    return {"minimum": bounds.minimum, "maximum": bounds.maximum}


def _cad_part(template: ModelPart, solid: Any, *, name: str | None = None) -> ModelPart:
    box = solid.BoundingBox()
    return replace(
        template,
        name=name or template.name,
        transform=Transform(),
        bounds=Bounds((box.xmin, box.ymin, box.zmin), (box.xmax, box.ymax, box.zmax)),
        solid=solid,
        _mesh=None,
        metadata={**template.metadata, "edited": True},
    )


def _mesh_part(
    template: ModelPart, mesh: trimesh.Trimesh, *, name: str | None = None, id: str | None = None
) -> ModelPart:
    return replace(
        template,
        id=id or template.id,
        name=name or template.name,
        transform=Transform(),
        bounds=Bounds.from_points(np.asarray(mesh.bounds, dtype=np.float64)),
        _mesh=mesh,
        solid=None,
        metadata={**template.metadata, "edited": True, "cad_semantics": "not-preserved"},
    )


def _world_mesh(part: ModelPart) -> trimesh.Trimesh:
    if part._mesh is None:
        raise EditOperationError("operation requires source mesh geometry")
    mesh = part._mesh.copy()
    mesh.apply_transform(part.transform.matrix)
    return mesh


def _translate(part: ModelPart, delta: tuple[float, float, float]) -> ModelPart:
    if part.solid is not None:
        return _cad_part(part, part.solid.translate(delta))
    mesh = _world_mesh(part)
    mesh.apply_translation(delta)
    return _mesh_part(part, mesh)


def _rotate(part: ModelPart, degrees: tuple[float, float, float]) -> ModelPart:
    if part.solid is not None:
        result = part.solid
        for axis, angle in enumerate(degrees):
            if angle:
                endpoint = [0.0, 0.0, 0.0]
                endpoint[axis] = 1.0
                result = result.rotate((0.0, 0.0, 0.0), tuple(endpoint), angle)
        return _cad_part(part, result)
    mesh = _world_mesh(part)
    matrix = Transform(rotation=cast(Vector3, tuple(radians(value) for value in degrees))).matrix
    mesh.apply_transform(matrix)
    return _mesh_part(part, mesh)


def _scale(part: ModelPart, factor: float) -> ModelPart:
    if part.solid is not None:
        return _cad_part(part, part.solid.scale(factor))
    mesh = _world_mesh(part)
    mesh.apply_scale(factor)
    return _mesh_part(part, mesh)


def _offset_solid(solid: Any, distance: float, tolerance: float) -> Any:
    """Build an OpenCascade offset and retain the returned B-rep shape."""
    try:
        import cadquery as cq
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    except ImportError as error:  # pragma: no cover - a CAD part cannot exist without it
        raise EditOperationError("CadQuery/OCP is required for this CAD edit") from error
    maker = BRepOffsetAPI_MakeOffsetShape()
    maker.PerformByJoin(solid.wrapped, distance, tolerance)
    if not maker.IsDone():
        raise EditOperationError(
            "OpenCascade could not construct this offset; reduce the distance or simplify the solid"
        )
    result = cq.Shape.cast(maker.Shape())
    if result.isNull() or not result.isValid():
        raise EditOperationError("OpenCascade produced an invalid offset solid")
    return result


def _workplane(solid: Any) -> Any:
    try:
        import cadquery as cq
    except ImportError as error:  # pragma: no cover - a CAD part cannot exist without it
        raise EditOperationError("CadQuery/OCP is required for this CAD edit") from error
    return cq.Workplane("XY").newObject([solid])


def _assemblies_after_edit(
    assemblies: Sequence[ModelAssembly],
    replacements: Mapping[str, ModelPart],
    removed: set[str],
    existing_ids: set[str],
) -> tuple[ModelAssembly, ...]:
    added_ids = tuple(item_id for item_id in replacements if item_id not in existing_ids)
    result: list[ModelAssembly] = []
    for assembly in assemblies:
        part_ids: list[str] = []
        for part_id in assembly.part_ids:
            if part_id not in removed:
                part_ids.append(part_id)
            elif added_ids:
                part_ids.extend(added_ids)
        result.append(replace(assembly, part_ids=tuple(part_ids)))
    return tuple(result)
