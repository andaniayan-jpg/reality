from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_blender_helper_exports_scene_and_script(tmp_path: Path) -> None:
    source = tmp_path / "cube.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    original = reality.perceive.from_3d(source, units="m", density_kg_m3=1000)
    script = original.modify.scale(2).export.to_blender(tmp_path / "out.py")
    assert script.is_file()
    assert script.with_suffix(".gltf").is_file()
    assert "bpy.ops" in script.read_text(encoding="utf-8")
    assert "rigid_body.mass" in script.read_text(encoding="utf-8")
    assert "cube.obj" in script.read_text(encoding="utf-8")
