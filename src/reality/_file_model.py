"""Safe, backend-neutral inspection of mesh and CAD files.

This module deliberately keeps imported geometry owned by its source backend.
Meshes are represented by Trimesh objects; STEP solids remain OpenCascade
shapes.  ``RealityModel`` provides the common public vocabulary without
pretending that a mesh has exact CAD topology or that a CAD solid is a mesh.
"""

from __future__ import annotations

import json
import re
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeAlias, TypeVar, cast

import numpy as np
import trimesh

from ._models import Bounds, Transform, Vector3, WorldObject
from ._world import World

if TYPE_CHECKING:
    from ._editing import EditSession

ModelFormat: TypeAlias = Literal["obj", "stl", "ply", "glb", "gltf", "step", "stp"]
_MESH_FORMATS = frozenset({"obj", "stl", "ply", "glb", "gltf"})
_CAD_FORMATS = frozenset({"step", "stp"})
_UNIT_FACTORS: Mapping[str, float] = MappingProxyType(
    {"m": 1.0, "mm": 0.001, "cm": 0.01, "um": 0.000001, "in": 0.0254, "ft": 0.3048}
)
T = TypeVar("T")


class ModelFileError(ValueError):
    """Raised for malformed, unsafe, or unsupported 3D/CAD input."""


class CADBackendUnavailableError(ImportError):
    """Raised when a STEP/STP file needs the optional CadQuery/OCP backend."""


@dataclass(frozen=True, slots=True)
class ModelResult(Generic[T]):
    """Typed result returned by deterministic model inspection operations."""

    value: T
    measurement: float | None
    units: str
    tolerance: float
    backend: str
    reason: str
    objects: tuple[ModelPart, ...]
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    @property
    def distance(self) -> float | None:
        return self.measurement


@dataclass(frozen=True, slots=True)
class ModelValidation:
    valid: bool
    format: str
    backend: str
    warnings: tuple[str, ...]
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@dataclass(frozen=True, slots=True)
class ModelAssembly:
    """A source assembly node. Names are source names where provided."""

    name: str
    id: str
    part_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    parent_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ModelPart:
    """One source part with either mesh data, a B-rep solid, or both.

    CAD ``solid`` is intentionally opaque and backend-owned. Accessing
    ``mesh`` lazily tessellates a CAD solid only when a mesh representation is
    explicitly requested.
    """

    name: str
    id: str
    transform: Transform
    bounds: Bounds
    material: object | None = None
    _mesh: Any = field(default=None, repr=False, compare=False)
    solid: Any = field(default=None, repr=False, compare=False)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def mesh(self) -> Any:
        if self._mesh is not None:
            return self._mesh
        if self.solid is None:
            return None
        # CadQuery tessellation is a view for interoperability, never the CAD source.
        vertices, triangles = self.solid.tessellate(0.1)
        return trimesh.Trimesh(
            vertices=np.asarray([vertex.toTuple() for vertex in vertices]),
            faces=np.asarray(triangles),
            process=False,
        )

    @property
    def volume(self) -> float | None:
        if self.solid is not None:
            return float(self.solid.Volume())
        if self._mesh is not None and bool(getattr(self._mesh, "is_volume", False)):
            return float(abs(self._mesh.volume) * abs(np.prod(self.transform.scale)))
        return None

    @property
    def surface_area(self) -> float | None:
        if self.solid is not None:
            return float(self.solid.Area())
        if self._mesh is not None:
            # A non-uniform transform invalidates simple area scaling.
            if len(set(self.transform.scale)) == 1:
                return float(self._mesh.area * self.transform.scale[0] ** 2)
            return None
        return None

    @property
    def center_of_mass(self) -> Vector3 | None:
        if self.solid is not None:
            center = self.solid.Center().toTuple()
            return tuple(float(value) for value in center)  # type: ignore[return-value]
        if self._mesh is not None and bool(getattr(self._mesh, "is_volume", False)):
            center = self.transform.apply(
                cast(Vector3, tuple(float(value) for value in self._mesh.center_mass))
            )
            return center
        return None

    @property
    def faces(self) -> tuple[Any, ...] | None:
        return tuple(self.solid.Faces()) if self.solid is not None else None

    @property
    def edges(self) -> tuple[Any, ...] | None:
        return tuple(self.solid.Edges()) if self.solid is not None else None

    @property
    def vertices(self) -> tuple[Any, ...] | None:
        return tuple(self.solid.Vertices()) if self.solid is not None else None

    @property
    def solids(self) -> tuple[Any, ...] | None:
        return tuple(self.solid.Solids()) if self.solid is not None else None

    @property
    def shells(self) -> tuple[Any, ...] | None:
        return tuple(self.solid.Shells()) if self.solid is not None else None

    def topology(self) -> Mapping[str, int] | None:
        if self.solid is None:
            return None
        return MappingProxyType(
            {
                "faces": len(self.solid.Faces()),
                "edges": len(self.solid.Edges()),
                "vertices": len(self.solid.Vertices()),
                "solids": len(self.solid.Solids()),
                "shells": len(self.solid.Shells()),
            }
        )


