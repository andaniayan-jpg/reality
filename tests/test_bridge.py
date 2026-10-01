"""Tests for the strict local v3 JSON bridge."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from reality import (
    Bounds,
    RealityBridge,
    SceneManifestIntegration,
    Transform,
    World,
    WorldObject,
    serve_jsonl,
)


def _manifest(root: Path) -> Path:
    source = root / "cell.reality.json"
    world = World(
        [
            WorldObject("Source", Bounds((0, 0, 0), (1, 1, 1)), id="source"),
            WorldObject(
                "Target",
                Bounds((0, 0, 0), (1, 1, 1)),
                Transform(position=(3, 0, 0)),
                id="target",
            ),
        ]
    )
    SceneManifestIntegration().export_world(world, source)
    return source


def test_bridge_delegates_manifest_world_operations_with_stable_json(tmp_path: Path) -> None:
    source = _manifest(tmp_path)
    bridge = RealityBridge(allowed_roots=[tmp_path])

    capabilities = bridge.handle({"id": "capabilities", "method": "capabilities"})
    assert capabilities["ok"] is True
    integrations = capabilities["result"]["integrations"]  # type: ignore[index]
    assert any(item["name"] == "reality-scene" and item["available"] for item in integrations)

    imported = bridge.handle(
        {
            "id": "import",
            "method": "world.import",
            "params": {"integration": "reality-scene", "path": str(source)},
        }
    )
    assert imported["ok"] is True
    world_id = imported["result"]["world_id"]  # type: ignore[index]

    distance = bridge.handle(
        {
            "id": "distance",
            "method": "world.distance",
            "params": {"world_id": world_id, "a": "Source", "b": "Target"},
        }
    )
    assert distance["ok"] is True
    assert distance["result"]["value"] == pytest.approx(2.0)  # type: ignore[index]
    assert distance["result"]["units"] == "m"  # type: ignore[index]

    destination = tmp_path / "round-trip.reality.json"
    exported = bridge.handle(
        {
            "id": "export",
            "method": "world.export",
            "params": {
                "world_id": world_id,
                "integration": "reality-scene",
                "path": str(destination),
            },
        }
    )
    assert exported["ok"] is True
    assert destination.is_file()


def test_bridge_rejects_paths_outside_the_explicit_root(tmp_path: Path) -> None:
    bridge = RealityBridge(allowed_roots=[tmp_path])

    response = bridge.handle(
        {
            "id": "outside",
            "method": "world.import",
            "params": {
                "integration": "reality-scene",
                "path": str(tmp_path.parent / "outside.json"),
            },
        }
    )

    assert response == {
        "id": "outside",
        "ok": False,
        "error": {
            "code": "invalid_request",
            "message": "path lies outside the bridge's configured filesystem roots",
        },
    }


def test_jsonl_transport_returns_one_response_per_line_and_never_executes_code(
    tmp_path: Path,
) -> None:
    bridge = RealityBridge(allowed_roots=[tmp_path])
    input_stream = StringIO('{"id":"one","method":"capabilities"}\nnot-json\n')
    output_stream = StringIO()

    serve_jsonl(bridge, input_stream, output_stream)

    responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert responses[0]["id"] == "one"
    assert responses[0]["ok"] is True
    assert responses[1]["ok"] is False
    assert responses[1]["error"]["code"] == "invalid_request"


def test_bridge_uses_real_mujoco_runtime_through_a_named_operation(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    source = tmp_path / "arm.xml"
    source.write_text(
        """<mujoco model="arm"><worldbody><body name="arm"><joint name="joint"/>
        <geom type="sphere" size="0.1"/></body></worldbody></mujoco>""",
        encoding="utf-8",
    )
    bridge = RealityBridge(allowed_roots=[tmp_path])

    response = bridge.handle(
        {"id": "inspect", "method": "mujoco.inspect", "params": {"path": str(source)}}
    )

    assert response["ok"] is True
    assert response["result"]["body_count"] == 2  # type: ignore[index]
    assert response["result"]["joints"][0]["name"] == "joint"  # type: ignore[index]
