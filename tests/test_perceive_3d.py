"""Deterministic tests for the physical-object entry point."""

from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality
from reality._core.router import ModelRouter
from reality._providers.base import AITask


def _box(path: Path, extents: tuple[float, float, float] = (2.0, 2.0, 2.0)) -> Path:
    trimesh.creation.box(extents=extents).export(path)
    return path


@pytest.mark.parametrize("suffix", ["obj", "stl", "ply", "glb", "gltf"])
def test_perceive_mesh_metrics_and_units(tmp_path: Path, suffix: str) -> None:
    mesh = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    if suffix == "gltf":
        for name, contents in trimesh.Scene(mesh).export(file_type="gltf").items():
            (tmp_path / name).write_bytes(contents)
        (tmp_path / "model.gltf").replace(tmp_path / "box.gltf")
    else:
        mesh.export(tmp_path / f"box.{suffix}")
    path = tmp_path / f"box.{suffix}"
    obj = reality.perceive.from_3d(path)
    assert isinstance(obj, reality.PhysicsObject)
    assert obj.model.format == suffix
    assert obj.volume == pytest.approx(8.0)
    assert obj.surface_area == pytest.approx(24.0)
    assert obj.centre_of_mass == pytest.approx((0.0, 0.0, 0.0))
    assert obj.watertight is True
    assert obj.face_areas
    assert obj.geometry is obj.model
    assert obj.graph is obj.model.graph
    assert obj.estimated_mass is None
    assert obj.balance == "unknown"
    assert not obj.joints
    assert obj.units == ("m" if suffix in {"glb", "gltf"} else "unknown")


def test_explicit_density_and_units_produce_mass_estimate(tmp_path: Path) -> None:
    path = _box(tmp_path / "box.obj")
    obj = reality.perceive.from_3d(path, units="mm", density_kg_m3=1000)
    assert obj.source_units == "unknown"
    assert obj.units == "mm"
    assert obj.estimated_mass == pytest.approx(0.000008)
    assert obj.density_kg_m3 == 1000
    assert obj.moment_of_inertia is not None
    assert obj.moment_of_inertia[0][0] == pytest.approx(5.333333333333334e-12)
    assert obj.model.units == "unknown"  # Source evidence is retained.
    assert reality.perceive.from_3d(path, density_kg_m3=1000).estimated_mass is None


def test_part_name_material_is_labelled_heuristic(tmp_path: Path) -> None:
    path = tmp_path / "scene.glb"
    trimesh.Scene({"steel_plate": trimesh.creation.box(extents=(2, 2, 0.05))}).export(path)
    obj = reality.perceive.from_3d(path)
    assert obj.material == "steel"
    assert obj.material_source == "name-heuristic"
    assert obj.estimated_mass == pytest.approx(2 * 2 * 0.05 * 7850)
    assert len(obj.weak_points) == 1
    assert "AABB" in str(obj.weak_points[0].evidence["method"])
    assert any("guess" in warning for warning in obj.limitations)


def test_open_shell_never_gets_volume_or_mass(tmp_path: Path) -> None:
    surface = trimesh.Trimesh(
        vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]], faces=[[0, 1, 2]], process=False
    )
    path = tmp_path / "surface.ply"
    surface.export(path)
    obj = reality.perceive.from_3d(path, units="m", density_kg_m3=1000)
    assert obj.watertight is False
    assert obj.volume is None
    assert obj.estimated_mass is None
    assert obj.centre_of_mass is None


def test_unsupported_formats_fail_without_faking_geometry(tmp_path: Path) -> None:
    path = tmp_path / "model.blend"
    path.write_bytes(b"BLENDER-vfake")
    with pytest.raises(reality.ModelFileError, match="unsupported format"):
        reality.perceive.from_3d(path)


def test_reason_predict_refuses_unverified_failure_claim(tmp_path: Path) -> None:
    obj = reality.perceive.from_3d(_box(tmp_path / "box.obj"))
    result = reality.reason.predict("will this fail under 500 kg load?", obj)
    assert result.outcome == "unknown"
    assert "support" in result.reason
    assert result.objects == (obj,)
    assert result.advisory is None


