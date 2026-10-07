from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_minimum_weight_does_not_invent_safety_factors(tmp_path: Path) -> None:
    path = tmp_path / "cube.obj"
    path.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    obj = reality.perceive.from_3d(path, units="m", density_kg_m3=1000)
    draft = obj.modify.optimize_for("minimum_weight")
    assert draft.optimization_log
    assert "safety factor" in draft.optimization_log[0]
    assert draft.result.estimated_mass == obj.estimated_mass
    assert obj.modify.optimize_for("not-a-goal").optimization_log == ["Unknown goal: not-a-goal"]
