from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def test_mesh_edit_is_transactional_and_exportable(tmp_path: Path) -> None:
    left = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    right = left.copy()
    right.apply_translation((3.0, 0.0, 0.0))
    source = tmp_path / "room.glb"
    trimesh.Scene({"left": left, "right": right}).export(source)

    base = reality.open(source)
    before = base.part("left").bounds
    session = base.edit()
    session.translate("left", x=2.0)
    assert base.part("left").bounds == before
    assert session.preview().part("left").bounds.center[0] == pytest.approx(before.center[0] + 2.0)
    session.undo().redo()
    committed = session.commit()
    assert committed.validate().valid
    assert committed.history[0].operation == "translate"

    output = tmp_path / "edited.glb"
    committed.export(str(output))
    reopened = reality.open(output)
    assert reopened.part("left").bounds.center[0] == pytest.approx(before.center[0] + 2.0)


def test_mesh_merge_and_split_use_real_trimesh_geometry(tmp_path: Path) -> None:
    first = trimesh.creation.box()
    second = first.copy()
    second.apply_translation((4.0, 0.0, 0.0))
    source = tmp_path / "two.glb"
    trimesh.Scene({"first": first, "second": second}).export(source)
    merged = reality.open(source).edit().merge(("first", "second")).commit()
    assert len(merged.model.parts) == 1
    assert merged.model.parts[0].mesh.faces.shape[0] == 24

    disconnected = trimesh.util.concatenate([first, second])
    split_source = tmp_path / "disconnected.glb"
    trimesh.Scene(disconnected).export(split_source)
    split = reality.open(split_source).edit().split("geometry_0").commit()
    assert len(split.model.parts) == 2


def test_step_hole_boolean_history_and_reopened_measurement(tmp_path: Path) -> None:
    cq = pytest.importorskip("cadquery")
    source = tmp_path / "block.step"
    cq.exporters.export(cq.Workplane("XY").box(20, 20, 10).val(), str(source), "STEP")
    base = reality.open(source)
    before = base.parts[0].volume
    edited = base.edit().hole("solid-1", radius=2.0, depth=12.0).commit()
    after = edited.model.parts[0].volume
    assert after is not None and before is not None and after < before
    assert edited.validate().valid
    assert edited.history[0].before["volume"] > edited.history[0].after["volume"]

    output = tmp_path / "block-with-hole.step"
    edited.export(str(output))
    reopened = reality.open(output)
    assert reopened.parts[0].volume == pytest.approx(after, rel=1e-5)


def test_step_offset_uses_native_brep_and_keeps_base_immutable(tmp_path: Path) -> None:
    cq = pytest.importorskip("cadquery")
    source = tmp_path / "offset-block.step"
    cq.exporters.export(cq.Workplane("XY").box(10, 10, 10).val(), str(source), "STEP")
    base = reality.open(source)
    before = base.parts[0].volume

    result = base.edit().offset("solid-1", 0.25).commit()

    assert result.model.parts[0].solid is not None
    assert result.model.parts[0].volume is not None
    assert before is not None
    assert result.model.parts[0].volume > before
    assert base.parts[0].volume == before
    assert result.history[0].operation == "offset"


def test_cad_selection_is_versioned_and_required_references_are_checked(tmp_path: Path) -> None:
    cq = pytest.importorskip("cadquery")
    source = tmp_path / "selection-block.step"
    cq.exporters.export(cq.Workplane("XY").box(4, 4, 4).val(), str(source), "STEP")
    base = reality.open(source)
    assert base.parts[0].faces and base.parts[0].edges

    session = base.edit().select_faces("solid-1", [0]).select_edges("solid-1", [0])
    assert [operation.operation for operation in session.history] == [
        "select_faces",
        "select_edges",
    ]
    assert session.preview().parts[0].solid is base.parts[0].solid
    with pytest.raises(reality.EditOperationError, match="impossible reference"):
        session.select_edges("solid-1", [100_000])
