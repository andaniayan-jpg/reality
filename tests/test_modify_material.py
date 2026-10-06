from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def test_material_change_is_deferred_and_does_not_mutate_source(tmp_path: Path) -> None:
    source = tmp_path / "beam.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    original = reality.perceive.from_3d(source, units="m")
    draft = original.modify.material("steel")
    assert original.material is None
    assert draft.change_log == ("Material set to steel",)
    assert draft.result.material == "steel"
    assert draft.result.estimated_mass == pytest.approx(7850)
    assert draft.result.parts[0]._mesh is original.parts[0]._mesh
