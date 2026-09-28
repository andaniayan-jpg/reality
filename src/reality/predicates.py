"""Typed predicate and objective specifications for parallel future evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast


@dataclass(frozen=True, slots=True)
class PredicateSpec:
    """A declarative, batch-evaluable spatial metric."""

    kind: Literal["collision", "distance", "visibility"]
    object_a: str
    object_b: str | None = None
    viewer: str | None = None

    @property
    def key(self) -> str:
        if self.kind == "visibility":
            if self.viewer is None:
                raise ValueError("visibility requires a viewer")
            return f"visibility:{self.object_a}:{self.viewer}"
        if self.object_b is None:
            raise ValueError(f"{self.kind} requires two objects")
        return f"{self.kind}:{self.object_a}:{self.object_b}"

    def __eq__(self, other: object) -> Condition | bool:  # type: ignore[override]
        if isinstance(other, PredicateSpec):
            return (
                self.kind == other.kind
                and self.object_a == other.object_a
                and self.object_b == other.object_b
                and self.viewer == other.viewer
            )
        return Condition(self, "eq", other)

    def __gt__(self, value: float) -> Condition:
        return Condition(self, "gt", value)

    def __ge__(self, value: float) -> Condition:
        return Condition(self, "ge", value)

    def __lt__(self, value: float) -> Condition:
        return Condition(self, "lt", value)

    def __le__(self, value: float) -> Condition:
        return Condition(self, "le", value)


@dataclass(frozen=True, slots=True)
class Condition:
    """A hard constraint applied to one predicate's vectorized values."""

    predicate: PredicateSpec
    operator: Literal["eq", "gt", "ge", "lt", "le"]
    expected: object

    def evaluate(self, values: object) -> Any:
        import numpy as np

        actual = np.asarray(values)
        if self.operator == "eq":
            return actual == self.expected
        if self.operator == "gt":
            return actual > self.expected
        if self.operator == "ge":
            return actual >= self.expected
        if self.operator == "lt":
            return actual < self.expected
        return actual <= self.expected


@dataclass(frozen=True, slots=True)
class Objective:
    """A weighted soft objective over one predicate vector."""

    predicate: PredicateSpec
    weight: float = 1.0


def collision(a: str, b: str) -> PredicateSpec:
    return PredicateSpec("collision", a, b)


def distance(a: str, b: str) -> PredicateSpec:
    return PredicateSpec("distance", a, b)


def visibility(target: str, *, from_: str) -> PredicateSpec:
    return PredicateSpec("visibility", target, viewer=from_)


def maximize(predicate: PredicateSpec, *, weight: float = 1.0) -> Objective:
    return Objective(predicate, abs(float(weight)))


def minimize(predicate: PredicateSpec, *, weight: float = 1.0) -> Objective:
    return Objective(predicate, -abs(float(weight)))


def no_collision(a: str, b: str) -> Condition:
    return cast(Condition, collision(a, b) == False)  # noqa: E712
