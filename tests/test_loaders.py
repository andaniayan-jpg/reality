from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


@pytest.mark.parametrize("suffix", [".obj", ".glb", ".gltf"])
def test_loads_supported_formats(tmp_path: Path, suffix: str) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="Cube")
    source = tmp_path / f"scene{suffix}"
    scene.export(source)

    world = reality.load(source)

    assert len(world.objects) == 1
    cube = world.objects[0]
    assert cube.mesh is not None
    assert cube.bounds.extents == pytest.approx((1.0, 1.0, 1.0))


def test_load_rejects_unsupported_format(tmp_path: Path) -> None:
    unsupported = tmp_path / "scene.stl"
    unsupported.touch()

    with pytest.raises(ValueError, match="unsupported"):
        reality.load(unsupported)
