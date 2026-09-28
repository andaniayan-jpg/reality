"""Explicit articulated joints and deterministic swept-AABB motion analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import ceil, cos, isfinite, radians, sin, sqrt
from types import MappingProxyType
from typing import TYPE_CHECKING, TypeAlias

import numpy as np

from ._models import Bounds, Vector3, WorldObject

if TYPE_CHECKING:
    from ._world import World

MotionKey: TypeAlias = tuple[str, str, float]
MotionRecord: TypeAlias = tuple[str, str, float, "MotionResult"]


def _unit_vector(value: Vector3) -> Vector3:
    converted = tuple(float(component) for component in value)
    length = sqrt(sum(component * component for component in converted))
    if length <= 1e-12 or not all(isfinite(component) for component in converted):
        raise ValueError("joint axis must be finite and non-zero")
    return tuple(component / length for component in converted)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class Joint:
    axis: Vector3
    minimum: float
    maximum: float
    current: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "axis", _unit_vector(self.axis))
        if not all(isfinite(value) for value in (self.minimum, self.maximum, self.current)):
            raise ValueError("joint values must be finite")
        if self.minimum > self.maximum:
            raise ValueError("joint minimum must not exceed maximum")
        if not self.minimum <= self.current <= self.maximum:
            raise ValueError("joint current value must lie within limits")

    @property
    def kind(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RevoluteJoint(Joint):
    """A degree-valued rotation about a world-space pivot and axis."""

    pivot: Vector3 = (0.0, 0.0, 0.0)
    angular_resolution: float = 1.0

    def __post_init__(self) -> None:
        super(RevoluteJoint, self).__post_init__()
        if len(self.pivot) != 3 or not all(isfinite(value) for value in self.pivot):
            raise ValueError("pivot must contain three finite values")
        if self.angular_resolution <= 0.0:
            raise ValueError("angular_resolution must be positive")

    @property
    def kind(self) -> str:
        return "revolute"


@dataclass(frozen=True, slots=True)
class PrismaticJoint(Joint):
    """A metre-valued translation along a world-space axis."""

    linear_resolution: float = 0.01

    def __post_init__(self) -> None:
        super(PrismaticJoint, self).__post_init__()
        if self.linear_resolution <= 0.0:
            raise ValueError("linear_resolution must be positive")

    @property
    def kind(self) -> str:
        return "prismatic"


@dataclass(frozen=True, slots=True)
class Articulation:
    object_id: str
    joint: RevoluteJoint | PrismaticJoint

    @property
    def value(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class MotionResult:
    possible: bool
    requested: float
    maximum_collision_free: float
    collision_at: float | None
    collides_with: tuple[WorldObject, ...]
    units: str
    reason: str
    samples_tested: int
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    @property
    def value(self) -> bool:
        return self.possible

    def to_dict(self) -> dict[str, object]:
        return {
            "possible": self.possible,
            "requested": self.requested,
            "maximum_collision_free": self.maximum_collision_free,
            "collision_at": self.collision_at,
            "collides_with": [
                {"id": object_.id, "name": object_.name} for object_ in self.collides_with
            ],
            "units": self.units,
            "reason": self.reason,
            "samples_tested": self.samples_tested,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class ArticulatedObject:
    """World-bound handle exposing an object's constrained motion queries."""

    object: WorldObject
    articulation: Articulation
    _world: World = field(compare=False, repr=False)

    def motion_range(self) -> tuple[float, float]:
        return self.articulation.joint.minimum, self.articulation.joint.maximum

    def can_rotate(self, degrees: float) -> MotionResult:
        if not isinstance(self.articulation.joint, RevoluteJoint):
            raise TypeError(f"{self.object.name!r} does not have a revolute joint")
        return self._world._motion_query(self.object.id, "revolute", float(degrees))

    def can_extend(self, distance: float) -> MotionResult:
        if not isinstance(self.articulation.joint, PrismaticJoint):
            raise TypeError(f"{self.object.name!r} does not have a prismatic joint")
        return self._world._motion_query(self.object.id, "prismatic", float(distance))


