from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh

import reality


class _Provider:
    def interpret_edit(self, instruction: str) -> str:
        assert instruction == "make it twice as big"
        return json.dumps({"method": "scale", "args": {"factor": 2.0}})


class _Offline:
    def interpret_edit(self, instruction: str) -> str:
        raise ConnectionError("offline")


def test_provider_proposal_is_schema_checked_then_applied(tmp_path: Path) -> None:
    source = tmp_path / "cube.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    original = reality.perceive.from_3d(source, units="m")
    draft = original.modify.apply("make it twice as big", provider=_Provider())
    assert draft.result.volume == pytest.approx(8)
    assert original.volume == pytest.approx(1)


def test_offline_provider_uses_literal_fallback_without_raising(tmp_path: Path) -> None:
    source = tmp_path / "cube.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    original = reality.perceive.from_3d(source, units="m")
    draft = original.modify.apply("make it 2 times as big", provider=_Offline())
    assert draft.result.volume == pytest.approx(8)
    assert draft.optimization_log[0].startswith("Provider unavailable")
