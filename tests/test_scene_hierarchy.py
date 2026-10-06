from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def test_nested_glb_is_a_scene_with_shared_per_mesh_objects(tmp_path: Path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="Foundation", geom_name="base")
    scene.add_geometry(
        trimesh.creation.box(),
        node_name="Roof",
        parent_node_name="Foundation",
        geom_name="roof",
    )
    path = tmp_path / "building.glb"
    path.write_bytes(scene.export(file_type="glb"))
    result = reality.perceive.from_3d(path, density_kg_m3=1000)
    assert isinstance(result, reality.PhysicsScene)
    assert len(result.objects) == 2
    assert [obj.parts[0].name for obj in result.objects] == ["Foundation", "Roof"]
    assert result.total_mass == pytest.approx(2000)
    root = result.hierarchy[0]
    assert root.children[0].name == "world"
    assert root.children[0].children[0].name == "Foundation"
    assert root.children[0].children[0].children[0].name == "Roof"
    assert result.objects[0].parts[0]._mesh is result.parts[0]._mesh
