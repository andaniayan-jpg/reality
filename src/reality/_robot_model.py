"""Bounded URDF import preserving declared joints and link hierarchy.

This is zero-configuration geometry only, not a dynamics or articulation
solver. External resources must be local files inside the URDF directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET

import numpy as np
import trimesh
from numpy.typing import NDArray

from ._file_model import ModelAssembly, ModelFileError, ModelPart, RealityModel, _model_from_parts
from ._models import Bounds, Transform, Vector3

_MAX_XML_BYTES = 32 * 1024 * 1024
_MESH_SUFFIXES = frozenset({".obj", ".stl", ".ply", ".glb", ".gltf"})


@dataclass(frozen=True, slots=True)
class DeclaredJoint:
    """A joint specified by the source URDF, not inferred from surface shape."""

    name: str
    type: str
    parent: str
    child: str
    axis: Vector3
    origin: Transform
    lower_limit: float | None = None
    upper_limit: float | None = None
    effort_limit: float | None = None
    velocity_limit: float | None = None


@dataclass(frozen=True, slots=True)
class DeclaredInertia:
    """SDF-provided link inertial properties in world coordinates at zero pose."""

    link: str
    mass_kg: float
    centre_of_mass_m: Vector3
    tensor_kg_m2: tuple[Vector3, Vector3, Vector3] | None


def _numbers(text: str | None, count: int, label: str) -> tuple[float, ...]:
    try:
        values = tuple(float(value) for value in (text or "").split())
    except ValueError as error:
        raise ModelFileError(f"invalid URDF {label}") from error
    if len(values) != count or not np.all(np.isfinite(values)):
        raise ModelFileError(f"URDF {label} must have {count} finite numbers")
    return values


def _origin(node: ET.Element | None) -> Transform:
    if node is None:
        return Transform()
    return Transform(
        position=cast(Vector3, _numbers(node.get("xyz", "0 0 0"), 3, "origin xyz")),
        rotation=cast(Vector3, _numbers(node.get("rpy", "0 0 0"), 3, "origin rpy")),
    )


def _child_attr(node: ET.Element, tag: str, attr: str) -> str:
    child = node.find(tag)
    value = child.get(attr) if child is not None else None
    if not value:
        raise ModelFileError(f"URDF {node.tag} requires {tag}/{attr}")
    return value


def _mesh_for_geometry(
    geometry: ET.Element, source: Path, max_bytes: int
) -> tuple[tuple[trimesh.Trimesh, Transform], ...]:
    box = geometry.find("box")
    if box is not None:
        size = _numbers(box.get("size"), 3, "box size")
        if any(value <= 0 for value in size):
            raise ModelFileError("URDF box dimensions must be positive")
        return ((trimesh.creation.box(extents=size), Transform()),)
    cylinder = geometry.find("cylinder")
    if cylinder is not None:
        radius = _numbers(cylinder.get("radius"), 1, "cylinder radius")[0]
        length = _numbers(cylinder.get("length"), 1, "cylinder length")[0]
        if radius <= 0 or length <= 0:
            raise ModelFileError("URDF cylinder dimensions must be positive")
        return (
            (trimesh.creation.cylinder(radius=radius, height=length, sections=64), Transform()),
        )
    sphere = geometry.find("sphere")
    if sphere is not None:
        radius = _numbers(sphere.get("radius"), 1, "sphere radius")[0]
        if radius <= 0:
            raise ModelFileError("URDF sphere radius must be positive")
        return ((trimesh.creation.icosphere(radius=radius, subdivisions=3), Transform()),)
    mesh_node = geometry.find("mesh")
    if mesh_node is None:
        raise ModelFileError("unsupported or missing URDF geometry")
    filename = mesh_node.get("filename")
    if not filename:
        raise ModelFileError("URDF mesh requires a filename")
    relative = Path(filename)
    if "://" in filename or relative.is_absolute():
        raise ModelFileError("URDF mesh references must be local relative paths")
    path = (source.parent / relative).resolve()
    if not path.is_relative_to(source.parent.resolve()):
        raise ModelFileError("URDF mesh path escapes source directory")
    if path.suffix.lower() not in _MESH_SUFFIXES:
        raise ModelFileError("unsupported URDF mesh format")
    from ._file_model import open_model

    model = open_model(path, max_bytes=max_bytes)
    scale_text = mesh_node.get("scale")
    scale = cast(Vector3, _numbers(scale_text, 3, "mesh scale")) if scale_text else (1.0, 1.0, 1.0)
    if any(value <= 0 for value in scale):
        raise ModelFileError("URDF mesh scale must be positive")
    return tuple(
        (part._mesh, Transform.from_matrix(np.diag((*scale, 1.0)) @ part.transform.matrix))
        for part in model.parts
        if part._mesh is not None
    )


def open_urdf(source: Path, *, max_bytes: int) -> RealityModel:
    """Import fixed-pose URDF collision geometry and explicit kinematic joints."""
    if source.stat().st_size > min(max_bytes, _MAX_XML_BYTES):
        raise ModelFileError("URDF XML exceeds safety limit")
    contents = source.read_bytes()
    if b"\0" in contents:
        raise ModelFileError("URDF XML must be UTF-8-compatible text")
    if b"<!DOCTYPE" in contents.upper() or b"<!ENTITY" in contents.upper():
        raise ModelFileError("URDF DTD and entity declarations are not permitted")
    try:
        root = ET.fromstring(contents)
    except ET.ParseError as error:
        raise ModelFileError("malformed URDF XML") from error
    if root.tag != "robot":
        raise ModelFileError("URDF root element must be <robot>")
    links = root.findall("link")
    if not links:
        raise ModelFileError("URDF contains no links")
    if len(links) > 10_000:
        raise ModelFileError("URDF exceeds the 10,000-link safety limit")
    names = [link.get("name") for link in links]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ModelFileError("URDF link names must be nonempty and unique")
    by_name = {cast(str, link.get("name")): link for link in links}
    joints: list[DeclaredJoint] = []
    parent_of: dict[str, str] = {}
    children: dict[str, list[DeclaredJoint]] = {name: [] for name in by_name}
    joint_nodes = root.findall("joint")
    if len(joint_nodes) > 10_000:
        raise ModelFileError("URDF exceeds the 10,000-joint safety limit")
    for node in joint_nodes:
        parent = _child_attr(node, "parent", "link")
        child = _child_attr(node, "child", "link")
        if parent not in by_name or child not in by_name or child in parent_of:
            raise ModelFileError("URDF joint has unknown or repeated child link")
        axis_node = node.find("axis")
        axis_text = axis_node.get("xyz", "1 0 0") if axis_node is not None else "1 0 0"
        axis = cast(Vector3, _numbers(axis_text, 3, "joint axis"))
        joint = DeclaredJoint(
            name=node.get("name") or f"{parent}-to-{child}",
            type=node.get("type") or "unknown",
            parent=parent,
            child=child,
            axis=axis,
            origin=_origin(node.find("origin")),
        )
        joints.append(joint)
        parent_of[child] = parent
        children[parent].append(joint)
    roots = [name for name in by_name if name not in parent_of]
    if not roots:
        raise ModelFileError("URDF joint graph contains a cycle")
    poses: dict[str, NDArray[np.float64]] = {}

    pending: list[tuple[str, NDArray[np.float64]]] = [
        (name, np.eye(4, dtype=np.float64)) for name in roots
    ]
    while pending:
        name, pose = pending.pop()
        if name in poses:
            raise ModelFileError("URDF joint graph contains a cycle or repeated link")
        poses[name] = pose
        for joint in children[name]:
            pending.append((joint.child, pose @ joint.origin.matrix))
    if len(poses) != len(by_name):
        raise ModelFileError("URDF joint graph is invalid")

    parts: list[ModelPart] = []
    assembly_part_ids: dict[str, list[str]] = {name: [] for name in by_name}
    for name, link in by_name.items():
        nodes = link.findall("collision") or link.findall("visual")
        for geometry_node in nodes:
            geometry = geometry_node.find("geometry")
            if geometry is None:
                raise ModelFileError("URDF collision/visual element needs geometry")
            local = _origin(geometry_node.find("origin"))
            for mesh, mesh_transform in _mesh_for_geometry(geometry, source, max_bytes):
                matrix = poses[name] @ local.matrix @ mesh_transform.matrix
                transform = Transform.from_matrix(matrix)
                part_id = f"part-{len(parts) + 1}"
                part_name = (
                    name
                    if not assembly_part_ids[name]
                    else f"{name}-{len(assembly_part_ids[name]) + 1}"
                )
                role = "collision" if link.findall("collision") else "visual"
                parts.append(
                    ModelPart(
                        name=part_name,
                        id=part_id,
                        transform=transform,
                        bounds=Bounds.from_points(np.asarray(mesh.bounds)).transformed(transform),
                        _mesh=mesh,
                        metadata={"source_link": name, "geometry_role": role},
                    )
                )
                assembly_part_ids[name].append(part_id)
    if not parts:
        raise ModelFileError("URDF contains no supported collision or visual geometry")
    assemblies = (
        ModelAssembly(
            name=root.get("name") or source.stem,
            id="assembly-root",
            child_ids=tuple(f"link-{name}" for name in roots),
        ),
        *(
            ModelAssembly(
                name=name,
                id=f"link-{name}",
                part_ids=tuple(assembly_part_ids[name]),
                child_ids=tuple(f"link-{joint.child}" for joint in children[name]),
                parent_id=f"link-{parent_of[name]}" if name in parent_of else "assembly-root",
            )
            for name in by_name
        ),
    )
    return _model_from_parts(
        source,
        "urdf",
        "m",
        parts,
        assemblies,
        {
            "backend": "urdf-xml+trimesh",
            "unit_source": "URDF SI metres convention",
            "joints": tuple(joints),
            "pose": "zero joint configuration",
            "file_size": len(contents),
            "source_xml": contents,
        },
    )


@dataclass(frozen=True, slots=True)
class _VisualMaterial:
    name: str


def _sdf_pose(element: ET.Element) -> Transform:
    node = element.find("pose")
    if node is None:
        return Transform()
    if node.get("relative_to") or node.get("degrees") == "true":
        raise ModelFileError("SDF relative_to frames and degree-valued poses need libsdformat")
    values = _numbers(node.text or "0 0 0 0 0 0", 6, "pose")
    return Transform(position=cast(Vector3, values[:3]), rotation=cast(Vector3, values[3:]))


def _sdf_optional_number(node: ET.Element, path: str) -> float | None:
    text = node.findtext(path)
    if text is None:
        return None
    return _numbers(text, 1, path)[0]


def _sdf_inertia(link: ET.Element, link_matrix: NDArray[np.float64]) -> DeclaredInertia | None:
    inertial = link.find("inertial")
    if inertial is None:
        return None
    mass = _sdf_optional_number(inertial, "mass")
    if mass is None or mass <= 0:
        raise ModelFileError("SDF inertial mass must be positive")
    world_matrix = link_matrix @ _sdf_pose(inertial).matrix
    center = cast(Vector3, tuple(float(value) for value in world_matrix[:3, 3]))
    inertia = inertial.find("inertia")
    tensor: tuple[Vector3, Vector3, Vector3] | None = None
    if inertia is not None:
        values = [
            _sdf_optional_number(inertia, label)
            for label in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")
        ]
        if any(value is None for value in values):
            raise ModelFileError("SDF inertia requires all six tensor components")
        ixx, ixy, ixz, iyy, iyz, izz = cast(
            tuple[float, float, float, float, float, float], tuple(values)
        )
        local = np.asarray(((ixx, ixy, ixz), (ixy, iyy, iyz), (ixz, iyz, izz)), dtype=float)
        if np.min(np.linalg.eigvalsh(local)) < -1e-9:
            raise ModelFileError("SDF inertia tensor must be positive semidefinite")
        rotation = world_matrix[:3, :3]
        world_tensor = rotation @ local @ rotation.T
        tensor = cast(
            tuple[Vector3, Vector3, Vector3],
            tuple(tuple(float(value) for value in row) for row in world_tensor),
        )
    return DeclaredInertia(
        link=link.get("name") or "",
        mass_kg=mass,
        centre_of_mass_m=center,
        tensor_kg_m2=tensor,
    )


def _sdf_geometry(geometry: ET.Element) -> ET.Element:
    """Translate the supported SDF primitive tags to the shared mesh reader."""
    adapted = ET.Element("geometry")
    for tag, attributes in (
        ("box", {"size": "size"}),
        ("sphere", {"radius": "radius"}),
        ("cylinder", {"radius": "radius", "length": "length"}),
        ("mesh", {"filename": "uri", "scale": "scale"}),
    ):
        shape = geometry.find(tag)
        if shape is None:
            continue
        child = ET.SubElement(adapted, tag)
        for target, source in attributes.items():
            value = shape.findtext(source)
            if value is not None:
                child.set(target, value.strip())
        return adapted
    raise ModelFileError("unsupported SDF geometry; box, sphere, cylinder or local mesh required")


def open_sdf(source: Path, *, max_bytes: int) -> RealityModel:
    """Read a single simple SDF model at its declared zero configuration.

    Full SDF frame graphs, includes, plugins and dynamics require libsdformat;
    this reader rejects those constructs instead of silently misplacing parts.
    """
    if source.stat().st_size > min(max_bytes, _MAX_XML_BYTES):
        raise ModelFileError("SDF XML exceeds safety limit")
    contents = source.read_bytes()
    if b"\0" in contents or b"<!DOCTYPE" in contents.upper() or b"<!ENTITY" in contents.upper():
        raise ModelFileError("SDF XML must be UTF-8-compatible text without DTD/entities")
    try:
        root = ET.fromstring(contents)
    except ET.ParseError as error:
        raise ModelFileError("malformed SDF XML") from error
    if root.tag != "sdf":
        raise ModelFileError("SDF root element must be <sdf>")
    models = root.findall("model") + root.findall("world/model")
    if len(models) != 1:
        raise ModelFileError("SDF reader requires exactly one top-level model")
    model = models[0]
    if any(model.findall(tag) for tag in ("include", "model", "frame", "plugin")):
        raise ModelFileError("nested SDF models, includes, frames and plugins are unsupported")
    links = model.findall("link")
    if not links or len(links) > 10_000:
        raise ModelFileError("SDF model must contain 1–10,000 direct links")
    names = [link.get("name") for link in links]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ModelFileError("SDF link names must be nonempty and unique")
    by_name = {cast(str, link.get("name")): link for link in links}
    model_pose = _sdf_pose(model)
    joints: list[DeclaredJoint] = []
    parent_of: dict[str, str] = {}
    children: dict[str, list[str]] = {name: [] for name in by_name}
    for node in model.findall("joint"):
        parent = (node.findtext("parent") or "").strip()
        child = (node.findtext("child") or "").strip()
        if parent not in by_name or child not in by_name or child in parent_of:
            raise ModelFileError("SDF joint has unknown or repeated child link")
        axis_node = node.find("axis/xyz")
        if axis_node is not None and axis_node.get("expressed_in"):
            raise ModelFileError("SDF joint axis expressed_in requires frame resolution")
        axis_text = axis_node.text if axis_node is not None else "0 0 1"
        joints.append(
            DeclaredJoint(
                name=node.get("name") or f"{parent}-to-{child}",
                type=node.get("type") or "unknown",
                parent=parent,
                child=child,
                axis=cast(Vector3, _numbers(axis_text, 3, "joint axis")),
                origin=_sdf_pose(node),
                lower_limit=_sdf_optional_number(node, "axis/limit/lower"),
                upper_limit=_sdf_optional_number(node, "axis/limit/upper"),
                effort_limit=_sdf_optional_number(node, "axis/limit/effort"),
                velocity_limit=_sdf_optional_number(node, "axis/limit/velocity"),
            )
        )
        parent_of[child] = parent
        children[parent].append(child)
    for name in by_name:
        lineage: set[str] = set()
        current = name
        while current in parent_of:
            if current in lineage:
                raise ModelFileError("SDF joint hierarchy contains a cycle")
            lineage.add(current)
            current = parent_of[current]
    parts: list[ModelPart] = []
    part_ids: dict[str, list[str]] = {name: [] for name in by_name}
    declared_inertias: dict[str, DeclaredInertia] = {}
    for name, link in by_name.items():
        link_matrix = model_pose.matrix @ _sdf_pose(link).matrix
        inertial = _sdf_inertia(link, link_matrix)
        if inertial is not None:
            declared_inertias[name] = inertial
        visual = link.find("visual/material/script/name")
        visual_material = (
            _VisualMaterial(visual.text.strip()) if visual is not None and visual.text else None
        )
        nodes = link.findall("collision") or link.findall("visual")
        for node in nodes:
            geometry = node.find("geometry")
            if geometry is None:
                raise ModelFileError("SDF collision/visual element needs geometry")
            for mesh, mesh_transform in _mesh_for_geometry(
                _sdf_geometry(geometry), source, max_bytes
            ):
                transform = Transform.from_matrix(
                    link_matrix @ _sdf_pose(node).matrix @ mesh_transform.matrix
                )
                part_id = f"part-{len(parts) + 1}"
                part_name = name if not part_ids[name] else f"{name}-{len(part_ids[name]) + 1}"
                parts.append(
                    ModelPart(
                        name=part_name,
                        id=part_id,
                        transform=transform,
                        bounds=Bounds.from_points(np.asarray(mesh.bounds)).transformed(transform),
                        material=visual_material,
                        _mesh=mesh,
                        metadata={"source_link": name, "geometry_role": node.tag},
                    )
                )
                part_ids[name].append(part_id)
    if not parts:
        raise ModelFileError("SDF contains no supported collision or visual geometry")
    roots = [name for name in by_name if name not in parent_of]
    assemblies = (
        ModelAssembly(
            name=model.get("name") or source.stem,
            id="assembly-root",
            child_ids=tuple(f"link-{name}" for name in roots),
        ),
        *(
            ModelAssembly(
                name=name,
                id=f"link-{name}",
                part_ids=tuple(part_ids[name]),
                child_ids=tuple(f"link-{child}" for child in children[name]),
                parent_id=f"link-{parent_of[name]}" if name in parent_of else "assembly-root",
            )
            for name in by_name
        ),
    )
    return _model_from_parts(
        source,
        "sdf",
        "m",
        parts,
        assemblies,
        {
            "backend": "sdf-xml+trimesh",
            "unit_source": "SDF SI metres convention",
            "joints": tuple(joints),
            "declared_inertias": declared_inertias,
            "pose": "declared zero configuration",
            "file_size": len(contents),
            "source_xml": contents,
        },
    )
