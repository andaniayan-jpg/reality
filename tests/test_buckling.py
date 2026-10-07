from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_slender_column_buckling_is_independent_of_bending(tmp_path: Path) -> None:
    path = tmp_path / "steel_column.obj"
    path.write_text(trimesh.creation.box(extents=(0.1, 0.1, 3)).export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    result = reality.reason.predict(
        "500 N compressive load",
        obj,
        load_case="axial_compression",
        youngs_modulus_pa=200e9,
    )
    assert result.buckling_load is not None and result.buckling_load > 0
    assert result.buckling_risk in {"low", "medium", "high"}
    assert result.slender_members
    assert result.outcome == "partial"
    assert "buckling" not in result.missing_by_mode
    assert result.max_bending_stress is None


def test_unsupported_file_returns_mode_gaps_instead_of_crashing(tmp_path: Path) -> None:
    path = tmp_path / "unreadable.blend"
    path.write_bytes(b"BLENDER-vfake")
    obj = reality.perceive.from_3d(path)
    result = reality.reason.predict("500 N load", obj)
    assert result.outcome == "unknown"
    assert result.buckling_load is None
    assert "buckling" in result.missing_by_mode
