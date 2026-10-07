"""Conservative URDF/SDF write-back using source XML and link-local mesh sidecars."""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, cast
from xml.etree import ElementTree as ET

import numpy as np
import trimesh
from numpy.typing import NDArray

from ._file_model import ModelPart, RealityModel
from ._robot_model import _origin, _sdf_pose

if TYPE_CHECKING:
    from ._physics_object import PhysicsObject

_METRES = {"m": 1.0, "mm": 0.001, "cm": 0.01, "um": 0.000001, "in": 0.0254, "ft": 0.3048}


def _mesh(part: ModelPart, scale: float, link_inverse: NDArray[np.float64]) -> trimesh.Trimesh:
    from ._physics_modify import PhysicsModificationError

    if part._mesh is None or part.solid is not None:
        raise PhysicsModificationError("robot XML mesh write-back cannot preserve CAD B-rep")
    mesh = cast(trimesh.Trimesh, part._mesh).copy()
    mesh.apply_transform(part.transform.matrix)
    mesh.apply_scale(scale)
    mesh.apply_transform(link_inverse)
    return mesh


def _urdf_link_poses(root: ET.Element) -> dict[str, NDArray[np.float64]]:
    links = {name for node in root.findall("link") if (name := node.get("name"))}
    parents: set[str] = set()
    children: dict[str, list[tuple[str, NDArray[np.float64]]]] = {}
    for joint in root.findall("joint"):
        parent = joint.find("parent")
        child_node = joint.find("child")
        if parent is None or child_node is None:
            continue
        parent_name, child_name = parent.get("link"), child_node.get("link")
        if parent_name and child_name:
            parents.add(child_name)
            children.setdefault(parent_name, []).append(
                (child_name, _origin(joint.find("origin")).matrix)
            )
    poses = {name: np.eye(4) for name in links - parents}
    pending = list(poses)
    while pending:
        current = pending.pop()
        for child, local in children.get(current, []):
            poses[child] = poses[current] @ local
            pending.append(child)
    return poses


def _link_nodes(
    root: ET.Element, kind: str
) -> tuple[dict[str, ET.Element], dict[str, NDArray[np.float64]]]:
    if kind == "urdf":
        return (
            {cast(str, node.get("name")): node for node in root.findall("link")},
            _urdf_link_poses(root),
        )
    model = root.find("model")
    if model is None:
        model = root.find("world/model")
    if model is None:
        raise ValueError("SDF requires one model")
    model_matrix = _sdf_pose(model).matrix
    nodes = {cast(str, node.get("name")): node for node in model.findall("link")}
    return nodes, {name: model_matrix @ _sdf_pose(node).matrix for name, node in nodes.items()}


def _fmt(value: float) -> str:
    return format(float(value), ".12g")


def _inertia_values(
    mesh: trimesh.Trimesh, density: float
) -> tuple[float, NDArray[np.float64], NDArray[np.float64]]:
    from ._physics_modify import PhysicsModificationError

    if not mesh.is_volume or mesh.volume <= 0 or not isfinite(mesh.volume):
        raise PhysicsModificationError("inertia requires a closed positive-volume mesh")
    mass = float(mesh.volume * density)
    center = np.asarray(mesh.center_mass, dtype=float)
    tensor = np.asarray(mesh.moment_inertia, dtype=float) * density
    if mass <= 0 or not np.all(np.isfinite(tensor)):
        raise PhysicsModificationError("computed mass or inertia is invalid")
    return mass, center, tensor


def _density(
    obj: PhysicsObject, source: RealityModel | None, link: str, root: ET.Element | None, kind: str
) -> float | None:
    if obj.density_kg_m3 is not None:
        return obj.density_kg_m3
    if source is None or root is None or source.format != kind:
        return None
    nodes, _ = _link_nodes(root, kind)
    node = nodes.get(link)
    if node is None:
        return None
    if kind == "urdf":
        mass_text = node.find("inertial/mass")
        mass_text_value = mass_text.get("value") if mass_text is not None else None
    else:
        mass_text_value = node.findtext("inertial/mass")
    try:
        mass = float(mass_text_value) if mass_text_value is not None else None
    except ValueError:
        mass = None
    volume = sum(
        part.volume or 0.0 for part in source.parts if part.metadata.get("source_link") == link
    )
    if mass is not None and mass > 0 and volume > 0:
        # Source mass/geometry imply an effective uniform density. This is an
        # estimate, not a claim that the part has homogeneous real material.
        return mass / volume
    return None


def _set_inertial(link: ET.Element, kind: str, mesh: trimesh.Trimesh, density: float) -> None:
    mass, center, tensor = _inertia_values(mesh, density)
    inertial = link.find("inertial")
    if inertial is not None:
        link.remove(inertial)
    inertial = ET.SubElement(link, "inertial")
    if kind == "urdf":
        ET.SubElement(
            inertial, "origin", xyz=" ".join(_fmt(float(value)) for value in center), rpy="0 0 0"
        )
        ET.SubElement(inertial, "mass", value=_fmt(mass))
        ET.SubElement(
            inertial,
            "inertia",
            ixx=_fmt(tensor[0, 0]),
            ixy=_fmt(tensor[0, 1]),
            ixz=_fmt(tensor[0, 2]),
            iyy=_fmt(tensor[1, 1]),
            iyz=_fmt(tensor[1, 2]),
            izz=_fmt(tensor[2, 2]),
        )
    else:
        ET.SubElement(inertial, "pose").text = " ".join(
            _fmt(float(value)) for value in (*center, 0.0, 0.0, 0.0)
        )
        ET.SubElement(inertial, "mass").text = _fmt(mass)
        inertia = ET.SubElement(inertial, "inertia")
        for tag, value in (
            ("ixx", tensor[0, 0]),
            ("ixy", tensor[0, 1]),
            ("ixz", tensor[0, 2]),
            ("iyy", tensor[1, 1]),
            ("iyz", tensor[1, 2]),
            ("izz", tensor[2, 2]),
        ):
            ET.SubElement(inertia, tag).text = _fmt(value)


