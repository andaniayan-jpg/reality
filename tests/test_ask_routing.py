from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import trimesh

import reality


def test_ask_routes_predict_and_what_if(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "cube.obj"
    path.write_text(trimesh.creation.box().export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    called: list[str] = []

    def fake_predict(*_args, **_kwargs):
        called.append("predict")
        return SimpleNamespace(reason="measured screen")

    def fake_what_if(*_args, **_kwargs):
        called.append("what_if")
        return SimpleNamespace(recommendation="comparison")

    monkeypatch.setattr(reality.reason, "predict", fake_predict)
    monkeypatch.setattr(reality.reason, "what_if", fake_what_if)
    monkeypatch.setattr(reality.reason, "_optional_ollama", lambda *_: None)
    assert reality.reason.ask(obj, "will it fail under 500kg?").route == "predict"
    assert reality.reason.ask(obj, "what if I use aluminium?").route == "what_if"
    assert called == ["predict", "what_if"]
