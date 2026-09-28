"""Find collision-free table layouts with exact, reproducible Futures search."""

from __future__ import annotations

import reality
from reality.predicates import distance, maximize, no_collision


def main() -> None:
    box = reality.Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    world = reality.World(
        [
            reality.WorldObject("Table", box),
            reality.WorldObject("Sofa", box, reality.Transform(position=(3.0, 0.0, 0.0))),
            reality.WorldObject("Column", box, reality.Transform(position=(1.0, 0.0, 0.0))),
        ]
    )
    result = world.explore(
        possibilities=10_000,
        changes=[reality.position("Table", x=(-2.0, 2.0), y=(-2.0, 2.0), z=(0.0, 0.0))],
        constraints=[no_collision("Table", "Column")],
        objectives=[maximize(distance("Table", "Sofa"))],
        seed=42,
        best=5,
        # Keep demo stdout strictly machine-readable even on hosts where Warp logs
        # CUDA probing notices to stdout. `backend="auto"` remains the API default.
        backend="cpu",
    )
    print(result.to_json())


if __name__ == "__main__":
    main()
