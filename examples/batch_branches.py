"""Evaluate 10,000 alternate translations without copying the world."""

from reality import Bounds, World, WorldObject

world = World(
    [
        WorldObject("Table", Bounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))),
        WorldObject("Chair", Bounds((2.0, 0.0, 0.0), (3.0, 1.0, 1.0))),
    ]
)
branches = world.branches(10_000)
branches.randomize("Table.position", x=(-2.0, 2.0), seed=42)
result = branches.evaluate(predicates=("collision",))
print(
    {
        "branches": result.branch_count,
        "colliding": int(result.collisions.sum()) if result.collisions is not None else None,
        "delta_bytes": result.delta_bytes,
        "seconds": result.elapsed_seconds,
    }
)
