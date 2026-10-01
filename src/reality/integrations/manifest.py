"""A safe, deterministic interchange adapter for Reality worlds.

``reality-scene/v1`` is deliberately small: it transports authored AABB,
transform, and explicit rigid-body inputs.  It is not a replacement for mesh,
CAD, Blender, game-engine, or simulator formats.  It gives future adapters a
real, testable interchange path without executing external project scripts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

from .._models import Bounds, PhysicalProperties, Transform, Vector3, WorldObject
from .._world import World
from .base import (
    IntegrationCapability,
    IntegrationDescriptor,
    IntegrationError,
    IntegrationSyncResult,
)

_SCHEMA = "reality-scene/v1"
_MAX_MANIFEST_BYTES = 10 * 1024 * 1024


class SceneManifestError(IntegrationError):
    """Raised when a Reality scene manifest is malformed or unsafe."""


class SceneManifestIntegration:
    """Read and write the documented ``reality-scene/v1`` JSON interchange."""

    _descriptor = IntegrationDescriptor(
        name="reality-scene",
        version="1",
        runtime="portable JSON",
        capabilities=frozenset(
            {
                IntegrationCapability.IMPORT_SCENE,
                IntegrationCapability.EXPORT_SCENE,
                IntegrationCapability.READ_TRANSFORMS,
                IntegrationCapability.WRITE_TRANSFORMS,
                IntegrationCapability.READ_HIERARCHY,
            }
        ),
    )

    @property
    def descriptor(self) -> IntegrationDescriptor:
        return self._descriptor

    def import_world(self, source: Path) -> tuple[World, IntegrationSyncResult]:
        """Load a local manifest with strict schema and size checks."""
        try:
            if source.stat().st_size > _MAX_MANIFEST_BYTES:
                raise SceneManifestError(
                    f"manifest exceeds the {_MAX_MANIFEST_BYTES}-byte safety limit"
                )
            payload = json.loads(source.read_text(encoding="utf-8"))
        except OSError as error:
            raise SceneManifestError(f"could not read scene manifest {source}") from error
        except json.JSONDecodeError as error:
            raise SceneManifestError(
                f"invalid JSON scene manifest {source}: {error.msg}"
            ) from error
        world = _world_from_payload(payload)
        ids = tuple(object_.id for object_ in world.objects)
        return world, IntegrationSyncResult(
            integration=self.descriptor,
            direction="import",
            object_ids=ids,
            changed_object_ids=ids,
            reason="loaded strict reality-scene/v1 manifest",
        )

    def export_world(self, world: World, destination: Path) -> IntegrationSyncResult:
        """Write a deterministic JSON scene manifest without mesh or scripts."""
        payload = {
            "schema": _SCHEMA,
            "units": world.units,
            "objects": [_object_payload(object_) for object_ in world.objects],
        }
        try:
            destination.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        except OSError as error:
            raise SceneManifestError(f"could not write scene manifest {destination}") from error
        ids = tuple(object_.id for object_ in world.objects)
        return IntegrationSyncResult(
            integration=self.descriptor,
            direction="export",
            object_ids=ids,
            changed_object_ids=ids,
            reason=(
                "wrote strict reality-scene/v1 manifest; mesh and CAD source data are not included"
            ),
        )


def _world_from_payload(payload: object) -> World:
    if not isinstance(payload, dict):
        raise SceneManifestError("scene manifest root must be an object")
    if payload.get("schema") != _SCHEMA:
        raise SceneManifestError(f"scene manifest schema must be {_SCHEMA!r}")
    units = payload.get("units")
    if not isinstance(units, str) or not units.strip():
        raise SceneManifestError("scene manifest units must be a non-empty string")
    objects = payload.get("objects")
    if not isinstance(objects, list):
        raise SceneManifestError("scene manifest objects must be a list")
    return World((_object_from_payload(item) for item in objects), units=units)


def _object_from_payload(payload: object) -> WorldObject:
    if not isinstance(payload, dict):
        raise SceneManifestError("scene object must be an object")
    name = payload.get("name")
    identifier = payload.get("id")
    if not isinstance(name, str) or not name.strip():
        raise SceneManifestError("scene object name must be a non-empty string")
    if not isinstance(identifier, str) or not identifier.strip():
        raise SceneManifestError("scene object id must be a non-empty string")
    try:
        local_bounds = Bounds(
            _vector(payload["local_bounds"]["minimum"], "local_bounds.minimum"),
            _vector(payload["local_bounds"]["maximum"], "local_bounds.maximum"),
        )
        transform_payload = payload.get("transform", {})
        if not isinstance(transform_payload, dict):
            raise SceneManifestError("transform must be an object")
        transform = Transform(
            position=_vector(transform_payload.get("position", (0.0, 0.0, 0.0)), "position"),
            rotation=_vector(transform_payload.get("rotation", (0.0, 0.0, 0.0)), "rotation"),
            scale=_vector(transform_payload.get("scale", (1.0, 1.0, 1.0)), "scale"),
        )
        physical_payload = payload.get("physical", {})
        if not isinstance(physical_payload, dict):
            raise SceneManifestError("physical must be an object")
        physical = PhysicalProperties(
            mass=float(physical_payload.get("mass", 1.0)),
            dynamic=bool(physical_payload.get("dynamic", False)),
            collision_shape=cast(Literal["box"], physical_payload.get("collision_shape", "box")),
            friction=float(physical_payload.get("friction", 0.5)),
            restitution=float(physical_payload.get("restitution", 0.0)),
            center_of_mass=_vector(
                physical_payload.get("center_of_mass", (0.0, 0.0, 0.0)), "center_of_mass"
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SceneManifestError(f"invalid scene object {identifier!r}: {error}") from error
    return WorldObject(
        name=name,
        id=identifier,
        local_bounds=local_bounds,
        transform=transform,
        physical=physical,
    )


def _vector(value: object, field_name: str) -> Vector3:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise SceneManifestError(f"{field_name} must be a three-number array")
    try:
        return cast(Vector3, tuple(float(component) for component in value))
    except (TypeError, ValueError) as error:
        raise SceneManifestError(f"{field_name} must be a three-number array") from error


def _object_payload(object_: WorldObject) -> dict[str, Any]:
    physical = object_.physical
    return {
        "id": object_.id,
        "name": object_.name,
        "local_bounds": {
            "minimum": list(object_.local_bounds.minimum),
            "maximum": list(object_.local_bounds.maximum),
        },
        "transform": {
            "position": list(object_.position),
            "rotation": list(object_.rotation),
            "scale": list(object_.scale),
        },
        "physical": {
            "mass": physical.mass,
            "dynamic": physical.dynamic,
            "collision_shape": physical.collision_shape,
            "friction": physical.friction,
            "restitution": physical.restitution,
            "center_of_mass": list(physical.center_of_mass),
        },
    }