def test_physics_object_reuses_existing_model_and_world_queries(tmp_path: Path) -> None:
    path = tmp_path / "two.glb"
    left = trimesh.creation.box()
    right = left.copy()
    right.apply_translation((3, 0, 0))
    trimesh.Scene({"left": left, "right": right}).export(path)
    obj = reality.perceive.from_3d(path)
    assert obj.distance("left", "right").value == pytest.approx(2)
    assert obj.clearance("left", "right").value == pytest.approx(2)
    assert len(obj.intersections()) == 1
    assert obj.measure("left").value["volume"] == pytest.approx(1)
    assert obj.world.objects[0].mesh is obj.parts[0]._mesh


class _FakeProvider:
    def complete(self, task: AITask, *, model: str) -> str:
        assert any(
            marker in task.prompt
            for marker in (
                "Measured object facts",
                "Authoritative geometry",
                "Authoritative imported geometry",
            )
        )
        assert model == "qwen3:14b"
        return "Possible concern; check material strength and supports."


def test_optional_ai_never_overwrites_geometry(tmp_path: Path) -> None:
    router = ModelRouter({"local": _FakeProvider()}, local_models=("qwen3:14b",))
    path = _box(tmp_path / "box.obj")
    obj = reality.perceive.from_3d(path, enrich=True, router=router)
    assert obj.ai_notes is not None
    assert obj.volume == pytest.approx(8)
    assert obj.estimated_mass is None
    report = reality.reason.predict("will it fail?", obj, router=router)
    assert report.outcome == "unknown"
    assert report.advisory is not None
    assert reality.copilot("what should I inspect?", obj, router=router).text


def test_step_preserves_brep_when_cad_extra_is_installed(tmp_path: Path) -> None:
    cq = pytest.importorskip("cadquery")
    path = tmp_path / "body.step"
    cq.exporters.export(cq.Workplane("XY").box(20, 20, 10).val(), str(path), "STEP")
    obj = reality.perceive.from_3d(path, density_kg_m3=7850)
    assert obj.geometry.parts[0].solid is not None
    assert obj.geometry.parts[0].faces is not None
    assert obj.source_units == "mm"
    assert obj.estimated_mass == pytest.approx(0.0314)


def test_urdf_preserves_declared_joint_and_link_hierarchy(tmp_path: Path) -> None:
    path = tmp_path / "arm.urdf"
    path.write_text(
        """<robot name="arm">
        <link name="base"><collision><geometry><box size="1 1 1"/></geometry></collision></link>
        <link name="tool"><collision><geometry><box size="0.2 0.2 1"/></geometry></collision></link>
        <joint name="shoulder" type="revolute">
          <parent link="base"/><child link="tool"/>
          <origin xyz="0 0 1" rpy="0 0 0"/><axis xyz="0 1 0"/>
        </joint></robot>""",
        encoding="utf-8",
    )
    obj = reality.perceive.from_3d(path, density_kg_m3=1000)
    assert obj.geometry.format == "urdf"
    assert [part.name for part in obj.geometry.parts] == ["base", "tool"]
    assert obj.geometry.part("tool").bounds.center[2] == pytest.approx(1)
    assert obj.joints[0].name == "shoulder"
    assert obj.joints[0].type == "revolute"
    assert obj.geometry.assemblies[1].child_ids == ("link-tool",)
    assert obj.estimated_mass == pytest.approx(1040)


def test_urdf_rejects_external_entities_and_escaping_mesh_paths(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.urdf"
    path.write_text('<!DOCTYPE robot [<!ENTITY x SYSTEM "file:///secret">]><robot/>')
    with pytest.raises(reality.ModelFileError, match="DTD"):
        reality.perceive.from_3d(path)
    path.write_text(
        '<robot><link name="x"><visual><geometry>'
        '<mesh filename="../outside.obj"/></geometry></visual></link></robot>'
    )
    with pytest.raises(reality.ModelFileError, match="escapes source directory"):
        reality.perceive.from_3d(path)
