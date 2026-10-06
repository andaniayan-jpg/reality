from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def _source(tmp_path: Path) -> reality.PhysicsObject:
    path = tmp_path / "cube.obj"
    path.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    return reality.perceive.from_3d(path, units="m", density_kg_m3=1000)


def test_mirror_keeps_closed_positive_volume(tmp_path: Path) -> None:
    source = _source(tmp_path)
    mirrored = source.modify.mirror(axis="x").result
    assert mirrored.volume == pytest.approx(source.volume)
    assert mirrored.watertight is True


def test_repair_log_reports_observed_changes(tmp_path: Path) -> None:
    source = _source(tmp_path)
    draft = source.modify.repair()
    assert not draft.repair_log  # deferred until materialization
    assert draft.result.watertight is True
    assert draft.repair_log


def test_box_hollow_is_measured_and_other_semantic_exports_are_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    hollowed = source.modify.hollow(wall_thickness=0.02).result
    assert hollowed.volume == pytest.approx(1 - 0.96**3)
    assert hollowed.watertight is True
    with pytest.raises(reality.PhysicsModificationError, match="robot XML"):
        source.export(tmp_path / "out.urdf")
    with pytest.raises(reality.PhysicsModificationError, match="Godot"):
        source.export.to_godot(tmp_path / "out.tscn")


def test_hollow_rejects_unsupported_non_box_mesh(tmp_path: Path) -> None:
    path = tmp_path / "sphere.obj"
    path.write_text(trimesh.creation.icosphere().export(file_type="obj"), encoding="utf-8")
    source = reality.perceive.from_3d(path, units="m")
    with pytest.raises(reality.PhysicsModificationError, match="box meshes"):
        _ = source.modify.hollow(wall_thickness=0.02).result


def test_material_name_survives_obj_roundtrip(tmp_path: Path) -> None:
    source = _source(tmp_path)
    path = source.modify.material("steel").export(tmp_path / "steel.obj")
    assert path.with_suffix(".mtl").is_file()
    reopened = reality.perceive.from_3d(path, units="m")
    assert reopened.material == "steel"


def test_unmeasured_improvement_is_not_fabricated(tmp_path: Path) -> None:
    source = _source(tmp_path)
    draft = source.modify.optimize_for("earthquake_safe")
    assert not draft.change_log
    assert draft.optimization_log
    assert reality.diff(source, draft).improvement_score is None


def test_robot_declared_mass_is_invalidated_after_geometry_edit(tmp_path: Path) -> None:
    source = tmp_path / "robot.sdf"
    source.write_text(
        '<sdf version="1.9"><model name="robot"><link name="body">'
        "<inertial><mass>2</mass><inertia><ixx>1</ixx><ixy>0</ixy><ixz>0</ixz>"
        "<iyy>1</iyy><iyz>0</iyz><izz>1</izz></inertia></inertial>"
        '<collision name="shape"><geometry><box><size>1 1 1</size></box>'
        "</geometry></collision></link></model></sdf>",
        encoding="utf-8",
    )
    original = reality.perceive.from_3d(source)
    assert original.estimated_mass == pytest.approx(2)
    modified = original.modify.scale(factor=2).result
    assert modified.estimated_mass is None
    assert modified.mass_source == "unknown"
    assert original.estimated_mass == pytest.approx(2)
