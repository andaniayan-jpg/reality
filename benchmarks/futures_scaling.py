"""CPU scaling measurements for compact futures (no CUDA required)."""

from __future__ import annotations

import json
import time
import tracemalloc

import reality
from reality.predicates import collision, distance


def scene(object_count: int = 1_000) -> reality.World:
    box = reality.Bounds((-0.05, -0.05, -0.05), (0.05, 0.05, 0.05))
    objects = [
        reality.WorldObject("Anchor", box, reality.Transform(position=(0.0, 0.0, 0.0))),
        reality.WorldObject("Mover", box, reality.Transform(position=(2.0, 0.0, 0.0))),
    ]
    objects.extend(
        reality.WorldObject(
            f"Static-{index}", box, reality.Transform(position=(index % 50, index // 50, 0.0))
        )
        for index in range(object_count - 2)
    )
    return reality.World(objects)


def measure(world: reality.World, count: int) -> dict[str, float | int]:
    tracemalloc.start()
    start = time.perf_counter()
    futures = world.futures(count).randomize_position(
        "Mover", x=(1.0, 3.0), y=(-1.0, 1.0), z=(0.0, 0.0), seed=17
    )
    creation = time.perf_counter() - start
    start = time.perf_counter()
    _ = futures.evaluate([collision("Mover", "Anchor"), distance("Mover", "Anchor")])
    evaluation_seconds = time.perf_counter() - start
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return {
        "futures": count,
        "creation_seconds": creation,
        "evaluation_seconds": evaluation_seconds,
        "delta_bytes": futures.delta_bytes,
        "peak_traced_bytes": peak,
        "reused_snapshot_objects": len(futures.shared_snapshot.objects),
    }


def main() -> None:
    world = scene()
    rows = [measure(world, count) for count in (100, 1_000, 10_000, 50_000, 100_000)]
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
