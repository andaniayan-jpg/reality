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


def test_mujoco_mjcf_adapter_compiles_real_source_and_preserves_supported_bounds(
    tmp_path: Path,
) -> None:
    mujoco = pytest.importorskip("mujoco")
    from reality import MuJoCoSceneIntegration

    source = tmp_path / "cell.xml"
    source.write_text(
        """<mujoco model="cell">
  <worldbody>
    <geom name="floor" type="plane" size="2 2 0.1"/>
    <body name="station" pos="1 2 0.5">
      <geom name="fixture" type="box" size="0.5 0.25 0.1"/>
    </body>
    <body name="payload" pos="2 2 1">
      <geom name="part" type="sphere" size="0.2"/>
    </body>
  </worldbody>
</mujoco>""",
        encoding="utf-8",
    )

    world, result = MuJoCoSceneIntegration().import_world(source)

    assert world.units == "m"
    assert world.object("fixture").position == pytest.approx((1.0, 2.0, 0.5))
    assert world.object("fixture").local_bounds.extents == pytest.approx((1.0, 0.5, 0.2))
    assert world.object("part").local_bounds.extents == pytest.approx((0.4, 0.4, 0.4))
    assert result.evidence["mujoco_version"] == mujoco.__version__
    assert result.evidence["imported_geom_count"] == 2
    assert result.evidence["skipped_geom_count"] == 1
    assert any("floor: unsupported" in warning for warning in result.warnings)


def test_mujoco_mjcf_adapter_writes_a_file_that_mujoco_compiles(tmp_path: Path) -> None:
    mujoco = pytest.importorskip("mujoco")
    from reality import MuJoCoSceneIntegration

    destination = tmp_path / "export.xml"
    result = MuJoCoSceneIntegration().export_world(_world(), destination)
    compiled = mujoco.MjModel.from_xml_path(str(destination))

    assert compiled.ngeom == 2
    assert result.evidence["compiled_geom_count"] == 2
    assert result.evidence["representation"] == "oriented bounding boxes"
    assert "bounding boxes" in result.warnings[0]


def test_mujoco_mjcf_export_requires_explicit_metre_units(tmp_path: Path) -> None:
    from reality import MuJoCoSceneIntegration

    centimetre_world = World(_world().objects, units="cm")
    with pytest.raises(ValueError, match="metres"):
        MuJoCoSceneIntegration().export_world(centimetre_world, tmp_path / "bad.xml")
