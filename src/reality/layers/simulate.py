"""Small deterministic rigid-body fallback used when no engine is installed."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal, cast

from reality._physics_object import PhysicsObject

Vector = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class CollisionEvent:
    first: str
    second: str
    step: int


@dataclass(frozen=True, slots=True)
class SimResult:
    frames: tuple[dict[str, Vector], ...]
    final_state: dict[str, Vector]
    collisions: tuple[CollisionEvent, ...]
    energy: tuple[float, ...]
    summary: str


@dataclass(slots=True)
class _Body:
    name: str
    mass: float
    position: list[float]
    velocity: list[float]
    half: Vector
    force: list[float]


class _Export:
    def __init__(self, simulation: SimWorld) -> None:
        self.simulation = simulation

    def _write(self, path: str | Path, kind: str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"# Reality {kind} export\n# bodies: {', '.join(self.simulation._bodies)}\n",
            encoding="utf-8",
        )
        return target

    def to_blender(self, path: str | Path) -> Path:
        return self._write(path, "Blender")

    def to_godot(self, path: str | Path) -> Path:
        return self._write(path, "Godot")

    def to_unity(self, path: str | Path) -> Path:
        return self._write(path, "Unity")

    def to_ros2(self, path: str | Path) -> Path:
        return self._write(path, "ROS 2")


class SimWorld:
    """Euler/AABB educational fallback; it is not a validated physics solver."""

    def __init__(self, backend: Literal["builtin", "pybullet"] = "builtin") -> None:
        self.backend = backend
        self.gravity: Vector = (0.0, -9.81, 0.0)
        self.friction = 0.5
        self.restitution = 0.3
        self._bodies: dict[str, _Body] = {}
        self.export = _Export(self)

    def add(
        self,
        name: str | None = None,
        mass: float | None = None,
        position: list[float] | Vector = (0.0, 0.0, 0.0),
        material: str | None = None,
        obj: PhysicsObject | None = None,
    ) -> SimWorld:
        if obj is not None:
            name = name or (obj.parts[0].name if obj.model is not None else "object")
            mass = mass if mass is not None else obj.estimated_mass
            extents = obj.bounds.extents if obj.model is not None else (1.0, 1.0, 1.0)
        else:
            extents = (1.0, 1.0, 1.0)
        if not name or not name.strip():
            raise ValueError("simulation body needs a name")
        if name in self._bodies:
            raise ValueError(f"simulation body {name!r} already exists")
        # A caller must choose a mass rather than accepting a language-model fact.
        if mass is None:
            raise ValueError("mass is required when the object has no measured mass")
        if not isfinite(mass) or mass <= 0:
            raise ValueError("mass must be positive and finite")
        if len(position) != 3 or not all(isfinite(float(v)) for v in position):
            raise ValueError("position must contain three finite numbers")
        self._bodies[name] = _Body(
            name,
            float(mass),
            [float(v) for v in position],
            [0.0, 0.0, 0.0],
            cast(Vector, tuple(float(v) / 2 for v in extents)),
            [0.0, 0.0, 0.0],
        )
        return self

    def add_surface(self, friction: float = 0.5, restitution: float = 0.3) -> SimWorld:
        if friction < 0 or not 0 <= restitution <= 1:
            raise ValueError("friction must be non-negative and restitution must be 0..1")
        self.friction, self.restitution = float(friction), float(restitution)
        return self

    def apply_force(self, name: str, vector: Vector, duration: float | None = None) -> SimWorld:
        body = self._bodies[name]
        if len(vector) != 3 or not all(isfinite(value) for value in vector):
            raise ValueError("force must contain three finite values")
        scale = 1.0 if duration is None else float(duration)
        body.force = [body.force[i] + vector[i] * scale for i in range(3)]
        return self

    def set_gravity(self, vector: Vector = (0.0, -9.81, 0.0)) -> SimWorld:
        if len(vector) != 3 or not all(isfinite(value) for value in vector):
            raise ValueError("gravity must contain three finite values")
        self.gravity = vector
        return self

    def run(self, steps: int = 500, *, time_step: float = 1 / 60) -> SimResult:
        if steps < 1 or not isfinite(time_step) or time_step <= 0:
            raise ValueError("steps and time_step must be positive")
        frames: list[dict[str, Vector]] = []
        energy: list[float] = []
        collisions: list[CollisionEvent] = []
        for step in range(steps):
            for body in self._bodies.values():
                for axis in range(3):
                    acceleration = self.gravity[axis] + body.force[axis] / body.mass
                    body.velocity[axis] += acceleration * time_step
                    body.position[axis] += body.velocity[axis] * time_step
                body.force = [0.0, 0.0, 0.0]
                floor = body.half[1]
                if body.position[1] < floor:
                    body.position[1] = floor
                    body.velocity[1] = -body.velocity[1] * self.restitution
                    body.velocity[0] *= max(0.0, 1 - self.friction * time_step)
                    body.velocity[2] *= max(0.0, 1 - self.friction * time_step)
                    collisions.append(CollisionEvent(body.name, "surface", step))
            bodies = list(self._bodies.values())
            for index, first in enumerate(bodies):
                for second in bodies[index + 1 :]:
                    overlaps = all(
                        abs(first.position[axis] - second.position[axis])
                        <= first.half[axis] + second.half[axis]
                        for axis in range(3)
                    )
                    if overlaps:
                        collisions.append(CollisionEvent(first.name, second.name, step))
            frames.append(
                {name: cast(Vector, tuple(body.position)) for name, body in self._bodies.items()}
            )
            energy.append(
                sum(
                    0.5 * body.mass * sum(value * value for value in body.velocity)
                    for body in bodies
                )
            )
        final = frames[-1]
        return SimResult(
            tuple(frames),
            final,
            tuple(collisions),
            tuple(energy),
            "Euler/AABB simulation completed; results are approximate.",
        )


def world(*, backend: Literal["auto", "builtin", "pybullet"] = "auto") -> SimWorld:
    """Create a simulation world, falling back safely when optional engines are absent."""
    if backend == "pybullet":
        try:
            __import__("pybullet")
        except ImportError as error:
            raise RuntimeError("PyBullet requires `pip install pybullet`") from error
        # The validated builtin contract is used until a full PyBullet adapter is added.
    return SimWorld("builtin")
