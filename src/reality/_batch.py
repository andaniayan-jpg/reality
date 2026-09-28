"""Delta-array branch batches sharing one immutable world snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Literal

import numpy as np
from numpy.typing import NDArray

from ._accelerators import require_cuda
from ._state import WorldSnapshot

if TYPE_CHECKING:
    from ._world import World


@dataclass(frozen=True, slots=True)
class BatchEvaluation:
    branch_count: int
    backend: str
    collisions: NDArray[np.bool_] | None
    elapsed_seconds: float
    delta_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "branch_count": self.branch_count,
            "backend": self.backend,
            "collisions": self.collisions.tolist() if self.collisions is not None else None,
            "elapsed_seconds": self.elapsed_seconds,
            "delta_bytes": self.delta_bytes,
        }


class BranchBatch:
    """Many alternate translations as compact arrays over one shared snapshot.

    Memory layout is one immutable base bounds array plus one ``N x 3`` float64
    translation array for each object changed in the batch. No ``World`` or mesh
    is copied per branch.
    """

    def __init__(self, world: World, count: int, *, backend: Literal["cpu", "cuda"] = "cpu"):
        if count <= 0:
            raise ValueError("branch count must be positive")
        if backend == "cuda":
            require_cuda()
        self.snapshot: WorldSnapshot = world.snapshot()
        self.count = int(count)
        self.backend = backend
        self._ids = tuple(object_.id for object_ in self.snapshot.objects)
        self._index = {object_id: index for index, object_id in enumerate(self._ids)}
        self._minimum = np.asarray([item.bounds.minimum for item in self.snapshot.objects])
        self._maximum = np.asarray([item.bounds.maximum for item in self.snapshot.objects])
        self._deltas: dict[str, NDArray[np.float64]] = {}

    @property
    def delta_bytes(self) -> int:
        return sum(array.nbytes for array in self._deltas.values())

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
        reference = field.removesuffix(".position")
        object_ = self.snapshot.objects_by_id.get(reference)
        if object_ is None:
            matches = self.snapshot.object_ids_by_name.get(reference, ())
            if len(matches) != 1:
                raise LookupError(
                    f"object reference {reference!r} resolved to {len(matches)} objects"
                )
            object_ = self.snapshot.objects_by_id[matches[0]]
        ranges = (x, y, z)
        if any(low > high for low, high in ranges):
            raise ValueError("randomization lower bounds must not exceed upper bounds")
        generator = np.random.default_rng(seed)
        delta = np.column_stack(
            [generator.uniform(low, high, self.count) for low, high in ranges]
        ).astype(np.float64, copy=False)
        self._deltas[object_.id] = delta
        return self

    def evaluate(self, *, predicates: tuple[str, ...] = ("collision",)) -> BatchEvaluation:
        unsupported = set(predicates) - {"collision"}
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValueError(f"unsupported batched predicates: {names}")
        if self.backend == "cuda":
            return self._evaluate_cuda(predicates)
        started = perf_counter()
        collisions = np.zeros(self.count, dtype=np.bool_) if "collision" in predicates else None
        for first in range(len(self._ids)):
            first_delta = self._deltas.get(self._ids[first])
            if first_delta is None:
                first_delta = np.zeros((self.count, 3), dtype=np.float64)
            first_minimum = self._minimum[first] + first_delta
            first_maximum = self._maximum[first] + first_delta
            for second in range(first + 1, len(self._ids)):
                second_delta = self._deltas.get(self._ids[second])
                if second_delta is None:
                    second_delta = np.zeros((self.count, 3), dtype=np.float64)
                second_minimum = self._minimum[second] + second_delta
                second_maximum = self._maximum[second] + second_delta
                overlap = np.all(
                    (first_minimum <= second_maximum) & (first_maximum >= second_minimum),
                    axis=1,
                )
                if collisions is not None:
                    collisions |= overlap
        return BatchEvaluation(
            self.count,
            self.backend,
            collisions,
            perf_counter() - started,
            self.delta_bytes,
        )

    def _evaluate_cuda(self, predicates: tuple[str, ...]) -> BatchEvaluation:
        """Evaluate compact deltas through both custom Reality Warp kernels."""
        from ._warp_ops import (
            evaluate_aabb_intersections_warp,
            evaluate_branch_transforms_warp,
        )

        object_count = len(self._ids)
        deltas = np.zeros((self.count, object_count, 3), dtype=np.float32)
        for object_id, values in self._deltas.items():
            deltas[:, self._index[object_id], :] = values
        minimum = self._minimum.astype(np.float32, copy=False)
        maximum = self._maximum.astype(np.float32, copy=False)
        centers = (minimum + maximum) / 2.0
        half_extents = (maximum - minimum) / 2.0
        pair_indices = np.asarray(
            [
                (first, second)
                for first in range(object_count)
                for second in range(first + 1, object_count)
            ],
            dtype=np.int32,
        ).reshape(-1, 2)
        if pair_indices.size == 0:
            return BatchEvaluation(
                self.count,
                self.backend,
                np.zeros(self.count, dtype=np.bool_) if "collision" in predicates else None,
                0.0,
                self.delta_bytes,
            )
        transformed = evaluate_branch_transforms_warp(centers, deltas)
        overlaps = evaluate_aabb_intersections_warp(transformed, half_extents, pair_indices)
        collisions = np.any(overlaps, axis=1) if "collision" in predicates else None
        return BatchEvaluation(
            self.count,
            self.backend,
            collisions,
            0.0,
            self.delta_bytes,
        )
