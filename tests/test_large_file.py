from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def test_progress_and_fast_mode_are_explicit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(reality.perceive, "LARGE_FILE_THRESHOLD_BYTES", 1)
    path = tmp_path / "cube.obj"
    trimesh.creation.box().export(path)
    updates: list[tuple[int, str]] = []
    result = reality.perceive.from_3d(
        path,
        units="m",
        density_kg_m3=1000,
        fast=True,
        on_progress=lambda pct, message: updates.append((pct, message)),
    )
    assert updates[0][0] == 0
    assert updates[-1][0] == 100
    assert any(message == "Scanning large input" for _, message in updates)
    assert all(left[0] <= right[0] for left, right in zip(updates, updates[1:], strict=False))
    assert result.fast is True
    assert result.analysis_sample_fraction is not None
    assert 0.1 <= result.analysis_sample_fraction <= 0.2
    assert result.surface_area is not None
    assert result.volume is None
    assert result.estimated_mass is None
