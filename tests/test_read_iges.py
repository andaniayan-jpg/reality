from __future__ import annotations

import sys
from pathlib import Path

import pytest

import reality


def test_missing_cad_backend_returns_hint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "surface.iges"
    path.write_text("S      1\n", encoding="ascii")
    monkeypatch.setitem(sys.modules, "cadquery", None)
    result = reality.perceive.from_3d(path)
    assert result.supported is False
    assert result.install_hint == "pip install reality[cad]"


def test_iges_brep_and_tessellated_surface_share_part(tmp_path: Path) -> None:
    cq = pytest.importorskip("cadquery")
    from OCP.IGESControl import IGESControl_Writer

    path = tmp_path / "body.iges"
    writer = IGESControl_Writer()
    writer.AddShape(cq.Workplane("XY").box(2, 2, 2).val().wrapped)
    assert writer.Write(str(path))
    result = reality.perceive.from_3d(path)
    assert result.parts[0].solid is not None
    assert result.parts[0].mesh is not None
    assert len(result.parts[0].mesh.faces) > 0
