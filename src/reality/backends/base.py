"""Narrow protocol implemented by physical simulation backends."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from .._models import Vector3, WorldObject
from .._physics import SimulationResult


@dataclass(frozen=True, slots=True)
class PhysicsCapabilities:
    rigid_bodies: bool
    colliders: bool
    gravity: bool
    contacts: bool
    forces: bool


class PhysicsBackend(Protocol):
    """The minimal engine surface Reality depends on."""

    name: str
    version: str
    capabilities: PhysicsCapabilities

    def simulate(
        self,
        objects: Sequence[WorldObject],
        *,
        seconds: float,
        time_step: float,
        gravity: Vector3,
        forces: Mapping[str, tuple[Vector3, float]],
    ) -> SimulationResult: ...
