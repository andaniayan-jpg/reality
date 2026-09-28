"""Check a door's exact sampled articulation sweep and print JSON evidence."""

from __future__ import annotations

import json

import reality


def main() -> None:
    door = reality.WorldObject("Door", reality.Bounds((0.0, 0.0, 0.0), (1.0, 0.1, 2.0)))
    world = reality.World([door], build_graph=False)
    world.articulate(
        "Door",
        joint="revolute",
        axis=(0.0, 0.0, 1.0),
        limits=(0.0, 90.0),
        pivot=(0.0, 0.0, 0.0),
    )
    result = world.can_open("Door", degrees=90.0)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
