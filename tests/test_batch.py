from __future__ import annotations

import numpy as np
import pytest

from reality import (
    AccelerationUnavailableError,
    Bounds,
    World,
    WorldObject,
    warp_status,
)


def test_branch_batch_shares_snapshot_and_stores_only_deltas() -> None:
    world = World(
        [
            WorldObject("Table", Bounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))),
            WorldObject("Chair", Bounds((2.0, 0.0, 0.0), (3.0, 1.0, 1.0))),
        ]
    )

    branches = world.branches(10_000)
    branches.randomize("Table.position", x=(-2.0, 2.0), seed=7)
    result = branches.evaluate(predicates=("collision",))

    assert branches.shared_snapshot is world.snapshot()
    assert result.branch_count == 10_000
    assert result.delta_bytes == 10_000 * 3 * 8
    assert result.collisions is not None
    assert result.collisions.dtype == np.bool_
    assert np.any(result.collisions)
    assert np.any(~result.collisions)


def test_batch_randomization_is_deterministic() -> None:
    world = World([WorldObject("Box", Bounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))])
    first = world.branches(100).randomize("Box.position", x=(-1.0, 1.0), seed=12)
    second = world.branches(100).randomize("Box.position", x=(-1.0, 1.0), seed=12)

    assert first.evaluate().to_dict()["collisions"] == second.evaluate().to_dict()["collisions"]


def test_cuda_request_has_useful_fallback_error_when_unavailable() -> None:
    status = warp_status()
    if status.cuda_available:
        pytest.skip("This host has CUDA; GPU kernels require the dedicated validation suite")
    world = World([WorldObject("Box", Bounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))])
    with pytest.raises(AccelerationUnavailableError, match="Select backend='cpu'"):
        world.branches(1, backend="cuda")


def test_basic_package_use_does_not_require_warp_initialization() -> None:
    world = World([WorldObject("Box", Bounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))])
    assert world.object("Box").name == "Box"
