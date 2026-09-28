"""Exact, deterministic search over compact Reality futures."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Literal, TypeAlias

import numpy as np

from ._batch import BatchEvaluation, FutureCandidate, Futures, RankedFutures
from .predicates import Condition, Objective, PredicateSpec

if TYPE_CHECKING:
    from ._world import World

Range: TypeAlias = tuple[float, float]


def _range(value: Range, *, name: str) -> Range:
    if len(value) != 2:
        raise ValueError(f"{name} must contain exactly two values")
    lower, upper = (float(item) for item in value)
    if not np.isfinite(lower) or not np.isfinite(upper) or lower > upper:
        raise ValueError(f"{name} must be finite and ordered as (minimum, maximum)")
    return lower, upper


@dataclass(frozen=True, slots=True)
class PositionSearchChange:
    """A deterministic position search domain for one object."""

    object: str
    x: Range
    y: Range
    z: Range | None = None

    def __post_init__(self) -> None:
        if not self.object.strip():
            raise ValueError("search object reference must not be empty")
        object.__setattr__(self, "x", _range(self.x, name="x"))
        object.__setattr__(self, "y", _range(self.y, name="y"))
        if self.z is not None:
            object.__setattr__(self, "z", _range(self.z, name="z"))


def position(
    object: str,
    *,
    x: Range,
    y: Range,
    z: Range | None = None,
) -> PositionSearchChange:
    """Create a compact position-domain specification for :meth:`World.explore`."""
    return PositionSearchChange(object, x, y, z)


@dataclass(frozen=True, slots=True)
class ExplorationResult:
    """Exact search evidence and only the selected, lazily materializable futures."""

    possibilities: int
    seed: int
    backend: Literal["cpu", "cuda"]
    elapsed_seconds: float
    futures: Futures
    evaluation: BatchEvaluation
    ranked: RankedFutures
    candidates: tuple[FutureCandidate, ...]
    changes: tuple[PositionSearchChange, ...]
    constraints: tuple[Condition, ...]
    objectives: tuple[Objective, ...]

    @property
    def valid_count(self) -> int:
        """Number of candidates satisfying every exact hard constraint."""
        return len(self.ranked)

    @property
    def best(self) -> tuple[FutureCandidate, ...]:
        """Best selected futures, ordered by exact score then stable candidate index."""
        return self.candidates

    def to_dict(self) -> dict[str, object]:
        """Serialize selected exact evidence without dumping every candidate array.

        Full per-candidate predicate arrays remain available through ``evaluation``
        for in-process analysis. Keeping them out of the transport form preserves
        the compact-result guarantee for searches with millions of possibilities.
        """
        return {
            "possibilities": self.possibilities,
            "seed": self.seed,
            "backend": self.backend,
            "elapsed_seconds": self.elapsed_seconds,
            "valid_count": self.valid_count,
            "changes": [
                {"object": change.object, "x": change.x, "y": change.y, "z": change.z}
                for change in self.changes
            ],
            "constraints": [condition.predicate.key for condition in self.constraints],
            "objectives": [
                {"predicate": objective.predicate.key, "weight": objective.weight}
                for objective in self.objectives
            ],
            "evaluation": {
                "branch_count": self.evaluation.branch_count,
                "backend": self.evaluation.backend,
                "elapsed_seconds": self.evaluation.elapsed_seconds,
                "delta_bytes": self.evaluation.delta_bytes,
                "predicate_keys": sorted(self.evaluation.predicate_values),
            },
            "ranking": {
                "valid_count": self.valid_count,
                "selected_count": len(self.candidates),
                "constraints": [condition.predicate.key for condition in self.ranked.constraints],
            },
            "candidates": [
                {
                    "future_id": candidate.future_id,
                    "future_index": candidate.future_index,
                    "score": candidate.score,
                    "constraints_satisfied": candidate.constraints_satisfied,
                    "deltas": candidate.deltas,
                    "predicates": candidate.predicate_values,
                }
                for candidate in self.candidates
            ],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize exact search evidence without materializing every candidate."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def explore(
    world: World,
    *,
    possibilities: int,
    changes: Sequence[PositionSearchChange | Mapping[str, object]],
    constraints: Sequence[Condition] = (),
    objectives: Sequence[Objective] = (),
    seed: int = 0,
    best: int = 10,
    backend: Literal["cpu", "cuda"] | None = None,
) -> ExplorationResult:
    """Run exact, deterministic spatial search over compact future deltas.

    The result never materializes every possible world.  CPU is always available;
    CUDA is selected automatically only when Reality reports a usable CUDA device.
    """
    if possibilities <= 0:
        raise ValueError("possibilities must be positive")
    if best <= 0:
        raise ValueError("best must be positive")
    resolved_changes = tuple(_change(change) for change in changes)
    if not resolved_changes:
        raise ValueError("changes must include at least one position search domain")
    if any(not isinstance(condition, Condition) for condition in constraints):
        raise TypeError("constraints must contain reality.predicates.Condition values")
    if any(not isinstance(objective, Objective) for objective in objectives):
        raise TypeError("objectives must contain reality.predicates.Objective values")
    selected_backend = backend or ("cuda" if _cuda_available() else "cpu")
    started = perf_counter()
    futures = world.futures(possibilities, backend=selected_backend)
    sequence = np.random.SeedSequence(seed)
    for change, child_seed in zip(
        resolved_changes, sequence.spawn(len(resolved_changes)), strict=True
    ):
        futures.randomize_position(
            change.object,
            x=change.x,
            y=change.y,
            z=change.z,
            seed=int(child_seed.generate_state(1, dtype=np.uint64)[0]),
        )
    specs: list[PredicateSpec] = [condition.predicate for condition in constraints]
    specs.extend(objective.predicate for objective in objectives)
    evaluation = futures.evaluate(tuple(specs))
    ranked = evaluation.rank(constraints=constraints, objectives=objectives)
    candidates = ranked.best(best)
    return ExplorationResult(
        possibilities,
        int(seed),
        selected_backend,
        perf_counter() - started,
        futures,
        evaluation,
        ranked,
        candidates,
        resolved_changes,
        tuple(constraints),
        tuple(objectives),
    )


def _cuda_available() -> bool:
    from ._accelerators import warp_status

    return warp_status().cuda_available


def _change(value: PositionSearchChange | Mapping[str, object]) -> PositionSearchChange:
    if isinstance(value, PositionSearchChange):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("changes must contain PositionSearchChange or mapping values")
    reference = value.get("object", value.get("reference"))
    x = value.get("x")
    y = value.get("y")
    z = value.get("z")
    if (
        not isinstance(reference, str)
        or not isinstance(x, tuple | list)
        or not isinstance(y, tuple | list)
    ):
        raise ValueError("change mappings require object, x=(min, max), and y=(min, max)")
    if z is not None and not isinstance(z, tuple | list):
        raise ValueError("change mapping z must be (min, max) when provided")
    return PositionSearchChange(
        reference,
        tuple(float(item) for item in x),  # type: ignore[arg-type]
        tuple(float(item) for item in y),  # type: ignore[arg-type]
        tuple(float(item) for item in z) if z is not None else None,  # type: ignore[arg-type]
    )
