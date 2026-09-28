"""Plan a dimensioned robot route using deterministic world geometry."""

from __future__ import annotations

import json

import reality


def main() -> None:
    world = reality.World(
        [
            reality.WorldObject("Dock", reality.Bounds((4.0, -0.4, 0.0), (4.6, 0.4, 1.0))),
            reality.WorldObject("Crate", reality.Bounds((1.8, -0.4, 0.0), (2.6, 0.4, 1.4))),
        ],
        build_graph=False,
    )
    robot = world.agent(name="Robot", position=(0.0, 0.0, 0.0), height=1.0, radius=0.25)
    path = robot.path_to("Dock")
    clearance = robot.clearance_to("Dock")
    print(
        json.dumps(
            {
                "path": path.to_dict(),
                "clearance": {
                    "reachable": clearance.reachable,
                    "minimum_clearance": clearance.minimum_clearance,
                    "narrowest_point": clearance.narrowest_point,
                    "reason": clearance.reason,
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
