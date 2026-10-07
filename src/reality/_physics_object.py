"""A physical interpretation of an imported model, with explicit uncertainty.

Geometry is shared with :class:`RealityModel`; this module does not copy meshes
or turn heuristic material labels into measured engineering properties.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, cast

import numpy as np
from numpy.typing import NDArray

from ._file_model import (
    ModelAssembly,
    ModelPart,
    ModelResult,
    RealityModel,
    _bounds_for_parts,
)
from ._models import Bounds, Vector3
from ._robot_model import DeclaredInertia, DeclaredJoint
from ._world import World

if TYPE_CHECKING:
    from ._physics_modify import PhysicsExporter, PhysicsModification

_METRES_PER_UNIT: Mapping[str, float] = MappingProxyType(
    {"m": 1.0, "mm": 0.001, "cm": 0.01, "um": 0.000001, "in": 0.0254, "ft": 0.3048}
)
# Nominal values are only used when a material token appears in a source name.
# They are not a substitute for a specified grade, porosity, or measured density.
_NAME_DENSITIES: Mapping[str, float] = MappingProxyType(
    {"steel": 7850.0, "aluminum": 2700.0, "aluminium": 2700.0}
)


@dataclass(frozen=True, slots=True)
class WeakPoint:
    """A screening candidate, never a stress or failure calculation."""

    part_id: str
    description: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@dataclass(frozen=True, slots=True)
class PhysicsObject:
    """Measured 3D structure plus separately labelled physical estimates.

    ``model`` retains the source meshes/B-reps, names, assemblies and Reality Graph.
    Unknown properties are ``None`` rather than invented values. Length, area,
    volume, and centre of mass use ``units``; estimated mass uses kilograms.
    """

    model: RealityModel | None
    units: str
    source_units: str
    material: str | None
    material_source: Literal["source-name", "name-heuristic", "unknown"]
    estimated_mass: float | None
    moment_of_inertia: tuple[Vector3, Vector3, Vector3] | None
    density_kg_m3: float | None
    volume: float | None
    surface_area: float | None
    centre_of_mass: Vector3 | None
    watertight: bool | None
    weak_points: tuple[WeakPoint, ...]
    joints: tuple[DeclaredJoint, ...]
    balance: Literal["stable", "unstable", "marginal", "unknown"]
    summary: str
    limitations: tuple[str, ...]
    ai_notes: str | None = None
    supported: bool = True
    install_hint: str | None = None
    blend_export_script: str | None = None
    message: str | None = None
    fast: bool = False
    mass_source: Literal["declared", "estimated", "unknown"] = "unknown"
    analysis_sample_fraction: float | None = None
    cycles_per_day: float | None = None

    @property
    def modify(self) -> PhysicsModification:
        """Start a copy-on-write edit draft; this parsed object stays unchanged."""
        from ._physics_modify import PhysicsModification

        return PhysicsModification(self)

    @property
    def export(self) -> PhysicsExporter:
        """Export the current unmodified mesh through a callable format namespace."""
        from ._physics_modify import PhysicsExporter

        return PhysicsExporter(self)

    @property
    def change_log(self) -> tuple[str, ...]:
        """An imported object has no edits; edit drafts hold their own logs."""
        return ()

    def _require_model(self) -> RealityModel:
        if self.model is None:
            raise ValueError(self.message or "Geometry is unavailable for this file")
        return self.model

    @property
    def geometry(self) -> RealityModel:
        """The original backend-neutral geometry and its source hierarchy."""
        return self._require_model()

    @property
    def graph(self) -> object:
        return self._require_model().graph

    @property
    def world(self) -> World:
        """Existing spatial World view, sharing the imported part geometry."""
        return self._require_model()._world

    @property
    def bounds(self) -> Bounds:
        return self._require_model().bounds

    @property
    def parts(self) -> tuple[ModelPart, ...]:
        return self._require_model().parts

    def measure(self, part: str | ModelPart) -> ModelResult[Mapping[str, object]]:
        return self._require_model().measure(part)

    def distance(self, first: str | ModelPart, second: str | ModelPart) -> ModelResult[float]:
        return self._require_model().distance(first, second)

    def clearance(self, first: str | ModelPart, second: str | ModelPart) -> ModelResult[float]:
        return self._require_model().clearance(first, second)

    def intersections(self) -> tuple[ModelResult[bool], ...]:
        return self._require_model().intersections()

    def contains(self, outer: str | ModelPart, inner: str | ModelPart) -> ModelResult[bool]:
        return self._require_model().contains(outer, inner)

    def topology(self, part: str | ModelPart | None = None) -> Mapping[str, object]:
        return self._require_model().topology(part)

    @property
    def center_of_mass(self) -> Vector3 | None:
        """US spelling of :attr:`centre_of_mass`."""
        return self.centre_of_mass

    @property
    def face_areas(self) -> Mapping[str, tuple[float, ...] | None]:
        """Per-triangle mesh or exact CAD-face areas, evaluated on demand.

        Mesh face areas are unavailable for non-uniformly scaled instances because
        their source triangle areas cannot be rescaled by a single factor.
        """
        result: dict[str, tuple[float, ...] | None] = {}
        for part in self._require_model().parts:
            if part.solid is not None:
                result[part.id] = tuple(float(face.Area()) for face in part.solid.Faces())
            elif part._mesh is not None and len(set(part.transform.scale)) == 1:
                scale_sq = part.transform.scale[0] ** 2
                result[part.id] = tuple(float(area * scale_sq) for area in part._mesh.area_faces)
            else:
                result[part.id] = None
        return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class SceneNode:
    """One source hierarchy node; parts are referenced by ID, not copied."""

    id: str
    name: str
    part_ids: tuple[str, ...]
    children: tuple[SceneNode, ...] = ()


@dataclass(frozen=True, slots=True)
class PhysicsScene(PhysicsObject):
    """A multi-component file with shared source geometry and an explicit tree."""

    objects: tuple[PhysicsObject, ...] = ()
    hierarchy: tuple[SceneNode, ...] = ()

    @property
    def total_mass(self) -> float | None:
        masses = [obj.estimated_mass for obj in self.objects]
        if any(mass is None for mass in masses):
            return None
        return sum(cast(float, mass) for mass in masses)


def unsupported_physics_object(
    *, message: str, install_hint: str | None = None, blend_export_script: str | None = None
) -> PhysicsObject:
    """Return an explicit absence of geometry without inventing a model."""
    return PhysicsObject(
        model=None,
        units="unknown",
        source_units="unknown",
        material=None,
        material_source="unknown",
        estimated_mass=None,
        moment_of_inertia=None,
        density_kg_m3=None,
        volume=None,
        surface_area=None,
        centre_of_mass=None,
        watertight=None,
        weak_points=(),
        joints=(),
        balance="unknown",
        summary=message,
        limitations=(message,),
        supported=False,
        install_hint=install_hint,
        blend_export_script=blend_export_script,
        message=message,
    )


def physics_scene_from_model(
    model: RealityModel,
    *,
    units: str | None = None,
    density_kg_m3: float | None = None,
    fast: bool = False,
) -> PhysicsScene:
    """Create per-component views that share all source meshes/B-reps."""
    aggregate = physics_object_from_model(
        model, units=units, density_kg_m3=density_kg_m3, fast=fast
    )
    groups: list[tuple[str, tuple[ModelPart, ...]]] = []
    if model.format in {"urdf", "sdf"}:
        for assembly in model.assemblies:
            if assembly.id == "assembly-root":
                continue
            selected = tuple(part for part in model.parts if part.id in assembly.part_ids)
            if selected:
                groups.append((assembly.name, selected))
    else:
        groups = [(part.name, (part,)) for part in model.parts]
    objects: list[PhysicsObject] = []
    for name, selected in groups:
        child_model = RealityModel(
            source=model.source,
            format=model.format,
            units=model.units,
            bounds=_bounds_for_parts(selected),
            parts=selected,
            assemblies=(
                ModelAssembly(
                    name=name, id="assembly-root", part_ids=tuple(p.id for p in selected)
                ),
            ),
            metadata={
                **model.metadata,
                "declared_inertias": {
                    link: inertia
                    for link, inertia in cast(
                        Mapping[str, DeclaredInertia], model.metadata.get("declared_inertias", {})
                    ).items()
                    if link in {str(part.metadata.get("source_link")) for part in selected}
                },
            },
            _world=model._world,
        )
        objects.append(
            physics_object_from_model(
                child_model, units=units, density_kg_m3=density_kg_m3, fast=fast
            )
        )
    assembly_by_id = {assembly.id: assembly for assembly in model.assemblies}

    def node(assembly: ModelAssembly, ancestors: frozenset[str]) -> SceneNode:
        if assembly.id in ancestors:
            raise ValueError("source assembly hierarchy contains a cycle")
        lineage = ancestors | {assembly.id}
        return SceneNode(
            id=assembly.id,
            name=assembly.name,
            part_ids=assembly.part_ids,
            children=tuple(
                node(assembly_by_id[child], lineage)
                for child in assembly.child_ids
                if child in assembly_by_id
            ),
        )

    roots = tuple(
        node(assembly, frozenset()) for assembly in model.assemblies if assembly.parent_id is None
    )
    return PhysicsScene(
        **{
            field.name: getattr(aggregate, field.name)
            for field in aggregate.__dataclass_fields__.values()
        },
        objects=tuple(objects),
        hierarchy=roots,
    )


def physics_object_from_model(
    model: RealityModel,
    *,
    units: str | None = None,
    density_kg_m3: float | None = None,
    fast: bool = False,
) -> PhysicsObject:
    """Interpret an existing parsed model without modifying or copying it."""
    if units is not None:
        if units not in _METRES_PER_UNIT:
            raise ValueError(f"unsupported declared units {units!r}")
        if model.units != "unknown" and units != model.units:
            raise ValueError(
                f"file declares {model.units!r}; use model.to_units({units!r}) to convert"
            )
    effective_units = units or model.units
    if density_kg_m3 is not None and (not isfinite(density_kg_m3) or density_kg_m3 <= 0):
        raise ValueError("density_kg_m3 must be a positive finite number")

    material, material_source = _material_from_names(model)
    density = density_kg_m3
    if density is None and material_source == "name-heuristic" and material is not None:
        density = _NAME_DENSITIES[material]

    volume_values = [None if fast else part.volume for part in model.parts]
    volume: float | None = sum(value for value in volume_values if value is not None)
    if any(value is None for value in volume_values):
        volume = None
    areas = [_sampled_area(part) if fast else part.surface_area for part in model.parts]
    area: float | None = sum(value for value in areas if value is not None)
    if any(value is None for value in areas):
        area = None

    mass = None
    mass_source: Literal["declared", "estimated", "unknown"] = "unknown"
    if volume is not None and effective_units in _METRES_PER_UNIT and density is not None:
        mass = volume * _METRES_PER_UNIT[effective_units] ** 3 * density
        mass_source = "estimated"
    inertia = (
        _mesh_inertia(model, effective_units, density) if mass is not None and not fast else None
    )

    centers = [] if fast else [part.center_of_mass for part in model.parts]
    center: Vector3 | None = None
    if volume is not None and volume > 0 and all(item is not None for item in centers):
        center = tuple(
            sum(
                float(part_center[axis]) * float(part_volume)
                for part_center, part_volume in zip(centers, volume_values, strict=True)
                if part_center is not None and part_volume is not None
            )
            / volume
            for axis in range(3)
        )  # type: ignore[assignment]

    declared = model.metadata.get("declared_inertias")
    source_links = {
        str(part.metadata.get("source_link"))
        for part in model.parts
        if part.metadata.get("source_link") is not None
    }
    if (
        isinstance(declared, Mapping)
        and source_links
        and all(isinstance(declared.get(link), DeclaredInertia) for link in source_links)
    ):
        entries = [cast(DeclaredInertia, declared[link]) for link in sorted(source_links)]
        mass = sum(entry.mass_kg for entry in entries)
        mass_source = "declared"
        center = cast(
            Vector3,
            tuple(
                sum(entry.mass_kg * entry.centre_of_mass_m[axis] for entry in entries) / mass
                for axis in range(3)
            ),
        )
        if all(entry.tensor_kg_m2 is not None for entry in entries):
            total: NDArray[np.float64] = np.zeros((3, 3), dtype=np.float64)
            for entry in entries:
                own = np.asarray(entry.tensor_kg_m2, dtype=np.float64)
                offset = np.asarray(entry.centre_of_mass_m) - np.asarray(center)
                total += own + entry.mass_kg * (
                    float(np.dot(offset, offset)) * np.eye(3) - np.outer(offset, offset)
                )
            inertia = cast(
                tuple[Vector3, Vector3, Vector3],
                tuple(tuple(float(value) for value in row) for row in total),
            )
        else:
            inertia = None

    closed = (
        ()
        if fast
        else tuple(
            bool(part.solid.Solids()) if part.solid is not None else bool(part._mesh.is_watertight)
            for part in model.parts
            if part.solid is not None or part._mesh is not None
        )
    )
    watertight = all(closed) if closed else None
    candidates = () if fast else _thin_part_candidates(model)
    limitations = [
        "Weak-point screening uses whole-part aspect ratios, not stress analysis.",
        "No support surface or load case was supplied; balance and failure cannot be verified.",
        "Undeclared joints cannot be detected reliably from arbitrary mesh geometry.",
    ]
    if inertia is None:
        limitations.append(
            "Moment of inertia needs closed mesh parts, known units and uniform density."
        )
    if effective_units == "unknown":
        limitations.append("Source units are unknown; absolute mass cannot be estimated.")
    if volume is None:
        limitations.append("At least one part lacks a valid closed volume.")
    if density is None and mass_source != "declared":
        limitations.append("No density was supplied or defensibly inferred from a part name.")
    if material_source == "name-heuristic":
        limitations.append(
            "Material and density are nominal name-based guesses, not verified facts."
        )
    elif material_source == "source-name":
        limitations.append("Source visual material name is not verified mechanical material data.")
    if fast:
        limitations.append(
            "Fast mode samples approximately 10% of mesh triangles for surface area, "
            "skips geometry-derived volume/inertia, watertightness and weak-point screening; "
            "the file is still fully parsed."
        )
    if mass_source == "declared":
        limitations.append(
            "Mass and inertial centre come from SDF declarations, not geometry estimates."
        )
    summary = (
        f"{len(model.parts)}-part {model.format.upper()} model; units: {effective_units}; "
        f"volume: {volume if volume is not None else 'unknown'}; "
        f"surface area: {area if area is not None else 'unknown'}; "
        f"mass estimate: {f'{mass:.6g} kg' if mass is not None else 'unavailable'}. "
        "No load-case or structural failure conclusion is implied."
    )
    return PhysicsObject(
        model=model,
        units=effective_units,
        source_units=model.units,
        material=material,
        material_source=material_source,
        estimated_mass=mass,
        moment_of_inertia=inertia,
        density_kg_m3=density,
        volume=volume,
        surface_area=area,
        centre_of_mass=center,
        watertight=watertight,
        weak_points=candidates,
        joints=cast(tuple[DeclaredJoint, ...], model.metadata.get("joints", ())),
        balance="unknown",
        summary=summary,
        limitations=tuple(limitations),
        fast=fast,
        mass_source=mass_source,
        analysis_sample_fraction=_sample_fraction(model) if fast else None,
    )


def _sample_fraction(model: RealityModel) -> float | None:
    counts = [len(part._mesh.faces) for part in model.parts if part._mesh is not None]
    total = sum(counts)
    if not total:
        return None
    return sum((count + 9) // 10 for count in counts) / total


def _sampled_area(part: ModelPart) -> float | None:
    if part._mesh is None or len(set(part.transform.scale)) != 1:
        return None
    faces = np.asarray(part._mesh.faces, dtype=np.int64)
    vertices = np.asarray(part._mesh.vertices, dtype=np.float64)
    if len(faces) == 0:
        return None
    sample = vertices[faces[::10]]
    vectors = np.cross(sample[:, 1] - sample[:, 0], sample[:, 2] - sample[:, 0])
    sampled_area = 0.5 * float(np.linalg.norm(vectors, axis=1).sum())
    return sampled_area * len(faces) / len(sample) * part.transform.scale[0] ** 2


def _material_from_names(
    model: RealityModel,
) -> tuple[str | None, Literal["source-name", "name-heuristic", "unknown"]]:
    # A visual PBR material is an appearance, not a mechanical material.
    labels = [getattr(part.material, "name", None) for part in model.parts]
    if (
        labels
        and all(isinstance(label, str) and label.strip() for label in labels)
        and len(set(labels)) == 1
    ):
        return cast(str, labels[0]), "source-name"
    matches_per_part = [
        {token.lower() for token in part.name.replace("-", "_").split("_")} & _NAME_DENSITIES.keys()
        for part in model.parts
    ]
    if matches_per_part and all(len(matches) == 1 for matches in matches_per_part):
        common = set.intersection(*(set(matches) for matches in matches_per_part))
        if len(common) == 1:
            return next(iter(common)), "name-heuristic"
    return None, "unknown"


def _mesh_inertia(
    model: RealityModel, units: str, density: float | None
) -> tuple[Vector3, Vector3, Vector3] | None:
    """Uniform-density inertia about aggregate COM, using SI units.

    This does not mutate the shared source meshes. CAD solids remain unsupported
    here until exact OCP mass properties have their own validated adapter.
    """
    if density is None or units not in _METRES_PER_UNIT:
        return None
    scale = _METRES_PER_UNIT[units]
    prepared: list[tuple[float, NDArray[np.float64], NDArray[np.float64]]] = []
    for part in model.parts:
        if part._mesh is None or not bool(part._mesh.is_volume):
            return None
        mesh = part._mesh.copy()
        mesh.apply_transform(part.transform.matrix)
        mesh.apply_scale(scale)
        properties = mesh.mass_properties
        volume = float(properties["volume"])
        if volume <= 0:
            return None
        prepared.append(
            (
                density * volume,
                np.asarray(properties["center_mass"], dtype=np.float64),
                density * np.asarray(properties["inertia"], dtype=np.float64),
            )
        )
    total_mass = sum(mass for mass, _, _ in prepared)
    if total_mass <= 0:
        return None
    center = sum((mass * point for mass, point, _ in prepared), np.zeros(3)) / total_mass
    matrix: NDArray[np.float64] = np.zeros((3, 3), dtype=np.float64)
    for mass, point, own_inertia in prepared:
        displacement = point - center
        matrix += own_inertia + mass * (
            np.dot(displacement, displacement) * np.eye(3) - np.outer(displacement, displacement)
        )
    if not np.all(np.isfinite(matrix)):
        return None
    return tuple(tuple(float(value) for value in row) for row in matrix)  # type: ignore[return-value]


def _thin_part_candidates(model: RealityModel) -> tuple[WeakPoint, ...]:
    found: list[WeakPoint] = []
    for part in model.parts:
        extents = part.bounds.extents
        longest = max(extents)
        if longest <= 0 or min(extents) / longest >= 0.05:
            continue
        found.append(
            WeakPoint(
                part.id,
                "Thin whole-part bounding extent; inspect the actual local wall geometry.",
                {"extents": extents, "units": model.units, "method": "AABB aspect-ratio screen"},
            )
        )
    return tuple(found)
