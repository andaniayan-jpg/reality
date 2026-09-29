"""Compact parallel futures over one immutable world snapshot."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

from ._accelerators import require_cuda
from ._models import Transform, Vector3
from ._state import WorldSnapshot
from .predicates import Condition, Objective, PredicateSpec

if TYPE_CHECKING:
    from ._branch import WorldBranch
    from ._models import WorldObject
    from ._state import ConsequenceSet
    from ._world import World

FloatArray: TypeAlias = NDArray[np.float64]
ValuesArray: TypeAlias = NDArray[np.bool_] | NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class BatchEvaluation:
    """Vectorized predicate values for all futures in a batch."""

    branch_count: int
    backend: str
    collisions: NDArray[np.bool_] | None
    elapsed_seconds: float
    delta_bytes: int
    predicate_values: Mapping[str, ValuesArray] = field(default_factory=dict)
    predicate_specs: tuple[PredicateSpec, ...] = ()
    _futures: BranchBatch | None = field(default=None, repr=False, compare=False)

    @property
    def values(self) -> Mapping[str, ValuesArray]:
        return self.predicate_values

    def to_dict(self) -> dict[str, object]:
        return {
            "branch_count": self.branch_count,
            "backend": self.backend,
            "collisions": self.collisions.tolist() if self.collisions is not None else None,
            "elapsed_seconds": self.elapsed_seconds,
            "delta_bytes": self.delta_bytes,
            "predicates": {key: value.tolist() for key, value in self.predicate_values.items()},
        }

    def where(self, *conditions: Condition) -> FutureSelection:
        """Return futures satisfying every hard constraint."""
        evaluation = self._ensure_predicates(tuple(condition.predicate for condition in conditions))
        mask: NDArray[np.bool_] = np.ones(self.branch_count, dtype=np.bool_)
        for condition in conditions:
            values = evaluation.predicate_values[condition.predicate.key]
            mask &= np.asarray(condition.evaluate(values), dtype=np.bool_)
        return FutureSelection(evaluation, np.flatnonzero(mask))

    def rank(
        self,
        *,
        constraints: Sequence[Condition] = (),
        objectives: Sequence[Objective] | Mapping[PredicateSpec, float] = (),
    ) -> RankedFutures:
        """Apply hard constraints, then compute a weighted soft objective score."""
        specs = [condition.predicate for condition in constraints]
        objective_items = _objectives(objectives)
        specs.extend(item.predicate for item in objective_items)
        evaluation = self._ensure_predicates(tuple(specs))
        mask: NDArray[np.bool_] = np.ones(self.branch_count, dtype=np.bool_)
        for condition in constraints:
            mask &= np.asarray(
                condition.evaluate(evaluation.predicate_values[condition.predicate.key]),
                dtype=np.bool_,
            )
        scores: NDArray[np.float64] = np.zeros(self.branch_count, dtype=np.float64)
        for objective in objective_items:
            values = np.asarray(
                evaluation.predicate_values[objective.predicate.key], dtype=np.float64
            )
            scores += objective.weight * values
        return RankedFutures(evaluation, np.flatnonzero(mask), scores, tuple(constraints))

    def score(self, objectives: Mapping[PredicateSpec, float]) -> RankedFutures:
        return self.rank(objectives=objectives)

    def best(self, count: int) -> tuple[FutureCandidate, ...]:
        return self.rank().best(count)

    def _ensure_predicates(self, specs: tuple[PredicateSpec, ...]) -> BatchEvaluation:
        missing = tuple(spec for spec in specs if spec.key not in self.predicate_values)
        if not missing or self._futures is None:
            return self
        refreshed = self._futures.evaluate(missing)
        merged = dict(self.predicate_values)
        merged.update(refreshed.predicate_values)
        return BatchEvaluation(
            self.branch_count,
            refreshed.backend,
            refreshed.collisions if refreshed.collisions is not None else self.collisions,
            self.elapsed_seconds + refreshed.elapsed_seconds,
            self.delta_bytes,
            merged,
            tuple(dict.fromkeys(self.predicate_specs + specs)),
            self._futures,
        )


@dataclass(frozen=True, slots=True)
class FutureCandidate:
    """One lazily materializable future selected from a vectorized evaluation."""

    future_index: int
    future_id: str
    deltas: Mapping[str, Mapping[str, tuple[float, float, float]]]
    predicate_values: Mapping[str, object]
    constraints_satisfied: bool
    score: float
    _futures: BranchBatch = field(repr=False, compare=False)

    def materialize(self) -> WorldBranch:
        from ._branch import WorldBranch

        branch = WorldBranch(self._futures.snapshot)
        for object_id in self._futures._ids:
            transform = self._futures._transform_for(object_id, self.future_index)
            if transform != self._futures.snapshot.objects_by_id[object_id].transform:
                branch.update_transform(object_id, transform)
        return branch

    def consequences(self) -> ConsequenceSet:
        return self.materialize().consequences()


@dataclass(frozen=True, slots=True)
class FutureSelection:
    """A filtered view of futures that retains compact shared state."""

    evaluation: BatchEvaluation
    indices: NDArray[np.int64]

    def __len__(self) -> int:
        return int(self.indices.size)

    def __getitem__(self, index: int) -> FutureCandidate:
        return self.evaluation._futures._candidate(int(self.indices[index]), self.evaluation)  # type: ignore[union-attr]

    def __iter__(self) -> Iterator[FutureCandidate]:
        for index in self.indices:
            yield self.evaluation._futures._candidate(int(index), self.evaluation)  # type: ignore[union-attr]

    def rank(
        self,
        *,
        objectives: Sequence[Objective] | Mapping[PredicateSpec, float] = (),
        constraints: Sequence[Condition] = (),
    ) -> RankedFutures:
        ranked = self.evaluation.rank(constraints=constraints, objectives=objectives)
        allowed = set(int(index) for index in ranked.indices)
        indices = np.asarray(
            [int(index) for index in self.indices if int(index) in allowed], dtype=np.int64
        )
        return RankedFutures(ranked.evaluation, indices, ranked.scores, tuple(constraints))


@dataclass(frozen=True, slots=True)
class RankedFutures:
    """Futures ordered by score after hard constraints have been applied."""

    evaluation: BatchEvaluation
    indices: NDArray[np.int64]
    scores: NDArray[np.float64]
    constraints: tuple[Condition, ...]

    def __len__(self) -> int:
        return int(self.indices.size)

    def best(self, count: int) -> tuple[FutureCandidate, ...]:
        if count < 0:
            raise ValueError("count must be non-negative")
        selected_scores = self.scores[self.indices]
        order = self.indices[np.lexsort((self.indices, -selected_scores))[:count]]
        return tuple(
            self.evaluation._futures._candidate(int(index), self.evaluation, self.scores[index])  # type: ignore[union-attr]
            for index in order
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "count": len(self),
            "indices": self.indices.tolist(),
            "scores": self.scores[self.indices].tolist(),
            "constraints": [condition.predicate.key for condition in self.constraints],
        }


class BranchBatch:
    """Many alternate transforms stored as compact arrays over one snapshot."""

    def __init__(self, world: World, count: int, *, backend: Literal["cpu", "cuda"] = "cpu"):
        if count <= 0:
            raise ValueError("branch count must be positive")
        if backend == "cuda":
            require_cuda()
        self._world = world
        self.snapshot: WorldSnapshot = world.snapshot()
        self.count = int(count)
        self.backend = backend
        self._ids = tuple(object_.id for object_ in self.snapshot.objects)
        self._index = {object_id: index for index, object_id in enumerate(self._ids)}
        self._minimum = np.asarray(
            [item.bounds.minimum for item in self.snapshot.objects], dtype=np.float64
        )
        self._maximum = np.asarray(
            [item.bounds.maximum for item in self.snapshot.objects], dtype=np.float64
        )
        self._deltas: dict[str, FloatArray] = {}
        self._rotation_deltas: dict[str, FloatArray] = {}
        self._scale_factors: dict[str, FloatArray] = {}

    def __len__(self) -> int:
        return self.count

    def __getitem__(self, index: int) -> FutureCandidate:
        if not 0 <= index < self.count:
            raise IndexError(index)
        return self._candidate(
            index, BatchEvaluation(self.count, self.backend, None, 0.0, self.delta_bytes)
        )

    @property
    def delta_bytes(self) -> int:
        return int(
            sum(array.nbytes for array in self._deltas.values())
            + sum(array.nbytes for array in self._rotation_deltas.values())
            + sum(array.nbytes for array in self._scale_factors.values())
        )

    @property
    def shared_snapshot(self) -> WorldSnapshot:
        return self.snapshot

    def randomize(
        self,
        field: str,
        *,
        x: tuple[float, float] = (0.0, 0.0),
        y: tuple[float, float] = (0.0, 0.0),
        z: tuple[float, float] = (0.0, 0.0),
        seed: int = 0,
    ) -> BranchBatch:
        if not field.endswith(".position"):
            raise ValueError("batched randomization currently supports '<object>.position'")
        object_ = self._resolve(field.removesuffix(".position"))
        self._deltas[object_.id] = self._random_vectors((x, y, z), seed)
        return self

    def randomize_position(
        self,
        reference: str,
        *,
        x: tuple[float, float],
        y: tuple[float, float],
        z: tuple[float, float] | None = None,
        seed: int = 0,
    ) -> BranchBatch:
        object_ = self._resolve(reference)
        z_range = z or (object_.position[2], object_.position[2])
        positions = self._random_vectors((x, y, z_range), seed)
        self._deltas[object_.id] = positions - np.asarray(object_.position, dtype=np.float64)
        return self

    def set_positions(self, reference: str, positions: NDArray[np.floating[Any]]) -> BranchBatch:
        object_ = self._resolve(reference)
        values = _vectors(positions, self.count, "positions")
        self._deltas[object_.id] = values - np.asarray(object_.position, dtype=np.float64)
        return self

    def set_rotations(self, reference: str, rotations: NDArray[np.floating[Any]]) -> BranchBatch:
        object_ = self._resolve(reference)
        values = _vectors(rotations, self.count, "rotations")
        self._rotation_deltas[object_.id] = values - np.asarray(object_.rotation, dtype=np.float64)
        return self

    def set_scales(self, reference: str, scales: NDArray[np.floating[Any]]) -> BranchBatch:
        object_ = self._resolve(reference)
        values = _vectors(scales, self.count, "scales")
        if np.any(values <= 0.0):
            raise ValueError("scales must be positive")
        self._scale_factors[object_.id] = values / np.asarray(object_.scale, dtype=np.float64)
        return self

    def evaluate(
        self,
        predicates: Sequence[str | PredicateSpec] = ("collision",),
    ) -> BatchEvaluation:
        started = perf_counter()
        specs = tuple(item for item in predicates if isinstance(item, PredicateSpec))
        legacy_collision = any(item == "collision" for item in predicates if isinstance(item, str))
        unsupported = {
            item for item in predicates if isinstance(item, str) and item not in {"collision"}
        }
        if unsupported:
            raise ValueError(f"unsupported batched predicates: {', '.join(sorted(unsupported))}")
        self._ensure_supported_transforms()
        values: dict[str, ValuesArray] = {}
        if self.backend == "cuda" and specs:
            values.update(self._evaluate_cuda_specs(specs))
        else:
            values.update(self._evaluate_cpu_specs(specs))
        if legacy_collision:
            values["collision"] = self._collision_any(values_backend=self.backend)
        collisions = values.get("collision")
        if collisions is None:
            collision_values = [values[spec.key] for spec in specs if spec.kind == "collision"]
            collisions = collision_values[0] if collision_values else None
        return BatchEvaluation(
            self.count,
            self.backend,
            np.asarray(collisions, dtype=np.bool_)
            if isinstance(collisions, np.ndarray) and collisions.dtype == np.bool_
            else None,
            perf_counter() - started,
            self.delta_bytes,
            values,
            tuple(specs),
            self,
        )

    def where(self, *conditions: Condition) -> FutureSelection:
        return self.evaluate(tuple(condition.predicate for condition in conditions)).where(
            *conditions
        )

    def rank(
        self,
        *,
        constraints: Sequence[Condition] = (),
        objectives: Sequence[Objective] | Mapping[PredicateSpec, float] = (),
    ) -> RankedFutures:
        return self.evaluate(tuple(condition.predicate for condition in constraints)).rank(
            constraints=constraints, objectives=objectives
        )

    def score(self, objectives: Mapping[PredicateSpec, float]) -> RankedFutures:
        return self.rank(objectives=objectives)

    def _evaluate_cpu_specs(self, specs: Sequence[PredicateSpec]) -> dict[str, ValuesArray]:
        result: dict[str, ValuesArray] = {}
        for spec in specs:
            first = self._resolve(spec.object_a).id
            if spec.kind == "visibility":
                if spec.viewer is None:
                    raise ValueError("visibility requires a viewer")
                result[spec.key] = self._visibility_cpu(first, self._resolve(spec.viewer).id)
                continue
            if spec.object_b is None:
                raise ValueError(f"{spec.kind} requires two objects")
            second = self._resolve(spec.object_b).id
            minimum_a, maximum_a = self._branch_bounds(first)
            minimum_b, maximum_b = self._branch_bounds(second)
            if spec.kind == "collision":
                result[spec.key] = np.all(
                    (minimum_a <= maximum_b) & (maximum_a >= minimum_b), axis=1
                )
            elif spec.kind == "distance":
                gaps = np.maximum.reduce(
                    [np.zeros_like(minimum_a), minimum_b - maximum_a, minimum_a - maximum_b]
                )
                result[spec.key] = np.linalg.norm(gaps, axis=1)
            else:
                raise ValueError(f"unsupported predicate {spec.kind!r}")
        return result

    def _evaluate_cuda_specs(self, specs: Sequence[PredicateSpec]) -> dict[str, ValuesArray]:
        from ._warp_ops import (
            evaluate_aabb_distances_warp,
            evaluate_aabb_intersections_warp,
            evaluate_aabb_visibility_warp,
            evaluate_branch_transforms_warp,
        )

        minimum = self._minimum.astype(np.float32, copy=False)
        maximum = self._maximum.astype(np.float32, copy=False)
        centers = (minimum + maximum) / 2.0
        extents = (maximum - minimum) / 2.0
        deltas = self._all_deltas().astype(np.float32, copy=False)
        transformed = evaluate_branch_transforms_warp(centers, deltas)
        collision_pairs = {
            tuple(
                sorted(
                    (
                        self._index[self._resolve(spec.object_a).id],
                        self._index[self._resolve(spec.object_b or "").id],
                    )
                )
            )
            for spec in specs
            if spec.kind == "collision"
        }
        pairs = np.asarray(sorted(collision_pairs), dtype=np.int32).reshape(-1, 2)
        pair_map: dict[tuple[int, int], int] = {}
        for index, pair in enumerate(pairs):
            pair_map[(int(pair[0]), int(pair[1]))] = index
        result: dict[str, ValuesArray] = {}
        intersection_values = None
        if any(spec.kind == "collision" for spec in specs):
            intersection_values = evaluate_aabb_intersections_warp(transformed, extents, pairs)
        for spec in specs:
            first = self._index[self._resolve(spec.object_a).id]
            if spec.kind == "visibility":
                viewer = self._index[self._resolve(spec.viewer or "").id]
                result[spec.key] = evaluate_aabb_visibility_warp(
                    minimum, maximum, deltas, first, viewer
                )
            else:
                second = self._index[self._resolve(spec.object_b or "").id]
                sorted_pair = sorted((first, second))
                pair_index = pair_map[(int(sorted_pair[0]), int(sorted_pair[1]))]
                if spec.kind == "collision":
                    assert intersection_values is not None
                    result[spec.key] = intersection_values[:, pair_index]
                else:
                    result[spec.key] = np.asarray(
                        evaluate_aabb_distances_warp(
                            minimum, maximum, deltas, np.asarray((first, second), dtype=np.int32)
                        ),
                        dtype=np.float64,
                    )
        return result

    def _collision_any(self, *, values_backend: str) -> NDArray[np.bool_]:
        pairs = [
            PredicateSpec("collision", self._ids[first], self._ids[second])
            for first in range(len(self._ids))
            for second in range(first + 1, len(self._ids))
        ]
        values = (
            self._evaluate_cuda_specs(pairs)
            if values_backend == "cuda"
            else self._evaluate_cpu_specs(pairs)
        )
        if not values:
            return np.zeros(self.count, dtype=np.bool_)
        return np.asarray(np.any(np.stack(list(values.values())), axis=0), dtype=np.bool_)

    def _visibility_cpu(self, target_id: str, viewer_id: str) -> NDArray[np.bool_]:
        target_min, target_max = self._branch_bounds(target_id)
        viewer_min, viewer_max = self._branch_bounds(viewer_id)
        origin = (viewer_min + viewer_max) / 2.0
        target = (target_min + target_max) / 2.0
        direction = target - origin
        visible: NDArray[np.bool_] = np.ones(self.count, dtype=np.bool_)
        for object_id in self._ids:
            if object_id in {target_id, viewer_id}:
                continue
            minimum, maximum = self._branch_bounds(object_id)
            low: NDArray[np.float64] = np.zeros(self.count, dtype=np.float64)
            high: NDArray[np.float64] = np.ones(self.count, dtype=np.float64)
            valid: NDArray[np.bool_] = np.ones(self.count, dtype=np.bool_)
            for axis in range(3):
                parallel = np.abs(direction[:, axis]) <= 1e-12
                valid &= ~parallel | (
                    (origin[:, axis] >= minimum[:, axis]) & (origin[:, axis] <= maximum[:, axis])
                )
                safe_direction = np.where(parallel, 1.0, direction[:, axis])
                first = (minimum[:, axis] - origin[:, axis]) / safe_direction
                second = (maximum[:, axis] - origin[:, axis]) / safe_direction
                low = np.maximum(low, np.minimum(first, second))
                high = np.minimum(high, np.maximum(first, second))
            visible &= ~(valid & (high >= np.maximum(low, 0.0)) & (low <= 1.0))
        return visible

    def _branch_bounds(self, object_id: str) -> tuple[FloatArray, FloatArray]:
        delta = self._deltas.get(object_id)
        if delta is None:
            delta = np.zeros((self.count, 3), dtype=np.float64)
        return self._minimum[self._index[object_id]] + delta, self._maximum[
            self._index[object_id]
        ] + delta

    def _all_deltas(self) -> FloatArray:
        result: FloatArray = np.zeros((self.count, len(self._ids), 3), dtype=np.float64)
        for object_id, delta in self._deltas.items():
            result[:, self._index[object_id], :] = delta
        return result

    def _ensure_supported_transforms(self) -> None:
        if any(np.any(value != 0.0) for value in self._rotation_deltas.values()):
            raise NotImplementedError(
                "batched rotation predicates are prepared but not yet evaluated"
            )
        if any(np.any(value != 1.0) for value in self._scale_factors.values()):
            raise NotImplementedError("batched scale predicates are prepared but not yet evaluated")

    def _resolve(self, reference: str) -> WorldObject:
        if reference in self.snapshot.objects_by_id:
            return self.snapshot.objects_by_id[reference]
        matches = self.snapshot.object_ids_by_name.get(reference, ())
        if len(matches) != 1:
            raise LookupError(f"object reference {reference!r} resolved to {len(matches)} objects")
        return self.snapshot.objects_by_id[matches[0]]

    def _random_vectors(
        self,
        ranges: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
        seed: int,
    ) -> FloatArray:
        if any(low > high for low, high in ranges):
            raise ValueError("randomization lower bounds must not exceed upper bounds")
        generator = np.random.default_rng(seed)
        return np.column_stack(
            [generator.uniform(low, high, self.count) for low, high in ranges]
        ).astype(np.float64, copy=False)

    def _transform_for(self, object_id: str, index: int) -> Transform:
        object_ = self.snapshot.objects_by_id[object_id]
        position = (
            np.asarray(object_.position)
            + self._deltas.get(object_id, np.zeros((self.count, 3)))[index]
        )
        rotation = (
            np.asarray(object_.rotation)
            + self._rotation_deltas.get(object_id, np.zeros((self.count, 3)))[index]
        )
        scale = (
            np.asarray(object_.scale)
            * self._scale_factors.get(object_id, np.ones((self.count, 3)))[index]
        )
        return Transform(
            cast(Vector3, tuple(float(value) for value in position)),
            cast(Vector3, tuple(float(value) for value in rotation)),
            cast(Vector3, tuple(float(value) for value in scale)),
        )

    def _candidate(
        self, index: int, evaluation: BatchEvaluation, score: float = 0.0
    ) -> FutureCandidate:
        deltas = {
            object_id: {
                "position": tuple(
                    float(value)
                    for value in self._deltas.get(object_id, np.zeros((self.count, 3)))[index]
                ),
                "rotation": tuple(
                    float(value)
                    for value in self._rotation_deltas.get(object_id, np.zeros((self.count, 3)))[
                        index
                    ]
                ),
                "scale": tuple(
                    float(value)
                    for value in self._scale_factors.get(object_id, np.ones((self.count, 3)))[index]
                ),
            }
            for object_id in self._ids
            if object_id in self._deltas
            or object_id in self._rotation_deltas
            or object_id in self._scale_factors
        }
        values = {key: value[index].item() for key, value in evaluation.predicate_values.items()}
        return FutureCandidate(
            index,
            f"future-{index + 1}",
            cast(dict[str, Mapping[str, Vector3]], deltas),
            values,
            True,
            float(score),
            self,
        )


class Futures(BranchBatch):
    """Named public form of :class:`BranchBatch` for parallel alternate worlds."""


def _vectors(value: NDArray[np.floating[Any]], count: int, name: str) -> FloatArray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (count, 3):
        raise ValueError(f"{name} must have shape ({count}, 3)")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain finite values")
    return array


def _objectives(
    objectives: Sequence[Objective] | Mapping[PredicateSpec, float],
) -> tuple[Objective, ...]:
    if isinstance(objectives, Mapping):
        return tuple(
            Objective(predicate, float(weight)) for predicate, weight in objectives.items()
        )
    return tuple(objectives)
