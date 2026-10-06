from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def test_obj_roundtrip_preserves_component_names_and_volume(tmp_path: Path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="left", geom_name="left")
    scene.add_geometry(trimesh.creation.box(), node_name="right", geom_name="right")
    source = tmp_path / "two.glb"
    source.write_bytes(scene.export(file_type="glb"))
    original = reality.perceive.from_3d(source)
    assert isinstance(original, reality.PhysicsScene)
    draft = original.modify.scale(2)
    output = draft.export(tmp_path / "scaled.obj")
    reopened = reality.perceive.from_3d(output, units="m")
    assert isinstance(reopened, reality.PhysicsScene)
    assert {part.name for part in reopened.parts} == {"left", "right"}
    assert reopened.volume == pytest.approx(8 * original.volume)


def test_remove_component_preserves_unmodified_mesh_identity(tmp_path: Path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="left", geom_name="left")
    scene.add_geometry(trimesh.creation.box(), node_name="right", geom_name="right")
    source = tmp_path / "two.glb"
    source.write_bytes(scene.export(file_type="glb"))
    original = reality.perceive.from_3d(source)
    draft = original.modify.remove_component("right")
    assert len(original.parts) == 2
    assert len(draft.result.parts) == 1
    kept = next(part for part in original.parts if part.name == "left")
    assert draft.result.parts[0]._mesh is kept._mesh


@pytest.mark.parametrize("suffix", ["obj", "stl", "ply", "glb", "gltf"])
def test_single_mesh_export_formats_reopen(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / "cube.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    original = reality.perceive.from_3d(source, units="m")
    target = original.modify.scale(factor=2).export(tmp_path / f"cube-scaled.{suffix}")
    reopened = reality.perceive.from_3d(
        target, units="m" if suffix in {"obj", "stl", "ply"} else None
    )
    assert reopened.volume == pytest.approx(8)


def test_glb_writeback_keeps_named_parent_child_relationship(tmp_path: Path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="Foundation", geom_name="base")
    scene.add_geometry(
        trimesh.creation.box(),
        node_name="Roof",
        parent_node_name="Foundation",
        geom_name="roof",
    )
    source = tmp_path / "building.glb"
    source.write_bytes(scene.export(file_type="glb"))
    original = reality.perceive.from_3d(source)
    target = original.modify.scale(2).export(tmp_path / "edited.glb")
    reopened = reality.perceive.from_3d(target)
    roof = next(assembly for assembly in reopened.model.assemblies if assembly.name == "Roof")
    foundation = next(
        assembly for assembly in reopened.model.assemblies if assembly.name == "Foundation"
    )
    assert roof.parent_id == foundation.id


def test_gltf_export_converts_declared_millimetres_to_metres(tmp_path: Path) -> None:
    source = tmp_path / "millimetre-cube.obj"
    source.write_text(
        trimesh.creation.box(extents=(1000, 1000, 1000)).export(file_type="obj"),
        encoding="utf-8",
    )
    original = reality.perceive.from_3d(source, units="mm")
    target = original.export(tmp_path / "cube.glb")
    reopened = reality.perceive.from_3d(target)
    assert reopened.units == "m"
    assert reopened.bounds.extents == pytest.approx((1, 1, 1))


def test_merge_components_combines_disconnected_meshes(tmp_path: Path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="left", geom_name="left")
    scene.add_geometry(
        trimesh.creation.box(),
        node_name="right",
        geom_name="right",
        transform=trimesh.transformations.translation_matrix((3, 0, 0)),
    )
    source = tmp_path / "pair.glb"
    source.write_bytes(scene.export(file_type="glb"))
    original = reality.perceive.from_3d(source)
    merged = original.modify.merge_components(["left", "right"]).result
    assert len(original.parts) == 2
    assert len(merged.parts) == 1
    assert merged.parts[0].name in {"left+right", "right+left"}
    assert merged.volume == pytest.approx(2)