def _add_geometry(link: ET.Element, kind: str, filename: str, material: str | None) -> None:
    for role in ("collision", "visual"):
        node = ET.SubElement(link, role, name=f"reality_{role}")
        geometry = ET.SubElement(node, "geometry")
        if kind == "urdf":
            ET.SubElement(geometry, "mesh", filename=filename)
            if role == "visual" and material:
                ET.SubElement(node, "material", name=material)
        else:
            ET.SubElement(ET.SubElement(geometry, "mesh"), "uri").text = filename
            if role == "visual" and material:
                script = ET.SubElement(ET.SubElement(node, "material"), "script")
                ET.SubElement(script, "name").text = material


def _set_material(link: ET.Element, kind: str, material: str) -> None:
    if not link.findall("visual"):
        collision = link.find("collision")
        if collision is not None:
            visual = ET.SubElement(link, "visual", name="reality_visual")
            for tag in ("origin", "pose", "geometry"):
                child = collision.find(tag)
                if child is not None:
                    visual.append(deepcopy(child))
    for visual in link.findall("visual"):
        if kind == "urdf":
            node = visual.find("material")
            if node is None:
                node = ET.SubElement(visual, "material")
            node.set("name", material)
        else:
            node = visual.find("material/script/name")
            if node is None:
                material_node = visual.find("material")
                if material_node is None:
                    material_node = ET.SubElement(visual, "material")
                script = material_node.find("script")
                if script is None:
                    script = ET.SubElement(material_node, "script")
                node = ET.SubElement(script, "name")
            node.text = material


def export_robot(
    obj: PhysicsObject,
    target: Path,
    *,
    source: RealityModel | None = None,
    geometry_changed: bool = False,
    material_changed: bool = False,
) -> Path:
    """Export source-preserving XML or an explicitly generated robot conversion."""
    from ._physics_modify import PhysicsModificationError

    kind = target.suffix.lower().lstrip(".")
    if kind not in {"urdf", "sdf"}:
        raise PhysicsModificationError("robot export requires .urdf or .sdf")
    if obj.units not in _METRES:
        raise PhysicsModificationError("robot XML requires known source length units")
    scale = _METRES[obj.units]
    raw = (
        source.metadata.get("source_xml") if source is not None and source.format == kind else None
    )
    original_root = ET.fromstring(raw) if isinstance(raw, bytes) else None
    if original_root is not None:
        root = ET.fromstring(cast(bytes, raw))
    elif kind == "urdf":
        root = ET.Element("robot", name=target.stem)
        root.append(ET.Comment(" Generated by reality, not original "))
    else:
        root = ET.Element("sdf", version="1.9")
        root.append(ET.Comment(" Generated by reality, not original "))
        ET.SubElement(root, "model", name=target.stem)
    if original_root is None:
        container = root if kind == "urdf" else cast(ET.Element, root.find("model"))
        for index, part in enumerate(obj.parts):
            ET.SubElement(container, "link", name=part.name)
            if index:
                joint = ET.SubElement(
                    container, "joint", name=f"reality_fixed_{index}", type="fixed"
                )
                if kind == "urdf":
                    ET.SubElement(joint, "parent", link=obj.parts[0].name)
                    ET.SubElement(joint, "child", link=part.name)
                else:
                    ET.SubElement(joint, "parent").text = obj.parts[0].name
                    ET.SubElement(joint, "child").text = part.name
        geometry_changed = True
    links, poses = _link_nodes(root, kind)
    grouped: dict[str, list[ModelPart]] = {name: [] for name in links}
    for part in obj.parts:
        name = (
            cast(str, part.metadata.get("source_link"))
            if original_root is not None and part.metadata.get("source_link") in links
            else part.name
        )
        if name not in grouped:
            raise PhysicsModificationError(f"part {part.name!r} has no matching robot link")
        grouped[name].append(part)
    sidecars: list[tuple[Path, trimesh.Trimesh]] = []
    for index, (name, link) in enumerate(links.items(), 1):
        if material_changed and obj.material:
            _set_material(link, kind, obj.material)
        if not geometry_changed:
            continue
        for node in (*link.findall("collision"), *link.findall("visual")):
            link.remove(node)
        if not grouped[name]:
            continue
        inverse = np.linalg.inv(poses[name])
        meshes = [_mesh(part, scale, inverse) for part in grouped[name]]
        combined = trimesh.util.concatenate(meshes)
        filename = f"{target.stem}_link_{index}.obj"
        _add_geometry(link, kind, filename, obj.material if material_changed else None)
        density = _density(obj, source, name, original_root, kind)
        if density is not None:
            _set_inertial(link, kind, combined, density)
        else:
            # A conversion must not invent mass, and keeping an old inertial
            # after a geometry edit would assert invalid dynamics.
            raise PhysicsModificationError(
                f"{name}: density or source mass evidence is required for inertial write-back"
            )
        sidecars.append((target.parent / filename, combined))
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    ET.fromstring(xml)  # validate before any writes
    target.parent.mkdir(parents=True, exist_ok=True)
    for path, mesh in sidecars:
        path.write_text(mesh.export(file_type="obj"), encoding="utf-8")
    target.write_bytes(xml)
    return target
