"""Assimp adapter tests use a tiny in-memory scene, not fake measurements."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import trimesh

import reality


@pytest.mark.parametrize("suffix", ["fbx", "dae", "3ds"])
def test_assimp_scene_keeps_named_meshes_and_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, suffix: str
) -> None:
    from reality import _assimp_model

    cube = trimesh.creation.box()

    def leaf(name: str, x: float) -> SimpleNamespace:
        matrix = np.eye(4)
        matrix[0, 3] = x
        mesh = SimpleNamespace(name=name, vertices=cube.vertices, faces=cube.faces)
        return SimpleNamespace(name=name, transformation=matrix, meshes=[mesh], children=[])

    root = SimpleNamespace(
        name="Building",
        transformation=np.eye(4),
        meshes=[],
        children=[leaf("Foundation", 0), leaf("Roof", 2)],
    )

    @contextmanager
    def load(_path: str) -> Any:
        yield SimpleNamespace(rootnode=root)

    monkeypatch.setattr(
        _assimp_model.importlib, "import_module", lambda _: SimpleNamespace(load=load)
    )
    path = tmp_path / f"building.{suffix}"
    path.write_bytes(b"fixture handled by adapter boundary")
    scene = reality.perceive.from_3d(path, units="m")
    assert isinstance(scene, reality.PhysicsScene)
    assert [item.parts[0].name for item in scene.objects] == ["Foundation", "Roof"]
    assert scene.objects[1].bounds.center[0] == pytest.approx(2)
    assert scene.hierarchy[0].name == "Building"
    assert [node.name for node in scene.hierarchy[0].children] == ["Foundation", "Roof"]


def test_missing_assimp_is_explicit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from reality import _assimp_model

    def missing(_name: str) -> None:
        raise ImportError("not installed")

    monkeypatch.setattr(_assimp_model.importlib, "import_module", missing)
    path = tmp_path / "part.fbx"
    path.write_bytes(b"fixture")
    result = reality.perceive.from_3d(path)
    assert result.supported is False
    assert result.model is None
    assert result.install_hint == "pip install reality[assimp]"
