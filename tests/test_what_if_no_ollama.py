from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_what_if_computed_fallback_without_model(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "cube.obj"
    path.write_text(trimesh.creation.box().export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    monkeypatch.setattr(reality.reason, "_optional_ollama", lambda *_: None)
    report = reality.reason.what_if(obj, {"load": 1000}, "500 N load")
    assert "Original safety factor:" in report.recommendation
    assert "Modified safety factor:" in report.recommendation
    assert report.changes_applied["load"] == 1000
