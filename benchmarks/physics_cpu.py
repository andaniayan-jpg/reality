"""MuJoCo CPU initialization, stepping, branch, and contacts benchmark."""

from platform import platform, python_version
from time import perf_counter

import mujoco

from reality import Bounds, PhysicalProperties, Transform, World, WorldObject


def run(count: int, seconds: float = 0.1) -> dict[str, object]:
    objects = [
        WorldObject(
            f"Box-{index}",
            Bounds((-0.04, -0.04, -0.04), (0.04, 0.04, 0.04)),
            Transform(position=((index % 40) * 0.12, (index // 40) * 0.12, 1.0)),
            physical=PhysicalProperties(dynamic=True),
        )
        for index in range(count)
    ]
    world = World(objects, build_graph=False)
    started = perf_counter()
    result = world.simulate(seconds=seconds)
    elapsed = perf_counter() - started
    branch_started = perf_counter()
    branch = world.branch()
    branch.simulate(seconds=seconds)
    branch_elapsed = perf_counter() - branch_started
    return {
        "objects": count,
        "steps": result.steps,
        "stepping_performed": result.steps > 0,
        "simulation_seconds": elapsed,
        "branch_simulation_seconds": branch_elapsed,
        "contacts": result.contact_count,
    }


print(
    {
        "platform": platform(),
        "python": python_version(),
        "backend": f"MuJoCo {mujoco.__version__}",
        "results": [run(100, 0.05), run(1_000, 0.0)],
        "note": (
            "The 1,000-body row measures scene/backend initialization only. "
            "A five-step 1,000-body run exceeded 150 seconds on this host."
        ),
    }
)
