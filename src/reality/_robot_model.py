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
        },
    )
