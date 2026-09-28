"""Measure exact Explore generation, predicates, filtering, ranking, and output costs."""

from __future__ import annotations

import json
import tracemalloc
from time import perf_counter

import reality
from reality.predicates import distance, maximize, no_collision


def scene() -> reality.World:
    box = reality.Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    return reality.World(
        [
            reality.WorldObject("Mover", box),
            reality.WorldObject("Obstacle", box, reality.Transform(position=(1.5, 0.0, 0.0))),
            reality.WorldObject("Goal", box, reality.Transform(position=(4.0, 0.0, 0.0))),
        ],
        build_graph=False,
    )


def measure(world: reality.World, possibilities: int) -> dict[str, float | int | str | None]:
    tracemalloc.start()
    started = perf_counter()
    futures = world.futures(possibilities, backend="cpu").randomize_position(
        "Mover", x=(-2.0, 3.0), y=(-1.0, 1.0), z=(0.0, 0.0), seed=42
    )
    generation = perf_counter() - started
    started = perf_counter()
    evaluation = futures.evaluate([distance("Mover", "Goal")])
    kernels = perf_counter() - started
    started = perf_counter()
    ranked = evaluation.rank(
        constraints=[no_collision("Mover", "Obstacle")],
        objectives=[maximize(distance("Mover", "Goal"))],
    )
    filtering_and_ranking = perf_counter() - started
    started = perf_counter()
    candidates = ranked.best(10)
    download = perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return {
        "possibilities": possibilities,
        "backend": "cpu",
        "generation_seconds": generation,
        "upload_seconds": None,
        "kernel_seconds": kernels,
        "filtering_ranking_seconds": filtering_and_ranking,
        "download_seconds": download,
        "end_to_end_seconds": generation + kernels + filtering_and_ranking + download,
        "delta_bytes": futures.delta_bytes,
        "peak_traced_bytes": peak,
        "valid_candidates": len(ranked),
        "selected": len(candidates),
    }


def main() -> None:
    world = scene()
    rows = [measure(world, count) for count in (100, 1_000, 10_000, 100_000, 1_000_000)]
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
