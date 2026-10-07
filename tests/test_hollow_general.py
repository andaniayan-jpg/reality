from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_convex_hollow_and_safe_revert(tmp_path: Path) -> None:
    path = tmp_path / "sphere.obj"
    path.write_text(trimesh.creation.icosphere().export(file_type="obj"), encoding="utf-8")
    obj = reality.perceive.from_3d(path, units="m", density_kg_m3=1000)
    draft = obj.modify.hollow(wall_thickness=0.02)
    assert draft.result.watertight is True
    assert draft.result.estimated_mass < obj.estimated_mass
    too_thick = obj.modify.hollow(wall_thickness=2)
    assert too_thick.result.volume == obj.volume
    assert any("Hollowing reverted" in text for text in too_thick.change_log)
