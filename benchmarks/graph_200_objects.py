"""A repeatable baseline for current O(n²) graph construction behavior."""

from __future__ import annotations

from time import perf_counter

from reality import Bounds, Transform, World, WorldObject

COUNT = 200


def main() -> None:
    bounds = Bounds((-0.4, -0.4, -0.4), (0.4, 0.4, 0.4))
    objects = [
        WorldObject(
            f"Object-{index}",
            bounds,
            Transform(position=(float(index % 20) * 2.0, float(index // 20) * 2.0, 0.0)),
        )
        for index in range(COUNT)
    ]

    started = perf_counter()
    world = World(objects)
    graph_seconds = perf_counter() - started

    started = perf_counter()
    world.move("Object-0", x=0.25)
    incremental_seconds = perf_counter() - started

    print(f"objects: {COUNT}")
    print(f"graph build: {graph_seconds:.3f}s")
    print(f"move / incident-edge refresh: {incremental_seconds:.3f}s")
    print(f"relationships: {len(world.relationships('Object-0'))}")


if __name__ == "__main__":
    main()
