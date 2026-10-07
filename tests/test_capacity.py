from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_capacity_reports_only_supported_thresholds(tmp_path: Path) -> None:
    path = tmp_path / "column.obj"
    path.write_text(trimesh.creation.box(extents=(0.1, 0.1, 3)).export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    unknown = reality.reason.capacity(obj)
    assert unknown.max_load is None
    measured = reality.reason.capacity(
        obj,
        load_axis="z",
        load_case="axial_compression",
        support="opposed_face",
        yield_strength_pa=200e6,
        yield_source="test fixture",
        youngs_modulus_pa=200e9,
    )
    assert isinstance(measured.max_load, float)
    assert measured.limiting_mode in {"yield", "buckling"}


def test_capacity_uses_explicit_beam_span(tmp_path: Path) -> None:
    path = tmp_path / "beam.obj"
    path.write_text(trimesh.creation.box(extents=(3, 0.2, 0.2)).export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    result = reality.reason.capacity(
        obj,
        span_m=3,
        bending_support="simply_supported",
        yield_strength_pa=200e6,
        yield_source="test fixture",
    )
    assert result.max_load is not None and result.max_load > 0
    assert result.limiting_mode == "bending"
