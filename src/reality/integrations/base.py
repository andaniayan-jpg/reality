"""Capability-checked contracts for external Reality integrations.

Adapters live at the boundary between Reality's backend-neutral ``World`` and
an external runtime such as Blender, a game engine, or a robotics simulator.
The core package never treats an adapter as available merely because its Python
module can be imported: a caller must inspect its descriptor and capabilities.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from .._world import World


class IntegrationError(RuntimeError):
    """Base error raised by external-runtime integrations."""


class IntegrationUnavailableError(IntegrationError):
    """Raised when a requested adapter is not installed or cannot run."""


class UnsupportedIntegrationCapabilityError(IntegrationError):
    """Raised when an adapter does not implement a requested operation."""


class IntegrationCapability(StrEnum):
    """An operation an external runtime can truthfully support."""

    IMPORT_SCENE = "import_scene"
    EXPORT_SCENE = "export_scene"
    READ_TRANSFORMS = "read_transforms"
    WRITE_TRANSFORMS = "write_transforms"
    READ_MESHES = "read_meshes"
    READ_MATERIALS = "read_materials"
    READ_HIERARCHY = "read_hierarchy"
    LIVE_SYNC = "live_sync"
    PHYSICS_SIMULATION = "physics_simulation"
    SENSOR_STREAMS = "sensor_streams"
    ROBOT_COMMANDS = "robot_commands"
    RENDER_PREVIEW = "render_preview"


@dataclass(frozen=True, slots=True)
class IntegrationDescriptor:
    """Stable, serializable facts about one adapter implementation."""

    name: str
    version: str
    capabilities: frozenset[IntegrationCapability]
    runtime: str
    documentation_url: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("integration name must not be empty")
        if not self.version or not self.version.strip():
            raise ValueError("integration version must not be empty")
        if not self.runtime or not self.runtime.strip():
            raise ValueError("integration runtime must not be empty")
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))

    def supports(self, capability: IntegrationCapability) -> bool:
        """Return whether this adapter explicitly declares an operation."""
        return capability in self.capabilities

    def require(self, capability: IntegrationCapability) -> None:
        """Raise a clear error instead of silently degrading an operation."""
        if not self.supports(capability):
            raise UnsupportedIntegrationCapabilityError(
                f"integration {self.name!r} does not support {capability.value!r}"
            )


@dataclass(frozen=True, slots=True)
class IntegrationSyncResult:
    """Evidence returned after an adapter imports, exports, or synchronizes state."""

    integration: IntegrationDescriptor
    direction: str
    object_ids: tuple[str, ...]
    changed_object_ids: tuple[str, ...]
    reason: str
    warnings: tuple[str, ...] = ()
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@runtime_checkable
class WorldIntegration(Protocol):
    """Contract shared by Blender, engine, simulator, and robotics adapters.

    Implementations must not fabricate geometry facts.  They map the external
    runtime's source data into ``WorldObject`` values and surface any lost or
    unsupported semantics through exceptions or ``IntegrationSyncResult``.
    """

    @property
    def descriptor(self) -> IntegrationDescriptor: ...

    def import_world(self, source: Path) -> tuple[World, IntegrationSyncResult]: ...

    def export_world(self, world: World, destination: Path) -> IntegrationSyncResult: ...


class IntegrationRegistry:
    """Explicit registry for installed integrations.

    Registration is process-local by design. Production servers should create
    their registry during startup rather than discovering arbitrary modules or
    executing project scripts from an uploaded scene.
    """

    def __init__(self, integrations: Iterable[WorldIntegration] = ()) -> None:
        self._integrations: dict[str, WorldIntegration] = {}
        for integration in integrations:
            self.register(integration)

    def register(self, integration: WorldIntegration) -> None:
        descriptor = integration.descriptor
        key = descriptor.name.casefold()
        if key in self._integrations:
            raise ValueError(f"integration already registered: {descriptor.name!r}")
        self._integrations[key] = integration

    def get(self, name: str) -> WorldIntegration:
        try:
            return self._integrations[name.casefold()]
        except KeyError as error:
            available = ", ".join(item.name for item in self.descriptors()) or "none"
            raise IntegrationUnavailableError(
                f"integration {name!r} is unavailable; registered integrations: {available}"
            ) from error

    def descriptors(self) -> tuple[IntegrationDescriptor, ...]:
        """Return stable adapter facts sorted by integration name."""
        return tuple(
            sorted(
                (integration.descriptor for integration in self._integrations.values()),
                key=lambda descriptor: descriptor.name.casefold(),
            )
        )
