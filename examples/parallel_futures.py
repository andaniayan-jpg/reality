"""Deterministic 10,000-candidate future search over a programmatic room."""

from __future__ import annotations

import reality
from reality.predicates import collision, distance, maximize, no_collision, visibility


def make_world() -> reality.World:
    box = reality.Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    return reality.World(
        [
            reality.WorldObject("Camera", box, reality.Transform(position=(-4.0, 0.0, 1.5))),
            reality.WorldObject("Television", box, reality.Transform(position=(4.0, 0.0, 1.5))),
            reality.WorldObject("Table", box, reality.Transform(position=(0.0, 0.0, 0.5))),
            reality.WorldObject("Sofa", box, reality.Transform(position=(0.0, 2.0, 0.5))),
            reality.WorldObject("Column", box, reality.Transform(position=(1.0, 0.0, 1.0))),
        ]
    )


def main() -> None:
    world = make_world()
    futures = world.futures(10_000).randomize_position(
        "Table", x=(-1.0, 1.0), y=(-0.75, 0.75), z=(0.5, 0.5), seed=20260928
    )
    evaluation = futures.evaluate(
        [
            collision("Table", "Column"),
            distance("Table", "Sofa"),
            visibility("Television", from_="Camera"),
        ]
    )
    ranked = evaluation.rank(
        constraints=[no_collision("Table", "Column")],
        objectives=[maximize(distance("Table", "Sofa"))],
    )
    best = ranked.best(3)
    print(
        {
            "candidates": len(futures),
            "valid": len(ranked),
            "top_scores": [candidate.score for candidate in ranked.best(3)],
        }
    )
    for candidate in best:
        print(candidate.future_id, candidate.score, candidate.deltas)
    if best:
        print("selected consequences", best[0].consequences().to_json())


if __name__ == "__main__":
    main()
