"""Copy-on-write, deferred mesh edits for file-based physical interpretations.

This is deliberately separate from the CAD edit transaction: a tessellated
approximation must never silently replace an exact B-rep.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import isfinite, radians
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
import trimesh

from ._file_model import ModelPart, _model_from_parts
from ._materials import material as lookup_material
from ._models import Bounds, Transform

if TYPE_CHECKING:
    from ._physics_object import PhysicsObject


class PhysicsModificationError(ValueError):
    """An edit lacks geometry, semantics, or evidence needed for safe execution."""


@dataclass(frozen=True, slots=True)
class _PendingEdit:
    operation: str
    parameters: Mapping[str, object]
    description: str


@dataclass(frozen=True, slots=True)
class _NamedMaterial:
    name: str


@dataclass(frozen=True, slots=True)
class DiffResult:
    """Measured differences; unavailable engineering scores remain ``None``."""

    changes: tuple[str, ...]
    mass_delta: float | None
    volume_delta: float | None
    weak_points_fixed: int | None
    improvement_score: float | None


class PhysicsModification:
    """A chainable draft over an immutable :class:`PhysicsObject`.

    Methods append small commands, not mesh copies. The source is never changed.
    ``result`` or ``export`` applies pending commands in one materialization.
    """

    def __init__(self, source: PhysicsObject) -> None:
        if not source.supported or source.model is None:
            raise PhysicsModificationError(source.message or "source geometry is unavailable")
        self.source = source
        self._pending: list[_PendingEdit] = []
        self._result: PhysicsObject | None = None
        self.repair_log: list[str] = []
        self.optimization_log: list[str] = []

    @property
    def modify(self) -> PhysicsModification:
        return self

    @property
    def change_log(self) -> tuple[str, ...]:
        return tuple(edit.description for edit in self._pending)

    def _append(
        self, operation: str, description: str, **parameters: object
    ) -> PhysicsModification:
        self._pending.append(_PendingEdit(operation, parameters, description))
        self._result = None
        return self

    def material(self, name: str) -> PhysicsModification:
        if not name.strip() or len(name) > 100 or any(ord(char) < 32 for char in name):
            raise PhysicsModificationError(
                "material name must be printable and at most 100 characters"
            )
        return self._append("material", f"Material set to {name}", name=name.strip())

    def scale(
        self,
        factor: float | None = None,
        *,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> PhysicsModification:
        if factor is not None and any(value is not None for value in (x, y, z)):
            raise PhysicsModificationError("use factor or x/y/z, not both")
        factors = (factor, factor, factor) if factor is not None else (x, y, z)
        if any(value is None or not isfinite(value) or value <= 0 for value in factors):
            raise PhysicsModificationError("scale needs three positive finite factors")
        triple = cast(tuple[float, float, float], factors)
        return self._append("scale", f"Scaled by {triple}", factors=triple)

    def translate(self, *, x: float = 0, y: float = 0, z: float = 0) -> PhysicsModification:
        if not all(isfinite(value) for value in (x, y, z)):
            raise PhysicsModificationError("translation must be finite")
        return self._append("translate", f"Translated by {(x, y, z)}", offset=(x, y, z))

    def rotate(self, *, axis: str, degrees: float) -> PhysicsModification:
        if axis not in {"x", "y", "z"} or not isfinite(degrees):
            raise PhysicsModificationError("rotation needs axis x, y, or z and finite degrees")
        return self._append(
            "rotate", f"Rotated {degrees} degrees around {axis}", axis=axis, degrees=degrees
        )

    def mirror(self, *, axis: str) -> PhysicsModification:
        if axis not in {"x", "y", "z"}:
            raise PhysicsModificationError("mirror axis must be x, y, or z")
        return self._append("mirror", f"Mirrored across {axis}=0", axis=axis)

    def remove_component(self, name: str) -> PhysicsModification:
        self._resolve_names((name,))
        return self._append("remove", f"Removed component {name}", name=name)

    def merge_components(self, names: Sequence[str]) -> PhysicsModification:
        resolved = self._resolve_names(names)
        if len(resolved) < 2:
            raise PhysicsModificationError("merge requires at least two distinct components")
        return self._append("merge", f"Merged components {', '.join(names)}", names=tuple(names))

    def thickness(self, *, region: str, value: float) -> PhysicsModification:
        """Set the shortest AABB dimension of a named *whole mesh component*.

        This is not local wall-thickness editing. A generic ``walls`` label is
        ambiguous without authored face groups and is rejected.
        """
        if not isfinite(value) or value <= 0:
            raise PhysicsModificationError("thickness must be positive and finite")
        self._resolve_names((region,))
        return self._append(
            "thickness", f"Set {region} minimum AABB extent to {value}", region=region, value=value
        )

    def hollow(self, *, wall_thickness: float) -> PhysicsModification:
        if not isfinite(wall_thickness) or wall_thickness <= 0:
            raise PhysicsModificationError("wall_thickness must be positive and finite")
        return self._append(
            "hollow",
            f"Hollowed axis-aligned box components with wall {wall_thickness}",
            wall_thickness=wall_thickness,
        )

    def repair(self) -> PhysicsModification:
        return self._append("repair", "Requested mesh repair")

    def fix_weak_points(self) -> PhysicsModification:
        """Apply an explicitly heuristic *whole-part* AABB thickness screen.

        No load case exists here, so this is not a verified structural fix.
        """
        for candidate in self.source.weak_points:
            part = next((item for item in self.source.parts if item.id == candidate.part_id), None)
            if part is not None and min(part.bounds.extents) > 0:
                target = 0.05 * max(part.bounds.extents)
                self.thickness(region=part.name, value=target)
        if not self.source.weak_points:
            self.optimization_log.append("No AABB thin-part candidates were reported")
        return self

    def optimize_for(self, goal: str) -> PhysicsModification:
        if goal not in {
            "minimum_weight",
            "maximum_strength",
            "printable",
            "balanced",
            "earthquake_safe",
        }:
            raise PhysicsModificationError(f"unsupported optimization goal {goal!r}")
        if goal == "balanced" and self.source.centre_of_mass is not None:
            x, y, z = self.source.centre_of_mass
            self.translate(x=-x, y=-y, z=-z)
            self.optimization_log.append(
                "Aligned geometric centre of mass with the origin; stability is unverified"
            )
            return self
        self.optimization_log.append(
            f"{goal}: no reliable optimization without loads, constraints, "
            "and a validated objective"
        )
        return self

    def apply(self, instruction: str, *, provider: object | None = None) -> PhysicsModification:
        """Apply a narrowly validated instruction; provider errors become evidence.

        The optional provider may expose ``interpret_edit(text) -> mapping``.
        Otherwise an installed local model is tried before literal parsing.
        Arbitrary model text is never executed as Python or geometry code.
        """
        proposal: Mapping[str, object] | None = None
        if provider is None:
            try:
                from ._providers.base import AITask
                from ._providers.ollama import OllamaProvider

                local = OllamaProvider(timeout=2.0)
                installed = next(
                    (
                        name
                        for name in local.available_models()
                        if name == "qwen3:14b" or name.startswith("qwen3:14b:")
                    ),
                    None,
                )
                if installed is not None:
                    local.timeout = 20.0
                    raw = local.complete(
                        AITask(
                            prompt=(
                                "Return one JSON object only with keys method and args. "
                                "Allowed methods: scale, translate, rotate, material, "
                                "remove_component, mirror. Do not invent geometry or units. "
                                f"Existing parts: {[part.name for part in self.source.parts]}. "
                                f"Units: {self.source.units}. Request: {instruction}"
                            )
                        ),
                        model=installed,
                    )
                    decoded = json.loads(raw)
                    if isinstance(decoded, Mapping):
                        proposal = decoded
            except Exception as error:
                self.optimization_log.append(
                    f"Local interpretation unavailable: {type(error).__name__}"
                )
        if provider is not None:
            try:
                raw = provider.interpret_edit(instruction)  # type: ignore[attr-defined]
                decoded = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(decoded, Mapping):
                    proposal = decoded
            except Exception as error:
                self.optimization_log.append(f"Provider unavailable: {type(error).__name__}")
        if proposal is None:
            literal = instruction.strip().lower()
            match = re.fullmatch(
                r"(?:scale(?: it)? by |make it )(\d+(?:\.\d+)?)\s*(?:x|times(?: as big)?)",
                literal,
            )
            if match:
                proposal = {"method": "scale", "args": {"factor": float(match.group(1))}}
            elif literal == "remove all windows":
                windows = [part.name for part in self.source.parts if "window" in part.name.lower()]
                for name in windows:
                    self.remove_component(name)
                if not windows:
                    self.optimization_log.append("No window-named components were found")
                return self
            elif fit := re.fullmatch(r"scale to fit in a (\d+(?:\.\d+)?)m cube", literal):
                metres_per_unit = {"m": 1.0, "mm": 0.001, "cm": 0.01}
                unit_scale = metres_per_unit.get(self.source.units)
                maximum = max(self.source.bounds.extents)
                if unit_scale is not None and maximum > 0:
                    proposal = {
                        "method": "scale",
                        "args": {"factor": float(fit.group(1)) / (maximum * unit_scale)},
                    }
            elif thick := re.fullmatch(r"make the ([\w.-]+) (\d+(?:\.\d+)?)% thicker", literal):
                selected = [
                    part for part in self.source.parts if part.name.lower() == thick.group(1)
                ]
                if len(selected) == 1:
                    value = min(selected[0].bounds.extents) * (1 + float(thick.group(2)) / 100)
                    if value > 0:
                        self.thickness(region=selected[0].name, value=value)
                        return self
        if proposal is None:
            self.optimization_log.append(
                "Instruction not applied: insufficient unambiguous geometry detail"
            )
            return self
        method = proposal.get("method")
        arguments = proposal.get("args", {})
        if not isinstance(arguments, Mapping) or method not in {
            "scale",
            "translate",
            "rotate",
            "material",
            "remove_component",
            "mirror",
        }:
            self.optimization_log.append(
                "Instruction not applied: proposed operation is unsupported"
            )
            return self
        try:
            getattr(self, cast(str, method))(**arguments)
        except (PhysicsModificationError, TypeError, ValueError) as error:
            self.optimization_log.append(f"Instruction not applied: {error}")
        return self

    @property
    def result(self) -> PhysicsObject:
        if self._result is None:
            self._result = self._materialize()
        return self._result

    @property
    def export(self) -> PhysicsExporter:
        return PhysicsExporter(self)

    def _resolve_names(self, names: Sequence[str]) -> tuple[ModelPart, ...]:
        selected: list[ModelPart] = []
        for name in names:
            matches = [part for part in self.source.parts if name in {part.name, part.id}]
            if len(matches) != 1:
                raise PhysicsModificationError(f"component {name!r} is missing or ambiguous")
            if matches[0] not in selected:
                selected.append(matches[0])
        return tuple(selected)

    def _materialize(self) -> PhysicsObject:
        from ._physics_object import physics_object_from_model, physics_scene_from_model

        source_model = self.source.model
        assert source_model is not None
        parts = list(source_model.parts)
        selected_material: str | None = None
        # Each part is copied only on its first geometry-changing command.
        touched: set[str] = set()
        for edit in self._pending:
            parameters = edit.parameters
            if edit.operation == "material":
                selected_material = cast(str, parameters["name"])
                continue
            if edit.operation == "remove":
                name = cast(str, parameters["name"])
                parts = [part for part in parts if name not in {part.name, part.id}]
                continue
            if edit.operation == "merge":
                names = cast(tuple[str, ...], parameters["names"])
                chosen = [part for part in parts if part.name in names or part.id in names]
                if len(chosen) != len(names):
                    raise PhysicsModificationError("merge target was removed by an earlier edit")
                meshes = [_world_mesh(part) for part in chosen]
                merged = trimesh.util.concatenate(meshes)
                template = chosen[0]
                parts = [part for part in parts if part not in chosen]
                parts.append(
                    _new_part(template, merged, name="+".join(part.name for part in chosen))
                )
                touched.add(template.id)
                continue
            if edit.operation == "thickness":
                region = cast(str, parameters["region"])
                targets = [part for part in parts if region in {part.name, part.id}]
                if len(targets) != 1:
                    raise PhysicsModificationError(f"thickness target {region!r} is unavailable")
            else:
                targets = parts
            replacements: dict[str, ModelPart] = {}
            for part in targets:
                if part.solid is not None or part._mesh is None:
                    raise PhysicsModificationError(
                        "this mesh operation cannot preserve CAD B-rep semantics"
                    )
                mesh = (
                    _world_mesh(part)
                    if part.id not in touched
                    else cast(trimesh.Trimesh, part._mesh)
                )
                if edit.operation == "scale":
                    mesh.apply_scale(cast(tuple[float, float, float], parameters["factors"]))
                elif edit.operation == "translate":
                    mesh.apply_translation(cast(tuple[float, float, float], parameters["offset"]))
                elif edit.operation == "rotate":
                    axis = cast(str, parameters["axis"])
                    direction = np.eye(3)["xyz".index(axis)]
                    mesh.apply_transform(
                        trimesh.transformations.rotation_matrix(
                            radians(cast(float, parameters["degrees"])), direction
                        )
                    )
                elif edit.operation == "mirror":
                    matrix = np.eye(4)
                    matrix[
                        "xyz".index(cast(str, parameters["axis"])),
                        "xyz".index(cast(str, parameters["axis"])),
                    ] = -1
                    mesh.apply_transform(matrix)
                elif edit.operation == "thickness":
                    dimensions = np.asarray(mesh.extents, dtype=float)
                    axis_index = int(np.argmin(dimensions))
                    target = cast(float, parameters["value"])
                    if dimensions[axis_index] <= 0:
                        raise PhysicsModificationError("cannot thicken a zero-extent mesh")
                    factors = np.ones(3)
                    factors[axis_index] = target / dimensions[axis_index]
                    center = mesh.bounds.mean(axis=0)
                    mesh.apply_translation(-center)
                    mesh.apply_scale(factors)
                    mesh.apply_translation(center)
                elif edit.operation == "hollow":
                    if not _is_axis_aligned_box(mesh):
                        raise PhysicsModificationError(
                            "hollow currently supports only axis-aligned closed box meshes"
                        )
                    wall = cast(float, parameters["wall_thickness"])
                    inner_extent = np.asarray(mesh.extents, dtype=float) - 2 * wall
                    if np.any(inner_extent <= 0):
                        raise PhysicsModificationError("wall is too thick for this box")
                    inner = trimesh.creation.box(extents=inner_extent)
                    inner.apply_translation(mesh.bounds.mean(axis=0))
                    inner.invert()
                    mesh = trimesh.util.concatenate([mesh, inner])
                elif edit.operation == "repair":
                    before = (len(mesh.vertices), len(mesh.faces), bool(mesh.is_watertight))
                    mesh.update_faces(mesh.nondegenerate_faces())
                    mesh.remove_unreferenced_vertices()
                    mesh.merge_vertices()
                    trimesh.repair.fix_normals(mesh)
                    trimesh.repair.fill_holes(mesh)
                    after = (len(mesh.vertices), len(mesh.faces), bool(mesh.is_watertight))
                    self.repair_log.append(
                        f"{part.name}: vertices/faces/watertight {before} -> {after}; "
                        "remaining non-manifold defects may require manual repair"
                    )
                replacements[part.id] = _new_part(part, mesh)
                touched.add(part.id)
            parts = [replacements.get(part.id, part) for part in parts]
        if not parts:
            raise PhysicsModificationError("cannot export a scene with no components")
        if selected_material is not None:
            parts = [replace(part, material=_NamedMaterial(selected_material)) for part in parts]
        surviving = {part.id for part in parts}
        assemblies = tuple(
            replace(
                assembly,
                part_ids=tuple(part_id for part_id in assembly.part_ids if part_id in surviving),
            )
            for assembly in source_model.assemblies
        )
        metadata = {**source_model.metadata, "modified": True}
        invalidated_declarations = any(edit.operation != "material" for edit in self._pending)
        if invalidated_declarations:
            # Source zero-pose inertias and joint frames are not automatically
            # valid after a mesh edit. Never report stale robot properties.
            metadata.pop("declared_inertias", None)
            metadata.pop("joints", None)
        model = _model_from_parts(
            source_model.source,
            source_model.format,
            source_model.units,
            parts,
            assemblies,
            metadata,
        )
        interpret = physics_scene_from_model if len(parts) > 1 else physics_object_from_model
        density = self.source.density_kg_m3
        if selected_material is not None:
            density = lookup_material(selected_material).density_kg_m3 or density
        result = interpret(
            model,
            units=self.source.units if self.source.units != "unknown" else None,
            density_kg_m3=density,
        )
        if invalidated_declarations and source_model.format in {"urdf", "sdf"}:
            result = replace(
                result,
                limitations=(
                    *result.limitations,
                    "Source joint frames and declared inertias were invalidated by mesh editing.",
                ),
            )
        if selected_material is not None:
            # A named material is not a density or a certified mechanical grade.
            result = replace(
                result,
                material=selected_material,
                material_source="source-name",
                limitations=(
                    *result.limitations,
                    "Named material density is nominal unless an explicit grade is supplied.",
                ),
            )
        return result


def _world_mesh(part: ModelPart) -> trimesh.Trimesh:
    if part._mesh is None:
        raise PhysicsModificationError(f"{part.name}: mesh geometry is unavailable")
    mesh = cast(trimesh.Trimesh, part._mesh).copy()
    mesh.apply_transform(part.transform.matrix)
    return mesh


def _is_axis_aligned_box(mesh: trimesh.Trimesh) -> bool:
    if len(mesh.vertices) != 8 or len(mesh.faces) != 12 or not mesh.is_volume:
        return False
    center = mesh.bounds.mean(axis=0)
    half_extent = mesh.extents / 2
    return bool(
        all(
            np.allclose(np.abs(mesh.vertices[:, axis] - center[axis]), half_extent[axis])
            for axis in range(3)
        )
    )


def _new_part(template: ModelPart, mesh: trimesh.Trimesh, *, name: str | None = None) -> ModelPart:
    return replace(
        template,
        name=name or template.name,
        transform=Transform(),
        bounds=Bounds.from_points(np.asarray(mesh.bounds)),
        _mesh=mesh,
        metadata={**template.metadata, "modified": True},
    )


class PhysicsExporter:
    """Callable export namespace for a source object or a modification draft."""

    def __init__(self, source: PhysicsObject | PhysicsModification) -> None:
        self._source = source

    @property
    def _object(self) -> PhysicsObject:
        return (
            self._source.result if isinstance(self._source, PhysicsModification) else self._source
        )

    def __call__(self, path: str | Path) -> Path:
        target = Path(path)
        suffix = target.suffix.lower()
        if suffix not in {".obj", ".stl", ".ply", ".glb", ".gltf", ".urdf", ".sdf"}:
            raise PhysicsModificationError(f"unsupported export extension {suffix!r}")
        obj = self._object
        if obj.model is None:
            raise PhysicsModificationError("geometry is unavailable")
        if any(part.solid is not None for part in obj.parts):
            raise PhysicsModificationError(
                "mesh export of a CAD B-rep requires explicit CAD conversion"
            )
        if suffix in {".urdf", ".sdf"}:
            raise PhysicsModificationError(
                "robot XML export is unavailable until joint-frame and inertial "
                "round-trip validation exists"
            )
        if suffix in {".stl", ".ply"} and len(obj.parts) != 1:
            raise PhysicsModificationError(
                f"{suffix} cannot preserve multi-part names or hierarchy"
            )
        scene = trimesh.Scene()
        metres_per_unit = {
            "m": 1.0,
            "mm": 0.001,
            "cm": 0.01,
            "um": 0.000001,
            "in": 0.0254,
            "ft": 0.3048,
        }
        if suffix in {".glb", ".gltf"} and obj.units not in metres_per_unit:
            raise PhysicsModificationError(
                "glTF requires known length units; specify units when reading the source"
            )
        assemblies = {assembly.id: assembly for assembly in obj.model.assemblies}
        source_nodes = {
            part.id: assembly
            for part in obj.parts
            for assembly in obj.model.assemblies
            if assembly.id != "assembly-root"
            and part.id in assembly.part_ids
            and assembly.name == part.name
        }

        def depth(part: ModelPart) -> int:
            current = source_nodes.get(part.id)
            visited: set[str] = set()
            level = 0
            while current is not None and current.parent_id in assemblies:
                if current.id in visited:
                    raise PhysicsModificationError("source hierarchy contains a cycle")
                visited.add(current.id)
                current = assemblies[current.parent_id]
                level += 1
            return level

        for part in sorted(obj.parts, key=depth):
            if any(ord(char) < 32 for char in part.name):
                raise PhysicsModificationError(
                    "component names with control characters cannot be exported"
                )
            mesh = _world_mesh(part)
            if suffix in {".glb", ".gltf"}:
                mesh.apply_scale(metres_per_unit[obj.units])
            label = getattr(part.material, "name", None)
            if (
                isinstance(self._source, PhysicsModification)
                and any(edit.operation == "material" for edit in self._source._pending)
                and isinstance(label, str)
            ):
                # Assign visual material only to the export copy. The named
                # material is not a certified density or mechanical grade.
                mesh.visual = trimesh.visual.TextureVisuals(
                    material=trimesh.visual.material.SimpleMaterial(name=label)
                )
            source_node = source_nodes.get(part.id)
            parent = (
                assemblies[source_node.parent_id].name
                if source_node is not None and source_node.parent_id in assemblies
                else scene.graph.base_frame
            )
            if parent == part.name or parent not in {item.name for item in obj.parts}:
                parent = scene.graph.base_frame
            scene.add_geometry(
                mesh, node_name=part.name, geom_name=part.name, parent_node_name=parent
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if suffix == ".gltf":
            payload = trimesh.exchange.gltf.export_gltf(scene, embed_buffers=True)
            target.write_bytes(payload["model.gltf"])
        elif suffix == ".obj":
            output, resources = trimesh.exchange.obj.export_obj(
                scene, return_texture=True, mtl_name=f"{target.stem}.mtl"
            )
            target.write_text(output, encoding="utf-8")
            for filename, content in resources.items():
                if Path(filename).name != filename:
                    raise PhysicsModificationError("OBJ exporter returned an unsafe resource path")
                (target.parent / filename).write_bytes(content)
        elif suffix in {".stl", ".ply"}:
            data = next(iter(scene.geometry.values())).export(file_type=suffix[1:])
            target.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        else:
            data = scene.export(file_type=suffix[1:])
            target.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return target

    def to_blender(self, path: str | Path) -> Path:
        target = Path(path)
        if target.suffix.lower() != ".py":
            raise PhysicsModificationError("Blender export helper requires a .py path")
        obj = self._object
        names = [part.name for part in obj.parts]
        # A glTF sidecar, not inlined arbitrary vertex literals or executable source text.
        gltf = target.with_suffix(".gltf")
        self(gltf)
        script = (
            "import bpy\n"
            f"bpy.ops.import_scene.gltf(filepath={str(gltf)!r})\n"
            f"# Imported Reality components: {names!r}\n"
        )
        scale = {"m": 1.0, "mm": 0.001, "cm": 0.01, "um": 0.000001, "in": 0.0254, "ft": 0.3048}
        if obj.density_kg_m3 is not None and obj.units in scale:
            masses = {
                part.name: part.volume * scale[obj.units] ** 3 * obj.density_kg_m3
                for part in obj.parts
                if part.volume is not None
            }
            script += f"for _name, _mass in {masses!r}.items():\n"
            script += (
                "    _part = bpy.data.objects.get(_name)\n"
                "    if _part is not None:\n"
                "        bpy.context.view_layer.objects.active = _part\n"
                "        if _part.rigid_body is None:\n"
                "            bpy.ops.rigidbody.object_add()\n"
                "        _part.rigid_body.mass = _mass\n"
            )
        target.write_text(script, encoding="utf-8")
        return target

    def to_godot(self, path: str | Path) -> Path:
        raise PhysicsModificationError(
            "Godot RigidBody3D export needs validated collision and mass data"
        )

    def to_ros2(self, path: str | Path) -> Path:
        raise PhysicsModificationError(
            "ROS 2 export needs validated joint-frame and inertial round-trip data"
        )


def diff(original: PhysicsObject, modified: PhysicsObject | PhysicsModification) -> DiffResult:
    """Compare measured values without fabricating an engineering improvement score."""
    result = modified.result if isinstance(modified, PhysicsModification) else modified
    changes = modified.change_log if isinstance(modified, PhysicsModification) else ()
    if original.model is None or result.model is None:
        raise PhysicsModificationError("cannot diff unavailable geometry")
    if not changes:
        if original.material != result.material:
            changes = (f"Material changed: {original.material} -> {result.material}",)
        elif original.parts != result.parts:
            changes = ("Geometry or component structure changed",)
    mass_delta = (
        result.estimated_mass - original.estimated_mass
        if result.estimated_mass is not None and original.estimated_mass is not None
        else None
    )
    scale = {"m": 1.0, "mm": 0.001, "cm": 0.01, "in": 0.0254, "ft": 0.3048}
    volume_delta = (
        (result.volume - original.volume) * scale[original.units] ** 3
        if result.volume is not None and original.volume is not None and original.units in scale
        else None
    )
    weak_fixed = max(0, len(original.weak_points) - len(result.weak_points))
    return DiffResult(changes, mass_delta, volume_delta, weak_fixed, None)
