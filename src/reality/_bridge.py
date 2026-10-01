"""A strict local JSON bridge for future DCC, game, and robotics hosts.

The bridge deliberately exposes a small fixed set of Reality operations. It is
not a general Python execution service and does not make any network or hardware
connections. A host must configure explicit filesystem roots before file access
is permitted.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

from ._models import PredicateResult
from ._world import World
from .integrations import (
    IntegrationError,
    IntegrationRegistry,
    IntegrationSyncResult,
    MuJoCoRolloutResult,
    MuJoCoSceneInfo,
    MuJoCoSceneIntegration,
    SceneManifestIntegration,
)


class BridgeRequestError(ValueError):
    """An invalid or unsupported request sent to the local bridge."""


class RealityBridge:
    """Stateful local bridge that delegates every geometry action to Reality."""

    def __init__(
        self,
        *,
        allowed_roots: Iterable[str | Path],
        integrations: IntegrationRegistry | None = None,
    ) -> None:
        roots = tuple(Path(root).resolve() for root in allowed_roots)
        if not roots:
            raise ValueError("RealityBridge requires at least one allowed filesystem root")
        self._roots = roots
        self._integrations = integrations or IntegrationRegistry(
            [SceneManifestIntegration(), MuJoCoSceneIntegration()]
        )
        self._worlds: dict[str, World] = {}

    def handle(self, request: Mapping[str, object]) -> dict[str, object]:
        """Handle one JSON-compatible request without raising across a transport."""
        request_id = request.get("id")
        try:
            method = _string(request, "method")
            params = request.get("params", {})
            if not isinstance(params, Mapping):
                raise BridgeRequestError("params must be an object")
            result = self._dispatch(method, params)
        except BridgeRequestError as error:
            return _error(request_id, "invalid_request", str(error))
        except (IntegrationError, LookupError, ValueError, OSError) as error:
            return _error(request_id, "operation_failed", str(error))
        return {"id": request_id, "ok": True, "result": result}

    def _dispatch(self, method: str, params: Mapping[str, object]) -> dict[str, object]:
        if method == "capabilities":
            return {
                "integrations": [
                    {
                        "name": status.descriptor.name,
                        "version": status.descriptor.version,
                        "runtime": status.descriptor.runtime,
                        "capabilities": sorted(
                            capability.value for capability in status.descriptor.capabilities
                        ),
                        "available": status.available,
                        "reason": status.reason,
                        "runtime_version": status.runtime_version,
                    }
                    for status in self._integrations.statuses()
                ]
            }
        if method == "world.import":
            adapter = self._integrations.get(_string(params, "integration"))
            world, evidence = adapter.import_world(self._read_path(params))
            world_id = f"world-{uuid4().hex}"
            self._worlds[world_id] = world
            return {
                "world_id": world_id,
                "summary": _world_summary(world),
                "evidence": _sync(evidence),
            }
        if method == "world.summary":
            return _world_summary(self._world(params))
        if method == "world.distance":
            world = self._world(params)
            return _predicate(world.distance(_string(params, "a"), _string(params, "b")))
        if method == "world.visible":
            world = self._world(params)
            return _predicate(
                world.visible(_string(params, "target"), from_=_string(params, "from"))
            )
        if method == "world.export":
            adapter = self._integrations.get(_string(params, "integration"))
            evidence = adapter.export_world(self._world(params), self._write_path(params))
            return {"evidence": _sync(evidence)}
        if method == "mujoco.inspect":
            return _scene_info(MuJoCoSceneIntegration().inspect_scene(self._read_path(params)))
        if method == "mujoco.rollout":
            controls = params.get("controls", {})
            if not isinstance(controls, Mapping) or not all(
                isinstance(name, str) and isinstance(value, int | float)
                for name, value in controls.items()
            ):
                raise BridgeRequestError("controls must map actuator names to numbers")
            seconds = _number(params, "seconds")
            time_step = _optional_number(params, "time_step")
            result = MuJoCoSceneIntegration().rollout(
                self._read_path(params),
                controls={name: float(value) for name, value in controls.items()},
                seconds=seconds,
                **({"time_step": time_step} if time_step is not None else {}),
            )
            return _rollout(result)
        raise BridgeRequestError(f"unsupported bridge method {method!r}")

    def _world(self, params: Mapping[str, object]) -> World:
        world_id = _string(params, "world_id")
        try:
            return self._worlds[world_id]
        except KeyError as error:
            raise BridgeRequestError(f"unknown local world id {world_id!r}") from error

    def _read_path(self, params: Mapping[str, object]) -> Path:
        path = self._allowed_path(_string(params, "path"))
        if not path.is_file():
            raise BridgeRequestError(f"source path is not a file: {path}")
        return path

    def _write_path(self, params: Mapping[str, object]) -> Path:
        path = self._allowed_path(_string(params, "path"))
        if not path.parent.is_dir():
            raise BridgeRequestError(f"destination directory does not exist: {path.parent}")
        return path

    def _allowed_path(self, raw: str) -> Path:
        path = Path(raw).resolve()
        if not any(path.is_relative_to(root) for root in self._roots):
            raise BridgeRequestError("path lies outside the bridge's configured filesystem roots")
        return path


def serve_jsonl(bridge: RealityBridge, input_stream: TextIO, output_stream: TextIO) -> None:
    """Serve one request per line using JSON Lines over a caller-owned transport."""
    for line in input_stream:
        try:
            request = json.loads(line)
            if not isinstance(request, Mapping):
                raise BridgeRequestError("request must be an object")
            response = bridge.handle(request)
        except (BridgeRequestError, json.JSONDecodeError) as error:
            response = _error(None, "invalid_request", str(error))
        output_stream.write(json.dumps(response, sort_keys=True) + "\n")
        output_stream.flush()


def main() -> None:
    """Run a local JSONL bridge with roots supplied on the command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Run Reality's strict local JSON bridge")
    parser.add_argument("--allow-root", action="append", required=True)
    arguments = parser.parse_args()
    serve_jsonl(RealityBridge(allowed_roots=arguments.allow_root), sys.stdin, sys.stdout)


