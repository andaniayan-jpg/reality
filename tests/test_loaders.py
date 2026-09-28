from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh

import reality
from reality import SceneMetadataError


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


def test_sidecar_metadata_configures_units_physics_and_articulation(tmp_path: Path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="Door")
    source = tmp_path / "door.glb"
    scene.export(source)
    (tmp_path / "door.reality.json").write_text(
        json.dumps(
            {
                "units": "cm",
                "objects": {
                    "Door": {
                        "articulation": {
                            "joint": "revolute",
                            "axis": [0, 0, 1],
                            "pivot": [0, 0, 0],
                            "limits": [0, 90],
                        },
                        "physics": {"mass": 12.5, "dynamic": True, "friction": 0.4},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    world = reality.load(source)

    assert world.units == "cm"
    assert world.object("Door").mass == pytest.approx(12.5)
    assert world.object("Door").dynamic
    assert world["Door"].can_rotate(45).possible  # type: ignore[union-attr]


def test_gltf_node_extras_ingest_reality_metadata(tmp_path: Path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="Drawer")
    source = tmp_path / "drawer.gltf"
    scene.export(source)
    payload = json.loads(source.read_text(encoding="utf-8"))
    node = next(item for item in payload["nodes"] if item.get("name") == "Drawer")
    node["extras"] = {
        "reality": {
            "articulation": {
                "joint": "prismatic",
                "axis": [1, 0, 0],
                "limits": [0, 0.5],
                "linear_resolution": 0.02,
            },
            "physics": {"dynamic": True, "mass": 2.0},
        }
    }
    source.write_text(json.dumps(payload), encoding="utf-8")

    world = reality.load(source)

    assert world.object("Drawer").dynamic
    assert world["Drawer"].can_extend(0.4).possible  # type: ignore[union-attr]


def test_explicit_metadata_is_validated_and_missing_objects_are_rejected(tmp_path: Path) -> None:
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box(), node_name="Cube")
    source = tmp_path / "scene.glb"
    scene.export(source)

    with pytest.raises(SceneMetadataError, match="missing or ambiguous"):
        reality.load(
            source,
            metadata={
                "objects": {
                    "Missing": {
                        "articulation": {
                            "joint": "revolute",
                            "axis": [0, 0, 1],
                            "limits": [0, 45],
                        }
                    }
                }
            },
        )
