from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def test_scale_is_lazy_and_volume_scales_cubically(tmp_path: Path) -> None:
    source = tmp_path / "cube.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    original = reality.perceive.from_3d(source, units="m", density_kg_m3=1000)
    mesh = original.parts[0]._mesh
    original_vertices = mesh.vertices.copy()
    draft = original.modify.scale(factor=2).translate(x=1)
    assert original.volume == pytest.approx(1)
    assert draft.result.volume == pytest.approx(8)
    assert draft.result.bounds.center[0] == pytest.approx(1)
    assert (mesh.vertices == original_vertices).all()
    assert draft.result.parts[0]._mesh is not mesh


def test_nonuniform_scale_changes_volume(tmp_path: Path) -> None:
    source = tmp_path / "cube.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    original = reality.perceive.from_3d(source, units="m")
    assert original.modify.scale(x=1, y=2, z=3).result.volume == pytest.approx(6)


def test_chained_edits_copy_source_mesh_once_at_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "cube.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    original = reality.perceive.from_3d(source, units="m")
    original_mesh = original.parts[0]._mesh
    original_copy = trimesh.Trimesh.copy
    copies = 0

    def counted_copy(mesh: trimesh.Trimesh, *args: object, **kwargs: object) -> trimesh.Trimesh:
        nonlocal copies
        if mesh is original_mesh:
            copies += 1
        return original_copy(mesh, *args, **kwargs)

    monkeypatch.setattr(trimesh.Trimesh, "copy", counted_copy)
    draft = original.modify.scale(2).translate(x=1).rotate(axis="z", degrees=30)
    assert copies == 0
    assert draft.result.volume == pytest.approx(8)
    assert copies == 1
