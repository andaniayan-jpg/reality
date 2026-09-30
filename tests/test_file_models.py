from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh

import reality


def _cube_assets(directory: Path) -> tuple[Path, Path, Path, Path, Path]:
    cube = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    obj = directory / "cube.obj"
    stl = directory / "cube.stl"
    glb = directory / "cube.glb"
    ply = directory / "cube.ply"
    gltf = directory / "cube.gltf"
    cube.export(obj)
    cube.export(stl)
    trimesh.Scene(cube).export(glb)
    cube.export(ply)
    for name, data in trimesh.Scene(cube).export(file_type="gltf").items():
        (directory / name).write_bytes(data)
    (directory / "model.gltf").replace(gltf)
    return obj, stl, glb, ply, gltf


def test_open_mesh_formats_and_inspect_deterministically(tmp_path: Path) -> None:
    obj, stl, glb, ply, gltf = _cube_assets(tmp_path)

    for path, expected_format in (
        (obj, "obj"),
        (stl, "stl"),
        (ply, "ply"),
        (glb, "glb"),
        (gltf, "gltf"),
    ):
        model = reality.open(path)
        assert model.format == expected_format
        assert len(model.parts) == 1
        assert model.statistics()["mesh_parts"] == 1
        assert model.validate().valid
        assert model.measure(model.parts[0]).value["surface_area"] == pytest.approx(24.0)

    assert reality.open(obj).units == "unknown"
    assert reality.open(glb).units == "m"


def test_mesh_queries_graph_and_conversion(tmp_path: Path) -> None:
    left = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    right = left.copy()
    right.apply_translation((3.0, 0.0, 0.0))
    source = tmp_path / "two.glb"
    trimesh.Scene({"left": left, "right": right}).export(source)

    model = reality.open(source)
    assert model.assemblies[0].part_ids == tuple(part.id for part in model.parts)
    assert model.distance("left", "right").value == pytest.approx(2.0)
    assert model.clearance("left", "right").evidence["approximation"] == "AABB"
    assert model.nearest("left")[0].objects[1].name == "right"
    assert model.graph.predicate_count > 0

    stl = model.export(tmp_path / "two.stl")
    assert reality.open(stl).format == "stl"
    converted = model.to_units("mm")
    assert converted.bounds.extents[0] == pytest.approx(model.bounds.extents[0] * 1000)


def test_file_safety_rejects_bad_magic_and_size(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.glb"
    malformed.write_bytes(b"not-a-glb")
    with pytest.raises(reality.ModelFileError, match="magic"):
        reality.open(malformed)
    with pytest.raises(reality.ModelFileError, match="exceeds safety"):
        reality.open(malformed, max_bytes=1)

    unsafe_gltf = tmp_path / "unsafe.gltf"
    unsafe_gltf.write_text(
        json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "../outside.bin"}]}),
        encoding="utf-8",
    )
    with pytest.raises(reality.ModelFileError, match="not permitted"):
        reality.open(unsafe_gltf)


def test_step_preserves_brep_topology_units_and_exports(tmp_path: Path) -> None:
    cq = pytest.importorskip("cadquery")
    body = (
        cq.Workplane("XY")
        .box(20.0, 20.0, 10.0)
        .cut(cq.Workplane("XY").workplane(offset=-5.0).cylinder(10.0, 5.0))
        .val()
    )
    second = cq.Workplane("XY").transformed(offset=(35.0, 0.0, 0.0)).cylinder(4.0, 12.0).val()
    source = tmp_path / "assembly.step"
    cq.exporters.export(cq.Compound.makeCompound([body, second]), str(source), "STEP")

    model = reality.open(source)
    assert model.format == "step"
    assert model.units == "mm"
    assert model.metadata["brep_preserved"] is True
    assert len(model.parts) >= 2
    hole_part = max(model.parts, key=lambda part: len(part.faces or ()))
    assert hole_part.solid is not None
    assert hole_part.faces is not None and len(hole_part.faces) > 6
    assert hole_part.edges is not None
    assert hole_part.topology() is not None
    assert model.mass_properties().value["volume"] is not None

    with pytest.warns(UserWarning, match="CAD-to-mesh"):
        glb = model.export(tmp_path / "assembly.glb")
    assert reality.open(glb).format == "glb"
    step = model.export(tmp_path / "assembly-copy.step")
    assert reality.open(step).format == "step"
    stp = tmp_path / "assembly-copy.stp"
    stp.write_bytes(step.read_bytes())
    assert reality.open(stp).format == "stp"


def test_parser_hook_reports_parser_lifecycle(tmp_path: Path) -> None:
    obj, _, _, _, _ = _cube_assets(tmp_path)
    events: list[str] = []
    reality.open(obj, parser_hook=lambda _path, stage: events.append(stage))
    assert events == ["before", "after"]


def test_mesh_to_step_is_refused(tmp_path: Path) -> None:
    obj, _, _, _, _ = _cube_assets(tmp_path)
    with pytest.raises(reality.ModelFileError, match="Mesh-to-STEP"):
        reality.open(obj).export(tmp_path / "fabricated.step")
