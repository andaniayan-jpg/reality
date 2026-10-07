from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_weakest_ranks_two_comparable_components(tmp_path: Path) -> None:
    path = tmp_path / "two.glb"
    thick = trimesh.creation.box(extents=(0.5, 0.5, 2))
    thin = trimesh.creation.box(extents=(0.1, 0.1, 2))
    thin.apply_translation((2, 0, 0))
    trimesh.Scene({"thick": thick, "thin": thin}).export(path)
    obj = reality.perceive.from_3d(path, units="m")
    result = reality.reason.weakest(
        obj,
        load_axis="z",
        load_case="axial_compression",
        support="opposed_face",
        yield_strength_pa=200e6,
        yield_source="test fixture",
        force_newtons=1000,
    )
    assert isinstance(result.weakest_component, str)
    assert isinstance(result.failure_mode, str)
    assert result.safety_factor is not None
