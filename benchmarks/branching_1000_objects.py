"""Benchmark persistent branches against naive full object-state duplication."""

from __future__ import annotations

import copy
import gc
import tracemalloc
from time import perf_counter

from reality import Bounds, Transform, World, WorldObject

OBJECT_COUNT = 1_000
BRANCH_COUNT = 100
NAIVE_COPY_COUNT = 10


def main() -> None:
    bounds = Bounds((-0.4, -0.4, -0.4), (0.4, 0.4, 0.4))
    objects = [
        WorldObject(
            f"Object-{index}",
            bounds,
            Transform(position=(float(index % 40) * 3.0, float(index // 40) * 3.0, 0.0)),
        )
        for index in range(OBJECT_COUNT)
    ]

    started = perf_counter()
    world = World(objects)
    world_build_seconds = perf_counter() - started
    world.snapshot()  # Warm the immutable snapshot shared by every branch.

    gc.collect()
    tracemalloc.start()
    before_memory = tracemalloc.get_traced_memory()[0]
    started = perf_counter()
    branches = [world.branch() for _ in range(BRANCH_COUNT)]
    branch_seconds = perf_counter() - started
    branch_memory = tracemalloc.get_traced_memory()[0] - before_memory
    tracemalloc.stop()

    gc.collect()
    tracemalloc.start()
    before_memory = tracemalloc.get_traced_memory()[0]
    started = perf_counter()
    naive_copies = [copy.deepcopy(world.objects) for _ in range(NAIVE_COPY_COUNT)]
    naive_seconds = perf_counter() - started
    naive_memory = tracemalloc.get_traced_memory()[0] - before_memory
    tracemalloc.stop()

    branch = branches[0]
    started = perf_counter()
    branch.move("Object-0", x=0.5)
    move_seconds = perf_counter() - started
    started = perf_counter()
    report = branch.consequences()
    consequence_seconds = perf_counter() - started

    print(f"objects: {OBJECT_COUNT}")
    print(f"base world graph build: {world_build_seconds:.3f}s")
    print(f"branch creation: {branch_seconds / BRANCH_COUNT * 1_000:.3f}ms/branch")
    print(f"branch memory: {branch_memory / BRANCH_COUNT:.0f} bytes/branch")
    print(f"naive deep-copy creation: {naive_seconds / NAIVE_COPY_COUNT * 1_000:.3f}ms/copy")
    print(f"naive deep-copy memory: {naive_memory / NAIVE_COPY_COUNT:.0f} bytes/copy")
    print(f"incremental relationship recomputation: {move_seconds:.3f}s")
    print(f"consequence calculation: {consequence_seconds:.3f}s")
    print(f"consequences: {len(report)}")
    print(f"instrumentation: {branch.instrumentation}")
    assert branches and naive_copies  # Keep measured allocations alive through reporting.


if __name__ == "__main__":
    main()