def analyze_motion(
    world: World,
    object_: WorldObject,
    articulation: Articulation,
    requested: float,
) -> MotionResult:
    joint = articulation.joint
    units = "deg" if isinstance(joint, RevoluteJoint) else world.units
    limited = min(joint.maximum, max(joint.minimum, requested))
    limit_prevents = limited != requested
    resolution = (
        joint.angular_resolution if isinstance(joint, RevoluteJoint) else joint.linear_resolution
    )
    span = limited - joint.current
    sample_count = max(1, int(ceil(abs(span) / resolution)))
    samples = [joint.current + span * index / sample_count for index in range(1, sample_count + 1)]
    last_safe = joint.current
    tested = 0
    for sample in samples:
        tested += 1
        bounds = _motion_bounds(object_.bounds, joint, sample)
        blockers = tuple(
            candidate
            for candidate in world.objects
            if candidate.id != object_.id and bounds.intersects(candidate.bounds)
        )
        if blockers:
            refined = _refine_collision(world, object_, joint, last_safe, sample)
            refined_bounds = _motion_bounds(object_.bounds, joint, sample)
            refined_blockers = tuple(
                candidate
                for candidate in world.objects
                if candidate.id != object_.id and refined_bounds.intersects(candidate.bounds)
            )
            names = ", ".join(item.name for item in refined_blockers or blockers)
            return MotionResult(
                possible=False,
                requested=requested,
                maximum_collision_free=refined,
                collision_at=sample,
                collides_with=refined_blockers or blockers,
                units=units,
                reason=f"Motion is blocked by {names} near {sample:.4g} {units}.",
                samples_tested=tested,
                evidence={
                    "method": "sampled swept world-AABB with binary refinement",
                    "resolution": resolution,
                    "joint_limits": (joint.minimum, joint.maximum),
                },
            )
        last_safe = sample
    if limit_prevents:
        return MotionResult(
            possible=False,
            requested=requested,
            maximum_collision_free=limited,
            collision_at=None,
            collides_with=(),
            units=units,
            reason=f"Requested motion exceeds the configured joint limit of {limited:g} {units}.",
            samples_tested=tested,
            evidence={"joint_limits": (joint.minimum, joint.maximum), "resolution": resolution},
        )
    return MotionResult(
        possible=True,
        requested=requested,
        maximum_collision_free=requested,
        collision_at=None,
        collides_with=(),
        units=units,
        reason="The complete sampled motion path is collision-free.",
        samples_tested=tested,
        evidence={
            "method": "sampled swept world-AABB",
            "resolution": resolution,
            "joint_limits": (joint.minimum, joint.maximum),
        },
    )


def _motion_bounds(initial: Bounds, joint: RevoluteJoint | PrismaticJoint, value: float) -> Bounds:
    delta = value - joint.current
    if isinstance(joint, PrismaticJoint):
        offset = tuple(component * delta for component in joint.axis)
        return Bounds(
            tuple(initial.minimum[index] + offset[index] for index in range(3)),  # type: ignore[arg-type]
            tuple(initial.maximum[index] + offset[index] for index in range(3)),  # type: ignore[arg-type]
        )
    angle = radians(delta)
    axis = np.asarray(joint.axis, dtype=np.float64)
    cross = np.array([[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]])
    rotation = (
        np.eye(3) * cos(angle) + (1.0 - cos(angle)) * np.outer(axis, axis) + sin(angle) * cross
    )
    pivot = np.asarray(joint.pivot, dtype=np.float64)
    points = [rotation @ (np.asarray(corner) - pivot) + pivot for corner in initial.corners]
    return Bounds.from_points(np.asarray(points))


def _refine_collision(
    world: World,
    object_: WorldObject,
    joint: RevoluteJoint | PrismaticJoint,
    safe: float,
    blocked: float,
) -> float:
    tolerance = 0.01 if isinstance(joint, RevoluteJoint) else 0.0001
    low, high = safe, blocked
    for _ in range(24):
        if abs(high - low) <= tolerance:
            break
        middle = (low + high) / 2.0
        bounds = _motion_bounds(object_.bounds, joint, middle)
        collision = any(
            candidate.id != object_.id and bounds.intersects(candidate.bounds)
            for candidate in world.objects
        )
        if collision:
            high = middle
        else:
            low = middle
    return low