def _string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BridgeRequestError(f"{key!r} must be a non-empty string")
    return value


def _number(mapping: Mapping[str, object], key: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise BridgeRequestError(f"{key!r} must be a number")
    return float(value)


def _optional_number(mapping: Mapping[str, object], key: str) -> float | None:
    if key not in mapping:
        return None
    return _number(mapping, key)


def _error(request_id: object, code: str, message: str) -> dict[str, object]:
    return {"id": request_id, "ok": False, "error": {"code": code, "message": message}}


def _world_summary(world: World) -> dict[str, object]:
    return {
        "units": world.units,
        "object_count": len(world.objects),
        "objects": [{"id": object_.id, "name": object_.name} for object_ in world.objects],
    }


def _sync(result: IntegrationSyncResult) -> dict[str, object]:
    return {
        "integration": result.integration.name,
        "direction": result.direction,
        "object_ids": list(result.object_ids),
        "changed_object_ids": list(result.changed_object_ids),
        "reason": result.reason,
        "warnings": list(result.warnings),
        "evidence": dict(result.evidence),
    }


def _predicate(result: PredicateResult[Any]) -> dict[str, object]:
    return {
        "value": result.value,
        "measurement": result.measurement,
        "units": result.units,
        "reason": result.reason,
        "objects": [{"id": object_.id, "name": object_.name} for object_ in result.objects],
        "evidence": dict(result.evidence),
    }


def _scene_info(info: MuJoCoSceneInfo) -> dict[str, object]:
    return {
        "source": str(info.source),
        "units": info.units,
        "mujoco_version": info.mujoco_version,
        "body_count": info.body_count,
        "geom_count": info.geom_count,
        "joints": [asdict(joint) for joint in info.joints],
        "actuators": [asdict(actuator) for actuator in info.actuators],
        "sensors": [asdict(sensor) for sensor in info.sensors],
    }


def _rollout(result: MuJoCoRolloutResult) -> dict[str, object]:
    return {
        "seconds": result.seconds,
        "time_step": result.time_step,
        "steps": result.steps,
        "controls": dict(result.controls),
        "bodies": [
            {
                "id": body.id,
                "name": body.name,
                "transform": {
                    "position": list(body.transform.position),
                    "rotation": list(body.transform.rotation),
                    "scale": list(body.transform.scale),
                },
            }
            for body in result.bodies
        ],
        "sensor_readings": {name: list(values) for name, values in result.sensor_readings.items()},
        "final_contact_count": result.final_contact_count,
        "mujoco_version": result.mujoco_version,
        "evidence": dict(result.evidence),
    }


if __name__ == "__main__":
    main()
