from __future__ import annotations

from pathlib import Path

import reality


def test_blend_returns_embedded_gltf_script_without_running_it(tmp_path: Path) -> None:
    source = tmp_path / "robot.blend"
    source.write_bytes(b"BLENDER")
    result = reality.perceive.from_3d(source)
    assert isinstance(result, reality.PhysicsObject)
    assert result.supported is False
    assert result.model is None
    assert result.blend_export_script is not None
    assert "GLTF_EMBEDDED" in result.blend_export_script
    assert source.name in result.blend_export_script
    assert not (tmp_path / "robot-reality.gltf").exists()
