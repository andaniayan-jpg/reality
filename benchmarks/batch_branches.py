"""Actual CPU delta-batch timings; CUDA is reported only when available."""

from platform import platform, processor, python_version
from time import perf_counter

from reality import Bounds, World, WorldObject, warp_status

world = World(
    [
        WorldObject("Mover", Bounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))),
        WorldObject("Obstacle", Bounds((2.0, 0.0, 0.0), (3.0, 1.0, 1.0))),
    ]
)
rows = []
for count in (1, 10, 100, 1_000, 10_000):
    started = perf_counter()
    branches = world.branches(count).randomize("Mover.position", x=(-2.0, 2.0), seed=4)
    result = branches.evaluate()
    rows.append(
        {
            "branches": count,
            "end_to_end_seconds": perf_counter() - started,
            "evaluation_seconds": result.elapsed_seconds,
            "delta_bytes": result.delta_bytes,
        }
    )
print(
    {
        "platform": platform(),
        "python": python_version(),
        "cpu": processor(),
        "warp": warp_status(),
        "warmup": "none",
        "repetitions": 1,
        "rows": rows,
    }
)
