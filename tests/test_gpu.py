from __future__ import annotations

import numpy as np
import pytest

import reality
from reality._warp_ops import (
    evaluate_aabb_distances_cpu,
    evaluate_aabb_distances_warp,
    evaluate_aabb_intersections_cpu,
    evaluate_aabb_intersections_warp,
    evaluate_branch_transforms_cpu,
    evaluate_branch_transforms_warp,
)


def _cuda_or_skip() -> None:
    status = reality.warp_status()
    if not status.cuda_available:
        pytest.skip(f"CUDA validation unavailable: {status.reason}")


def test_branch_transform_warp_matches_cpu_oracle() -> None:
    _cuda_or_skip()
    generator = np.random.default_rng(20260928)
    base = generator.normal(size=(11, 3)).astype(np.float32)
    deltas = generator.normal(size=(37, 11, 3)).astype(np.float32)

    expected = evaluate_branch_transforms_cpu(base, deltas)
    actual = evaluate_branch_transforms_warp(base, deltas)

    assert np.allclose(actual, expected, rtol=1e-5, atol=1e-5)
    assert float(np.max(np.abs(actual - expected))) <= 1e-5


def test_aabb_intersection_warp_matches_cpu_oracle() -> None:
    _cuda_or_skip()
    generator = np.random.default_rng(20260928)
    centers = generator.normal(size=(23, 9, 3)).astype(np.float32)
    extents = generator.uniform(0.05, 0.5, size=(9, 3)).astype(np.float32)
    pairs = np.asarray([(0, 1), (1, 2), (2, 8), (3, 7), (4, 5)], dtype=np.int32)

    expected = evaluate_aabb_intersections_cpu(centers, extents, pairs)
    actual = evaluate_aabb_intersections_warp(centers, extents, pairs)

    assert np.array_equal(actual, expected)


def test_aabb_distance_warp_matches_cpu_oracle() -> None:
    _cuda_or_skip()
    generator = np.random.default_rng(20260928)
    minimum = generator.normal(size=(9, 3)).astype(np.float32)
    maximum = minimum + generator.uniform(0.05, 0.5, size=(9, 3)).astype(np.float32)
    deltas = generator.normal(size=(23, 9, 3)).astype(np.float32)
    pair = np.asarray((2, 7), dtype=np.int32)

    expected = evaluate_aabb_distances_cpu(minimum, maximum, deltas, pair)
    actual = evaluate_aabb_distances_warp(minimum, maximum, deltas, pair)

    assert np.allclose(actual, expected, rtol=1e-5, atol=1e-5)


def test_cuda_branch_batch_uses_custom_kernels() -> None:
    _cuda_or_skip()
    world = reality.World(
        [
            reality.WorldObject("Mover", reality.Bounds((0, 0, 0), (1, 1, 1))),
            reality.WorldObject("Obstacle", reality.Bounds((2, 0, 0), (3, 1, 1))),
        ]
    )
    result = (
        world.branches(128, backend="cuda")
        .randomize("Mover.position", x=(-2, 2), seed=9)
        .evaluate()
    )
    assert result.backend == "cuda"
    assert result.collisions is not None
