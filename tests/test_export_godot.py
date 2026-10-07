from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_godot_writes_scene_and_importable_glb_visual(tmp_path: Path) -> None:
    path = tmp_path / "cube.obj"
    path.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    obj = reality.perceive.from_3d(path, units="m", density_kg_m3=1000)
    scene = obj.export.to_godot(tmp_path / "scene.tscn")
    text = scene.read_text(encoding="utf-8")
    assert "[gd_scene" in text
    assert 'type="RigidBody3D"' in text
    assert 'type="CollisionShape3D"' in text
    assert 'type="BoxShape3D"' in text
    assert 'type="PackedScene"' in text
    assert (tmp_path / "scene_mesh.glb").is_file()
