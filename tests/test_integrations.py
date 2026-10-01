"""Tests for the v3 external-runtime integration boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reality import (
    Bounds,
    IntegrationCapability,
    IntegrationDescriptor,
    IntegrationRegistry,
    IntegrationUnavailableError,
    PhysicalProperties,
    SceneManifestError,
    SceneManifestIntegration,
    Transform,
    UnsupportedIntegrationCapabilityError,
    World,
    WorldObject,
)


def _world() -> World:
    return World(
        [
            WorldObject(
                "RobotBase",
                Bounds((-0.5, -0.5, 0.0), (0.5, 0.5, 0.3)),
                Transform(position=(1.0, 2.0, 0.0)),
                id="robot-base",
                physical=PhysicalProperties(mass=12.0, dynamic=False),
            ),
            WorldObject(
                "Payload",
                Bounds((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1)),
                Transform(position=(1.0, 2.0, 0.4)),
                id="payload",
                physical=PhysicalProperties(mass=0.5, dynamic=True, friction=0.7),
            ),
        ],
        units="m",
    )


def test_scene_manifest_round_trip_preserves_explicit_world_semantics(tmp_path: Path) -> None:
    adapter = SceneManifestIntegration()
    source = tmp_path / "robot.reality.json"

    exported = adapter.export_world(_world(), source)
    loaded, imported = adapter.import_world(source)

    assert exported.direction == "export"
    assert imported.direction == "import"
    assert loaded.units == "m"
    assert loaded.object("RobotBase").position == (1.0, 2.0, 0.0)
    assert loaded.object("Payload").dynamic
    assert loaded.object("Payload").friction == pytest.approx(0.7)
    assert [object_.id for object_ in loaded.objects] == ["robot-base", "payload"]
    assert "mesh and CAD source data are not included" in exported.reason


def test_scene_manifest_rejects_unsupported_schema_and_malformed_objects(tmp_path: Path) -> None:
    adapter = SceneManifestIntegration()
    source = tmp_path / "invalid.reality.json"
    source.write_text(json.dumps({"schema": "other/v1", "units": "m", "objects": []}))

    with pytest.raises(SceneManifestError, match="schema"):
        adapter.import_world(source)

    source.write_text(
        json.dumps(
            {
                "schema": "reality-scene/v1",
                "units": "m",
                "objects": [{"id": "missing-name"}],
            }
        )
    )
    with pytest.raises(SceneManifestError, match="name"):
        adapter.import_world(source)


def test_registry_requires_explicit_capabilities_and_rejects_duplicates() -> None:
    adapter = SceneManifestIntegration()
    registry = IntegrationRegistry([adapter])

    assert registry.get("REALITY-SCENE") is adapter
    assert registry.descriptors() == (adapter.descriptor,)
    adapter.descriptor.require(IntegrationCapability.IMPORT_SCENE)
    with pytest.raises(UnsupportedIntegrationCapabilityError, match="physics_simulation"):
        adapter.descriptor.require(IntegrationCapability.PHYSICS_SIMULATION)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(adapter)
    with pytest.raises(IntegrationUnavailableError, match="registered integrations"):
        registry.get("blender")


def test_integration_descriptor_rejects_missing_identity() -> None:
    with pytest.raises(ValueError, match="name"):
        IntegrationDescriptor(name="", version="1", runtime="test", capabilities=frozenset())
