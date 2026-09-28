"""Navigation benchmarks for 100, 1,000, and 5,000-object scenes."""

from __future__ import annotations

from time import perf_counter

from reality import Bounds, Transform, World, WorldObject


def benchmark(object_count: int) -> dict[str, float]:
    target = WorldObject(
        "Exit",
        Bounds((-0.1, -0.1, 0.0), (0.1, 0.1, 0.2)),
        Transform(position=(20.0, 0.0, 0.0)),
    )
    mover = WorldObject(
        "Mover",
        Bounds((-0.5, -3.0, 0.0), (0.5, 3.0, 2.0)),
        Transform(position=(10.0, 10.0, 0.0)),
    )
    filler = [
        WorldObject(
            f"Object-{index}",
            Bounds((-0.25, -0.25, 0.0), (0.25, 0.25, 1.0)),
            Transform(position=(float(index % 100), 20.0 + float(index // 100), 0.0)),
        )
        for index in range(max(0, object_count - 2))
    ]
    world = World([target, mover, *filler], build_graph=False)
    path_agent = world.agent(name="PathAgent", height=1.75, radius=0.30)
    reach_agent = world.agent(name="ReachAgent", height=1.75, radius=0.30)

    started = perf_counter()
    world.navigation_grid(path_agent, "Exit")
    grid_seconds = perf_counter() - started

    started = perf_counter()
    path_agent.path_to("Exit")
    path_seconds = perf_counter() - started

    started = perf_counter()
    reach_agent.can_reach("Exit")
    reachability_seconds = perf_counter() - started

    future = world.branch()
    started = perf_counter()
    future.move("Mover", y=-10.0)
    branch_update_seconds = perf_counter() - started

    started = perf_counter()
    future.consequences()
    consequence_seconds = perf_counter() - started

    return {
        "objects": float(object_count),
        "grid": grid_seconds,
        "path": path_seconds,
        "reachability": reachability_seconds,
        "branch_update": branch_update_seconds,
        "consequences": consequence_seconds,
    }


def main() -> None:
    print("objects,grid_s,path_s,reachability_s,branch_update_s,consequences_s")
    for object_count in (100, 1_000, 5_000):
        result = benchmark(object_count)
        print(
            f"{object_count},{result['grid']:.6f},{result['path']:.6f},"
            f"{result['reachability']:.6f},{result['branch_update']:.6f},"
            f"{result['consequences']:.6f}"
        )


if __name__ == "__main__":
    main()
