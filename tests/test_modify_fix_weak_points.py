from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def test_fix_weak_points_is_labelled_whole_part_heuristic(tmp_path: Path) -> None:
    source = tmp_path / "thin.obj"
    source.write_text(
        trimesh.creation.box(extents=(1, 1, 0.02)).export(file_type="obj"),
        encoding="utf-8",
    )
    original = reality.perceive.from_3d(source, units="m")
    assert len(original.weak_points) == 1
    draft = original.modify.fix_weak_points()
    assert draft.change_log
    assert draft.result.bounds.extents[2] == pytest.approx(0.05)
    assert original.bounds.extents[2] == pytest.approx(0.02)
    assert draft.result.balance == "unknown"
