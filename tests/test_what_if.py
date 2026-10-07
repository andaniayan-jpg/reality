from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_what_if_material_keeps_original_unchanged(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "cube.obj"
    path.write_text(trimesh.creation.box().export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m", density_kg_m3=1000)
    monkeypatch.setattr(reality.reason, "_optional_ollama", lambda *_: None)
    report = reality.reason.what_if(
        obj,
        {"material": "aluminium"},
        "500 N load",
        load_axis="z",
        load_case="axial_compression",
        support="opposed_face",
        yield_strength_pa=200e6,
        yield_source="test fixture",
    )
    assert report.original is not None and report.modified is not None
    assert isinstance(report.safety_factor_delta, float | type(None))
    assert isinstance(report.better, bool | type(None))
    assert report.changes_applied["material"] == "aluminium"
    assert obj.material != "aluminium"
    assert report.original.safety_factor is not None
    assert report.modified.safety_factor is None
