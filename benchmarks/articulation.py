"""Reproducible swept-articulation benchmark."""

from time import perf_counter

from reality import Bounds, World, WorldObject

world = World(
    [
        WorldObject("Door", Bounds((0.0, 0.0, 0.0), (1.0, 0.05, 2.0))),
        *[
            WorldObject(
                f"Obstacle-{index}",
                Bounds((3.0 + index, 3.0, 0.0), (3.5 + index, 3.5, 1.0)),
            )
            for index in range(1_000)
        ],
    ],
    build_graph=False,
)
world.articulate(
    "Door", joint="revolute", axis=(0.0, 0.0, 1.0), pivot=(0.0, 0.0, 0.0), limits=(0, 110)
)
started = perf_counter()
world.can_open("Door", degrees=110)
print({"objects": 1_001, "seconds": perf_counter() - started, "resolution_degrees": 1.0})
