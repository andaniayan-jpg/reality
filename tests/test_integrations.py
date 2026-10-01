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


def test_mujoco_mjcf_inspection_reads_real_joint_actuator_and_sensor_facts(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    from reality import MuJoCoSceneIntegration

    source = tmp_path / "arm.xml"
    source.write_text(
        """<mujoco model="arm">
  <compiler angle="degree"/>
  <worldbody>
    <body name="arm">
      <joint name="shoulder" type="hinge" axis="0 0 1" range="-45 90"/>
      <geom name="link" type="capsule" size="0.05 0.4"/>
    </body>
  </worldbody>
  <actuator>
    <motor name="shoulder-motor" joint="shoulder" ctrllimited="true" ctrlrange="-2 2"/>
  </actuator>
  <sensor><jointpos name="shoulder-position" joint="shoulder"/></sensor>
</mujoco>""",
        encoding="utf-8",
    )

    info = MuJoCoSceneIntegration().inspect_scene(source)

    assert info.units == "m"
    assert info.geom_count == 1
    assert len(info.joints) == len(info.actuators) == len(info.sensors) == 1
    assert info.joints[0].name == "shoulder"
    assert info.joints[0].kind == "hinge"
    assert info.joints[0].axis == pytest.approx((0.0, 0.0, 1.0))
    assert info.joints[0].limits == pytest.approx((-0.785398, 1.570796))
    assert info.joints[0].units == "rad"
    assert info.actuators[0].transmission == "joint"
    assert info.actuators[0].target_name == "shoulder"
    assert info.actuators[0].control_limits == pytest.approx((-2.0, 2.0))
    assert info.sensors[0].name == "shoulder-position"


def test_mujoco_rollout_uses_real_controls_and_never_commands_hardware(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    from reality import MuJoCoSceneIntegration

    source = tmp_path / "controlled-arm.xml"
    source.write_text(
        """<mujoco model="controlled-arm">
  <option gravity="0 0 0"/>
  <worldbody>
    <body name="arm">
      <joint name="shoulder" type="hinge" axis="0 0 1"/>
      <geom type="capsule" size="0.05 0.4"/>
    </body>
  </worldbody>
  <actuator>
    <motor name="shoulder-motor" joint="shoulder" ctrllimited="true" ctrlrange="-2 2"/>
  </actuator>
  <sensor><jointpos name="shoulder-position" joint="shoulder"/></sensor>
</mujoco>""",
        encoding="utf-8",
    )
    adapter = MuJoCoSceneIntegration()

    result = adapter.rollout(
        source,
        controls={"shoulder-motor": 1.0},
        seconds=0.02,
        time_step=0.002,
    )

    assert result.steps == 10
    assert result.controls == {"shoulder-motor": 1.0}
    assert result.sensor_readings["shoulder-position"]
    assert result.bodies[0].name == "arm"
    assert result.evidence["hardware_commanded"] is False
    assert result.evidence["source_modified"] is False
    with pytest.raises(ValueError, match="ctrlrange"):
        adapter.rollout(source, controls={"shoulder-motor": 3.0}, seconds=0.0)
    with pytest.raises(ValueError, match="unknown"):
        adapter.rollout(source, controls={"missing": 1.0}, seconds=0.0)


def test_mujoco_mjcf_export_requires_explicit_metre_units(tmp_path: Path) -> None:
    from reality import MuJoCoSceneIntegration

    centimetre_world = World(_world().objects, units="cm")
    with pytest.raises(ValueError, match="metres"):
        MuJoCoSceneIntegration().export_world(centimetre_world, tmp_path / "bad.xml")
