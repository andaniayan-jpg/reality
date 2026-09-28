"""Backend-neutral physical simulation values and backend selection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from ._models import Transform, Vector3, WorldObject

if TYPE_CHECKING:
    from .backends.base import PhysicsBackend


class PhysicsBackendUnavailableError(RuntimeError):
    """Raised when a requested optional physics backend cannot be used."""


class UnsupportedPhysicsOperationError(RuntimeError):
    """Raised when a backend lacks a required capability."""


@dataclass(frozen=True, slots=True)
class Contact:
    object_a_id: str
    object_b_id: str | None
    point: Vector3
    normal: Vector3
    separation: float


@dataclass(frozen=True, slots=True)
class BodySimulationResult:
    object_id: str
    object_name: str
    initial_transform: Transform
    final_transform: Transform
    initial_velocity: Vector3
    final_velocity: Vector3
    contacts: tuple[Contact, ...]
    fell: bool
    motion: float

    @property
    def collision_pairs(self) -> tuple[tuple[str, str | None], ...]:
        return tuple((contact.object_a_id, contact.object_b_id) for contact in self.contacts)

    @property
    def contact_count(self) -> int:
        return len(self.contacts)


@dataclass(frozen=True, slots=True)
class SimulationResult:
    backend: str
    backend_version: str
    seconds: float
    time_step: float
    steps: int
    bodies: tuple[BodySimulationResult, ...]
    deterministic: bool
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    @property
    def collision_pairs(self) -> tuple[tuple[str, str | None], ...]:
        pairs = {pair for body in self.bodies for pair in body.collision_pairs}
        return tuple(sorted(pairs, key=lambda pair: (pair[0], pair[1] or "")))

    @property
    def contact_count(self) -> int:
        return sum(body.contact_count for body in self.bodies)

    def body(self, reference: str | WorldObject) -> BodySimulationResult:
        key = reference.id if isinstance(reference, WorldObject) else reference
        matches = [body for body in self.bodies if body.object_id == key or body.object_name == key]
        if len(matches) != 1:
            raise LookupError(
                f"simulation body reference {key!r} resolved to {len(matches)} bodies"
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class StabilityResult:
    stable: bool
    object: WorldObject
    support_objects: tuple[WorldObject, ...]
    reason: str
    center_of_mass: Vector3
    support_region: tuple[float, float, float, float] | None

    @property
    def value(self) -> bool:
        return self.stable


def create_backend(name: str) -> PhysicsBackend:
    if name in {"cpu", "mujoco"}:
        try:
            from .backends.mujoco import MuJoCoBackend

            return MuJoCoBackend()
        except ImportError as error:
            raise PhysicsBackendUnavailableError(
                "The CPU physics backend requires the optional 'mujoco' package. "
                "Install reality[physics] or mujoco."
            ) from error
    raise PhysicsBackendUnavailableError(
        f"Unknown or unavailable physics backend {name!r}; available backend: 'cpu' (MuJoCo)."
    )
