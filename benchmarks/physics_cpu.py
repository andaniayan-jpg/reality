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
    cold_started = perf_counter()
    result = world.simulate(seconds=seconds)
    cold_elapsed = perf_counter() - cold_started
    warm_started = perf_counter()
    warm = world.simulate(seconds=0.0)
    warm_elapsed = perf_counter() - warm_started
    branch_started = perf_counter()
    branch = world.branch()
    branch.simulate(seconds=seconds)
    branch_elapsed = perf_counter() - branch_started
    return {
        "objects": count,
        "steps": result.steps,
        "stepping_performed": result.steps > 0,
        "cold_simulation_seconds": cold_elapsed,
        "warm_reset_seconds": warm_elapsed,
        "cold_model_setup_seconds": result.evidence["model_setup_seconds"],
        "warm_model_setup_seconds": warm.evidence["model_setup_seconds"],
        "warm_model_reused": warm.evidence["model_reused"],
        "stepping_seconds": result.evidence["stepping_seconds"],
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
