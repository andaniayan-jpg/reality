from __future__ import annotations

import sys
from pathlib import Path

import pytest
import trimesh

import reality


def test_missing_usd_bindings_returns_install_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "mesh.usda"
    path.write_text("#usda 1.0\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "pxr", None)
    result = reality.perceive.from_3d(path)
    assert result.supported is False
    assert result.install_hint == "pip install reality[usd]"


def test_usd_material_binding_is_source_visual_label(tmp_path: Path) -> None:
    pytest.importorskip("pxr")
    from pxr import Gf, Usd, UsdGeom, UsdShade

    path = tmp_path / "scene.usda"
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    mesh = UsdGeom.Mesh.Define(stage, "/Assembly/Body")
    cube = trimesh.creation.box()
    mesh.GetPointsAttr().Set([Gf.Vec3f(*map(float, point)) for point in cube.vertices])
    mesh.GetFaceVertexCountsAttr().Set([3] * len(cube.faces))
    mesh.GetFaceVertexIndicesAttr().Set([int(index) for index in cube.faces.ravel()])
    material = UsdShade.Material.Define(stage, "/Materials/BluePaint")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    stage.GetRootLayer().Save()
    del stage
    result = reality.perceive.from_3d(path)
    assert result.supported
    assert result.parts[0].material.name == "BluePaint"
    assert result.parts[0].metadata["material_path"] == "/Materials/BluePaint"
    assert result.material_source == "source-name"
