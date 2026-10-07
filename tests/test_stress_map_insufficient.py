from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_stress_map_is_grey_without_strength_and_load_case(tmp_path: Path) -> None:
    path = tmp_path / "cube.obj"
    path.write_text(trimesh.creation.box().export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    output = reality.reason.predict("will it fail?", obj).export_stress_map(tmp_path / "grey.obj")
    content = output.read_text()
    assert "# Stress data insufficient" in content
    assert any(
        line.endswith("0.5 0.5 0.5") for line in content.splitlines() if line.startswith("v ")
    )
