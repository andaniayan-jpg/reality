from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def test_diff_reports_measured_deltas_and_unknown_score(tmp_path: Path) -> None:
    source = tmp_path / "cube.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    original = reality.perceive.from_3d(source, units="m", density_kg_m3=1000)
    draft = original.modify.scale(2).material("steel")
    result = reality.diff(original, draft)
    assert result.changes
    assert result.mass_delta == pytest.approx(61800)
    assert result.volume_delta == pytest.approx(7)
    assert result.improvement_score is None  # no load case or safety-factor evidence
