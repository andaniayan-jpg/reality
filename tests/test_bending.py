from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import trimesh

import reality


def test_supported_beam_has_nominal_bending_stress_without_torque(tmp_path: Path) -> None:
    path = tmp_path / "beam.obj"
    path.write_text(trimesh.creation.box(extents=(3, 0.2, 0.2)).export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    result = reality.reason.predict(
        "500 N load",
        obj,
        span_m=3,
        bending_support="simply_supported",
        yield_strength_pa=200e6,
        yield_source="test fixture",
    )
    assert result.max_bending_stress is not None and result.max_bending_stress > 0
    assert result.bending_location is not None
    assert result.bending_risk is not None
    assert "bending" not in result.missing_by_mode
    assert result.applied_torque is None
    assert "cycles_per_day" in result.missing


def test_fatigue_is_optional_and_does_not_block_bending(tmp_path: Path) -> None:
    path = tmp_path / "beam.obj"
    path.write_text(trimesh.creation.box(extents=(3, 0.2, 0.2)).export(file_type="obj"))
    obj = replace(reality.perceive.from_3d(path, units="m"), cycles_per_day=100)
    result = reality.reason.predict(
        "500 N load",
        obj,
        load_axis="x",
        load_case="axial_tension",
        support="opposed_face",
        yield_strength_pa=200e6,
        yield_source="test fixture",
        tensile_strength_pa=300e6,
        fatigue_reference_cycles=1e6,
        span_m=3,
        bending_support="simply_supported",
    )
    assert result.fatigue_life_days is not None
    assert result.max_bending_stress is not None
