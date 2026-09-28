"""Generate labelled candidate data using exact Reality predicates, never a heuristic."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

import reality
from reality.predicates import distance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=10_000)
    parser.add_argument("--output", type=Path, default=Path("reality_explore_dataset.npz"))
    args = parser.parse_args()
    box = reality.Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    world = reality.World(
        [
            reality.WorldObject("Mover", box),
            reality.WorldObject("Goal", box, reality.Transform(position=(4.0, 0.0, 0.0))),
        ],
        build_graph=False,
    )
    futures = world.futures(args.samples).randomize_position(
        "Mover", x=(-2.0, 2.0), y=(-2.0, 2.0), z=(0.0, 0.0), seed=42
    )
    labels = np.asarray(futures.evaluate([distance("Mover", "Goal")]).values["distance:Mover:Goal"])
    positions = futures._deltas[world.object("Mover").id] + np.asarray(
        world.object("Mover").position
    )
    np.savez(args.output, features=positions, targets=labels)
    print({"output": str(args.output), "samples": args.samples, "label": "exact_aabb_distance"})


if __name__ == "__main__":
    main()
