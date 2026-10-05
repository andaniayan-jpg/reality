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


def test_blend_is_never_silently_parsed_as_geometry(tmp_path: Path) -> None:
    path = tmp_path / "model.blend"
    path.write_bytes(b"BLENDER-vfake")
    with pytest.raises(reality.BlenderConversionRequired) as caught:
        reality.perceive.from_3d(path)
    assert not caught.value.output.exists()
    caught.value.script.unlink()


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
                "Measured geometry",
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


def test_axial_yield_screen_uses_measured_area_and_explicit_strength(tmp_path: Path) -> None:
    obj = reality.perceive.from_3d(_box(tmp_path / "bar.obj"), units="m")
    inputs = {
        "load_axis": "z",
        "load_case": "axial_compression",
        "support": "opposed_face",
        "yield_source": "test fixture",
    }
    weak = reality.reason.predict(
        "will this fail under 500kg load?", obj, yield_strength_pa=1000, **inputs
    )
    assert weak.will_fail is True
    assert weak.safety_factor == pytest.approx(1000 * 4 / (500 * 9.80665))
    assert weak.failure_regions
    assert weak.confidence == "estimated"
    assert weak.evidence["sample_count"] == 19
    strong = reality.reason.predict(
        "will this fail under 500kg load?", obj, yield_strength_pa=1e6, **inputs
    )
    assert strong.will_fail is False
    assert strong.safety_factor is not None and strong.safety_factor > 1


def test_material_name_has_no_fabricated_yield_strength() -> None:
    spec = reality.material("steel")
    assert spec.density_kg_m3 == 7850
    assert spec.yield_strength_pa is None
    with pytest.raises(ValueError, match="source"):
        reality.material("steel", yield_strength_pa=2e8)


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


def test_sdf_reads_declared_links_joints_and_geometry(tmp_path: Path) -> None:
    path = tmp_path / "arm.sdf"
    path.write_text(
        """<sdf version="1.9"><model name="arm">
        <link name="base"><collision name="body"><geometry>
          <box><size>1 1 1</size></box>
        </geometry></collision></link>
        <link name="tool"><pose>0 0 2 0 0 0</pose><collision name="end">
          <geometry><box><size>0.2 0.2 1</size></box></geometry>
        </collision></link>
        <joint name="hinge" type="revolute"><parent>base</parent><child>tool</child>
          <axis><xyz>0 1 0</xyz></axis>
        </joint></model></sdf>""",
        encoding="utf-8",
    )
    obj = reality.perceive.from_3d(path)
    assert obj.model.format == "sdf"
    assert obj.units == "m"
    assert obj.model.part("tool").bounds.center[2] == pytest.approx(2)
    assert obj.joints[0].name == "hinge"
    assert obj.joints[0].axis == (0, 1, 0)
    assert obj.model.assemblies[1].child_ids == ("link-tool",)


def test_sdf_rejects_unresolved_relative_frame(tmp_path: Path) -> None:
    path = tmp_path / "frames.sdf"
    path.write_text(
        '<sdf version="1.9"><model name="m"><link name="x">'
        '<pose relative_to="other">0 0 0 0 0 0</pose>'
        '<collision name="c"><geometry><box><size>1 1 1</size></box>'
        "</geometry></collision></link></model></sdf>"
    )
    with pytest.raises(reality.ModelFileError, match="relative_to"):
        reality.perceive.from_3d(path)


def test_iges_keeps_solid_brep_with_unknown_source_units(tmp_path: Path) -> None:
    cq = pytest.importorskip("cadquery")
    from OCP.IGESControl import IGESControl_Writer

    path = tmp_path / "body.iges"
    writer = IGESControl_Writer()
    writer.AddShape(cq.Workplane("XY").box(20, 20, 10).val().wrapped)
    assert writer.Write(str(path))
    obj = reality.perceive.from_3d(path)
    assert obj.model.format == "iges"
    assert obj.model.parts[0].solid is not None
    assert obj.model.parts[0].faces is not None
    assert obj.source_units == "unknown"
    assert obj.estimated_mass is None
    if not any(part.volume is not None for part in obj.parts):
        assert obj.watertight is False


@pytest.mark.parametrize("suffix", ["usda", "usdc", "usd"])
def test_usd_reads_real_stage_mesh_and_hierarchy(tmp_path: Path, suffix: str) -> None:
    pytest.importorskip("pxr")
    from pxr import Gf, Usd, UsdGeom

    path = tmp_path / f"scene.{suffix}"
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/Assembly")
    cube = trimesh.creation.box(extents=(2, 2, 2))
    mesh = UsdGeom.Mesh.Define(stage, "/Assembly/Body")
    mesh.GetPointsAttr().Set([Gf.Vec3f(*map(float, vertex)) for vertex in cube.vertices])
    mesh.GetFaceVertexCountsAttr().Set([3] * len(cube.faces))
    mesh.GetFaceVertexIndicesAttr().Set([int(index) for index in cube.faces.ravel()])
    stage.GetRootLayer().Save()
    del stage

    obj = reality.perceive.from_3d(path, density_kg_m3=1000)
    assert obj.model.format == suffix
    assert obj.volume == pytest.approx(8)
    assert obj.estimated_mass == pytest.approx(8000)
    assert obj.model.parts[0].name == "Body"
    assert obj.model.assemblies[1].name == "Assembly"
    assert obj.model.assemblies[1].part_ids == ("part-1",)


def test_blend_requires_reviewed_manual_export(tmp_path: Path) -> None:
    path = tmp_path / "scene.blend"
    path.write_bytes(b"BLENDER-v2-test")
    with pytest.raises(reality.BlenderConversionRequired) as caught:
        reality.perceive.from_3d(path)
    instruction = caught.value
    assert instruction.source == path
    assert instruction.output == tmp_path / "scene-reality.obj"
    assert "--disable-autoexec" in instruction.command
    assert "bpy.ops.wm.obj_export" in instruction.script.read_text(encoding="utf-8")
    instruction.script.unlink()


def test_assimp_obj_conversion_rejects_nontriangular_faces() -> None:
    from types import SimpleNamespace

    from reality._assimp_model import _obj_mesh

    cube = trimesh.creation.box()
    converted = _obj_mesh(SimpleNamespace(vertices=cube.vertices, faces=cube.faces))
    assert converted.is_watertight
    assert converted.volume == pytest.approx(1)
    bad = SimpleNamespace(vertices=cube.vertices, faces=[[0, 1, 2, 3]])
    with pytest.raises(reality.ModelFileError, match="non-triangular"):
        _obj_mesh(bad)


def test_assimp_dependency_failure_is_actionable(tmp_path: Path) -> None:
    path = tmp_path / "model.fbx"
    path.write_bytes(b"not a valid FBX file")
    with pytest.raises(reality.ModelFileError) as caught:
        reality.perceive.from_3d(path)
    assert "native libassimp" in str(caught.value) or "could not parse" in str(caught.value)
