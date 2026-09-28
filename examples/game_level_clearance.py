"""Emit exact game-character route and clearance evidence as JSON."""

from __future__ import annotations

import json

import reality


def main() -> None:
    world = reality.World(
        [
            reality.WorldObject("Exit", reality.Bounds((5.0, -0.5, 0.0), (5.5, 0.5, 2.0))),
            reality.WorldObject("Pillar", reality.Bounds((2.0, -0.5, 0.0), (3.0, 0.5, 2.0))),
        ],
        build_graph=False,
    )
    player = world.agent(name="Player", position=(0.0, 0.0, 0.0), height=1.8, radius=0.3)
    path = player.path_to("Exit")
    reachability = player.can_reach("Exit")
    print(
        json.dumps(
            {
                "path": path.to_dict(),
                "reachability": {
                    "reachable": reachability.reachable,
                    "required_clearance": reachability.required_clearance,
                    "available_clearance": reachability.available_clearance,
                    "reason": reachability.reason,
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