@dataclass(frozen=True, slots=True)
class RealityModel:
    """A backend-neutral model imported from a real 3D or CAD file."""

    format: ModelFormat
    units: str
    bounds: Bounds
    parts: tuple[ModelPart, ...]
    assemblies: tuple[ModelAssembly, ...]
    metadata: Mapping[str, object]
    source: Path
    _world: World = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def graph(self) -> object:
        """The existing dependency-aware Reality Graph over the imported parts."""
        return self._world.graph

    def part(self, reference: str | ModelPart) -> ModelPart:
        if isinstance(reference, ModelPart):
            return reference
        matches = [part for part in self.parts if part.id == reference or part.name == reference]
        if len(matches) != 1:
            raise LookupError(f"part reference {reference!r} resolved to {len(matches)} parts")
        return matches[0]

    def edit(self) -> EditSession:
        """Start an isolated copy-on-write editing transaction for this model."""
        from ._editing import EditSession

        return EditSession(self)

    def summary(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "format": self.format,
                "units": self.units,
                "part_count": len(self.parts),
                "assembly_count": len(self.assemblies),
                "bounds": self.bounds,
                "source": str(self.source),
                "backend": self.metadata.get("backend"),
            }
        )

    def statistics(self) -> Mapping[str, object]:
        topology = self.topology()
        return MappingProxyType(
            {
                **self.summary(),
                "mesh_parts": sum(part._mesh is not None for part in self.parts),
                "cad_parts": sum(part.solid is not None for part in self.parts),
                "topology": topology,
            }
        )

    def validate(self) -> ModelValidation:
        warnings_found: list[str] = []
        if self.units == "unknown":
            warnings_found.append("Source format did not declare linear units.")
        for part in self.parts:
            if part._mesh is not None and not bool(part._mesh.is_watertight):
                warnings_found.append(
                    f"{part.name}: mesh is not watertight; volume is unavailable."
                )
        return ModelValidation(
            valid=True,
            format=self.format,
            backend=str(self.metadata["backend"]),
            warnings=tuple(warnings_found),
            evidence={"part_count": len(self.parts), "source": str(self.source)},
        )

    def measure(self, reference: str | ModelPart) -> ModelResult[Mapping[str, object]]:
        part = self.part(reference)
        values: dict[str, object] = {
            "bounds": part.bounds,
            "extents": part.bounds.extents,
            "volume": part.volume,
            "surface_area": part.surface_area,
            "center_of_mass": part.center_of_mass,
        }
        return self._result(values, (part,), "Measured source geometry without semantic inference.")

    def distance(self, first: str | ModelPart, second: str | ModelPart) -> ModelResult[float]:
        a, b = self.part(first), self.part(second)
        distance = a.bounds.distance_to(b.bounds)
        return self._result(
            distance,
            (a, b),
            "Euclidean separation between part axis-aligned bounds.",
            measurement=distance,
            evidence={"approximation": "AABB"},
        )

    def clearance(self, first: str | ModelPart, second: str | ModelPart) -> ModelResult[float]:
        result = self.distance(first, second)
        return replace(result, reason="Non-negative AABB clearance between parts.")

    def intersections(self) -> tuple[ModelResult[bool], ...]:
        result: list[ModelResult[bool]] = []
        for index, first in enumerate(self.parts):
            for second in self.parts[index + 1 :]:
                intersects = first.bounds.intersects(second.bounds)
                result.append(
                    self._result(
                        intersects,
                        (first, second),
                        "Part AABBs overlap or touch."
                        if intersects
                        else "Part AABBs are disjoint.",
                        measurement=0.0 if intersects else first.bounds.distance_to(second.bounds),
                        evidence={"approximation": "AABB"},
                    )
                )
        return tuple(result)

    def contains(self, outer: str | ModelPart, inner: str | ModelPart) -> ModelResult[bool]:
        a, b = self.part(outer), self.part(inner)
        value = a.bounds.contains(b.bounds)
        return self._result(
            value,
            (a, b),
            "Containment of part axis-aligned bounds; not an exact B-rep containment proof.",
            evidence={"approximation": "AABB"},
        )

    def nearest(
        self, reference: str | ModelPart, *, limit: int = 1
    ) -> tuple[ModelResult[float], ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        part = self.part(reference)
        candidates = [self.distance(part, other) for other in self.parts if other.id != part.id]
        return tuple(sorted(candidates, key=lambda item: (item.value, item.objects[1].id))[:limit])

    def mass_properties(
        self, reference: str | ModelPart | None = None
    ) -> ModelResult[Mapping[str, object]]:
        parts = (self.part(reference),) if reference is not None else self.parts
        volume = sum(part.volume or 0.0 for part in parts)
        unavailable = tuple(part.name for part in parts if part.volume is None)
        return self._result(
            {"volume": volume if not unavailable else None, "unavailable": unavailable},
            parts,
            "Geometric volume only; material density/mass is not inferred.",
            measurement=volume if not unavailable else None,
        )

    def topology(self, reference: str | ModelPart | None = None) -> Mapping[str, object]:
        parts = (self.part(reference),) if reference is not None else self.parts
        values = {part.id: part.topology() for part in parts}
        return MappingProxyType(values)

    def to_units(self, units: str) -> RealityModel:
        if self.units == "unknown":
            raise ModelFileError(
                "Cannot convert an undeclared source unit; provide a unit explicitly first."
            )
        if units not in _UNIT_FACTORS:
            raise ValueError(
                f"unsupported target unit {units!r}; supported: {', '.join(_UNIT_FACTORS)}"
            )
        factor = _UNIT_FACTORS[self.units] / _UNIT_FACTORS[units]
        parts = tuple(_scale_part(part, factor) for part in self.parts)
        world = _world_for_parts(parts, units)
        return replace(
            self,
            units=units,
            bounds=_scale_bounds(self.bounds, factor),
            parts=parts,
            metadata={**self.metadata, "unit_conversion": {"from": self.units, "to": units}},
            _world=world,
        )

    def export(self, path: str | Path) -> Path:
        target = Path(path)
        suffix = target.suffix.lower().lstrip(".")
        if suffix not in {"glb", "stl", "step"}:
            raise ValueError("export supports .glb, .stl, and .step")
        target.parent.mkdir(parents=True, exist_ok=True)
        if suffix == "step":
            if any(part.solid is None for part in self.parts):
                raise ModelFileError(
                    "Mesh-to-STEP export is disallowed: it would fabricate B-rep semantics."
                )
            import cadquery as cq

            solids = [part.solid for part in self.parts]
            shape = solids[0] if len(solids) == 1 else cq.Compound.makeCompound(solids)
            cq.exporters.export(shape, str(target), exportType="STEP")
            return target
        if any(part.solid is not None for part in self.parts):
            warnings.warn(
                "CAD-to-mesh export tessellates B-rep solids; exact topology, assembly labels, "
                "and CAD metadata are not preserved.",
                UserWarning,
                stacklevel=2,
            )
        meshes: list[tuple[ModelPart, trimesh.Trimesh]] = []
        for part in self.parts:
            mesh = part.mesh
            if mesh is None:
                continue
            copied = mesh.copy()
            copied.apply_transform(part.transform.matrix)
            meshes.append((part, copied))
        if not meshes:
            raise ModelFileError("Model contains no mesh-exportable geometry.")
        scene = trimesh.Scene()
        for part, mesh in meshes:
            # Keep stable node names through mesh exports so a subsequent open()
            # can address edited parts by their public name.
            scene.add_geometry(mesh, node_name=part.name, geom_name=part.id)
        if suffix == "glb":
            target.write_bytes(scene.export(file_type="glb"))
        else:
            merged = trimesh.util.concatenate([mesh for _, mesh in meshes])
            target.write_bytes(merged.export(file_type="stl"))
        return target

    def _result(
        self,
        value: T,
        objects: Sequence[ModelPart],
        reason: str,
        *,
        measurement: float | None = None,
        evidence: Mapping[str, object] | None = None,
    ) -> ModelResult[T]:
        return ModelResult(
            value=value,
            measurement=measurement,
            units=self.units,
            tolerance=1e-9,
            backend=str(self.metadata["backend"]),
            reason=reason,
            objects=tuple(objects),
            evidence=evidence or {},
        )


def open_model(
    path: str | Path,
    *,
    max_bytes: int = 512 * 1024 * 1024,
    parser_hook: Callable[[Path, str], None] | None = None,
) -> RealityModel:
    """Open a trusted-data-safe mesh or STEP/STP model.

    ``parser_hook`` is invoked before and after parsing so services can enforce
    process-level timeouts/cancellation. In-process CAD parsers cannot be
    safely force-cancelled on every supported platform; isolate them in a
    worker process when a hard timeout is required.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    size = source.stat().st_size
    if size > max_bytes:
        raise ModelFileError(f"{source}: file size {size} exceeds safety limit {max_bytes}")
    suffix = source.suffix.lower().lstrip(".")
    if suffix not in _MESH_FORMATS | _CAD_FORMATS:
        raise ModelFileError(f"{source}: unsupported format .{suffix}")
    _validate_content(source, suffix)
    if parser_hook is not None:
        parser_hook(source, "before")
    try:
        model = _open_step(source, suffix) if suffix in _CAD_FORMATS else _open_mesh(source, suffix)
    except ModelFileError:
        raise
    except Exception as error:
        raise ModelFileError(
            f"{source}: parser rejected malformed {suffix.upper()} content: {error}"
        ) from error
    finally:
        if parser_hook is not None:
            parser_hook(source, "after")
    return model


def _open_mesh(source: Path, suffix: str) -> RealityModel:
    loaded = trimesh.load(source, force="scene", process=False)
    scene = loaded if isinstance(loaded, trimesh.Scene) else trimesh.Scene(loaded)
    parts: list[ModelPart] = []
    used: set[str] = set()
    for index, node_name in enumerate(scene.graph.nodes_geometry, start=1):
        matrix, geometry_name = scene.graph[node_name]
        mesh = scene.geometry[geometry_name]
        name = _unique_name(str(node_name or geometry_name or f"part-{index}"), used)
        transform = Transform.from_matrix(np.asarray(matrix, dtype=np.float64))
        bounds = Bounds.from_points(np.asarray(mesh.bounds, dtype=np.float64)).transformed(
            transform
        )
        parts.append(
            ModelPart(
                name=name,
                id=f"part-{index}",
                transform=transform,
                bounds=bounds,
                material=getattr(getattr(mesh, "visual", None), "material", None),
                _mesh=mesh,
                metadata={"source_node": str(node_name), "source_geometry": str(geometry_name)},
            )
        )
    if not parts:
        raise ModelFileError(f"{source}: contains no mesh geometry")
    units, unit_source = _mesh_units(source, suffix)
    assemblies = (
        ModelAssembly(
            name=source.stem,
            id="assembly-root",
            part_ids=tuple(part.id for part in parts),
            metadata={"name_source": "file"},
        ),
    )
    return _model_from_parts(
        source,
        suffix,
        units,
        parts,
        assemblies,
        {"backend": "trimesh", "unit_source": unit_source, "file_size": source.stat().st_size},
    )


def _open_step(source: Path, suffix: str) -> RealityModel:
    try:
        import cadquery as cq
    except ImportError as error:
        raise CADBackendUnavailableError(
            "STEP/STP support requires reality[cad] (CadQuery/OCP)."
        ) from error
    try:
        imported = cq.importers.importStep(str(source)).val()
    except Exception as error:
        raise ModelFileError(f"{source}: invalid STEP/STP payload: {error}") from error
    solids = tuple(imported.Solids())
    if not solids:
        raise ModelFileError(f"{source}: contains no transferable B-rep solids")
    units, unit_source = _step_units(source)
    parts = tuple(
        ModelPart(
            name=f"solid-{index}",
            id=f"part-{index}",
            transform=Transform(),
            bounds=_cad_bounds(solid),
            solid=solid,
            metadata={"name_source": "generated", "source_top_level_solid": index},
        )
        for index, solid in enumerate(solids, start=1)
    )
    assemblies = (
        ModelAssembly(
            name=source.stem,
            id="assembly-root",
            part_ids=tuple(part.id for part in parts),
            metadata={"name_source": "file", "hierarchy": "top-level-solids"},
        ),
    )
    return _model_from_parts(
        source,
        suffix,
        units,
        parts,
        assemblies,
        {
            "backend": "cadquery-ocp",
            "unit_source": unit_source,
            "file_size": source.stat().st_size,
            "brep_preserved": True,
        },
    )


def _model_from_parts(
    source: Path,
    format_name: str,
    units: str,
    parts: Sequence[ModelPart],
    assemblies: Sequence[ModelAssembly],
    metadata: Mapping[str, object],
) -> RealityModel:
    world = _world_for_parts(parts, units)
    return RealityModel(
        format=format_name,  # type: ignore[arg-type]
        units=units,
        bounds=_bounds_for_parts(parts),
        parts=tuple(parts),
        assemblies=tuple(assemblies),
        metadata={
            **metadata,
            "graph_materialization": "eager" if len(parts) <= 250 else "lazy",
        },
        source=source,
        _world=world,
    )


def _world_for_parts(parts: Sequence[ModelPart], units: str) -> World:
    objects = tuple(
        # The graph only needs the already world-space bounds. Keep this internal
        # mirror identity-transformed rather than attempting a lossy inverse of a
        # potentially rotated source transform.
        WorldObject(part.name, part.bounds, Transform(), id=part.id, mesh=part._mesh)
        for part in parts
    )
    # Relationship evaluation is quadratic. Keep the dependency-aware graph on
    # every imported model, but materialize edges only for normal-size scenes.
    # Large models retain graph indexes/predicate capacity and can be refreshed
    # selectively instead of turning import into an accidental all-pairs job.
    world = World(objects, units=units, build_graph=False)
    if len(parts) <= 250:
        world.graph.refresh_all()
    return world


def _bounds_for_parts(parts: Sequence[ModelPart]) -> Bounds:
    points = [corner for part in parts for corner in part.bounds.corners]
    return Bounds.from_points(np.asarray(points, dtype=np.float64))


def _cad_bounds(solid: Any) -> Bounds:
    box = solid.BoundingBox()
    return Bounds(
        (float(box.xmin), float(box.ymin), float(box.zmin)),
        (float(box.xmax), float(box.ymax), float(box.zmax)),
    )


def _scale_part(part: ModelPart, factor: float) -> ModelPart:
    transform = Transform(
        position=cast(Vector3, tuple(value * factor for value in part.transform.position)),
        rotation=part.transform.rotation,
        scale=part.transform.scale,
    )
    mesh = None
    if part._mesh is not None:
        mesh = part._mesh.copy()
        mesh.apply_scale(factor)
    solid = part.solid.scale(factor) if part.solid is not None else None
    return replace(
        part,
        transform=transform,
        bounds=_scale_bounds(part.bounds, factor),
        _mesh=mesh,
        solid=solid,
    )


def _scale_bounds(bounds: Bounds, factor: float) -> Bounds:
    return Bounds(
        cast(Vector3, tuple(value * factor for value in bounds.minimum)),
        cast(Vector3, tuple(value * factor for value in bounds.maximum)),
    )


def _mesh_units(source: Path, suffix: str) -> tuple[str, str]:
    if suffix in {"glb", "gltf"}:
        return "m", "glTF specification convention"
    return "unknown", f".{suffix} does not declare linear units"


def _step_units(source: Path) -> tuple[str, str]:
    text = source.read_text(encoding="latin-1", errors="ignore")[:2_000_000].upper()
    if re.search(r"SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)", text):
        return "mm", "STEP SI_UNIT(.MILLI.,.METRE.)"
    if re.search(r"SI_UNIT\s*\(\s*\$\s*,\s*\.METRE\.\s*\)", text):
        return "m", "STEP SI_UNIT($,.METRE.)"
    if "INCH" in text:
        return "in", "STEP conversion-based INCH unit"
    return "unknown", "No supported STEP length unit declaration found"


def _validate_content(source: Path, suffix: str) -> None:
    prefix = source.read_bytes()[:4096]
    if not prefix:
        raise ModelFileError(f"{source}: empty file")
    if suffix == "glb" and prefix[:4] != b"glTF":
        raise ModelFileError(f"{source}: .glb content is missing the glTF magic header")
    elif suffix == "gltf":
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModelFileError(f"{source}: malformed glTF JSON") from error
        if not isinstance(document, Mapping) or "asset" not in document:
            raise ModelFileError(f"{source}: glTF JSON must contain an asset object")
        for collection in (document.get("buffers"), document.get("images")):
            if not isinstance(collection, list):
                continue
            for item in collection:
                if not isinstance(item, Mapping) or not isinstance(item.get("uri"), str):
                    continue
                uri = item["uri"]
                if uri.startswith("data:"):
                    continue
                candidate = Path(uri)
                if "://" in uri or candidate.is_absolute() or ".." in candidate.parts:
                    raise ModelFileError(
                        f"{source}: external glTF URI {uri!r} is not permitted by the safety policy"
                    )
    elif suffix == "ply" and not prefix.startswith(b"ply"):
        raise ModelFileError(f"{source}: .ply content is missing the PLY magic header")
    elif suffix in _CAD_FORMATS and b"ISO-10303-21" not in prefix.upper():
        raise ModelFileError(f"{source}: STEP/STP content is missing the ISO-10303-21 header")
    elif suffix == "obj" and b"\0" in prefix:
        raise ModelFileError(f"{source}: binary data is not valid OBJ text")
    elif suffix == "stl" and len(prefix) < 84:
        raise ModelFileError(f"{source}: STL content is too short")


def _unique_name(candidate: str, used: set[str]) -> str:
    name = candidate.strip() or "part"
    result = name
    suffix = 2
    while result in used:
        result = f"{name}-{suffix}"
        suffix += 1
    used.add(result)
    return result
