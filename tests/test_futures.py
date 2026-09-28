from __future__ import annotations

import numpy as np

import reality
from reality.predicates import collision, distance, maximize, no_collision, visibility


def _scene() -> reality.World:
    return reality.World(
        [
            reality.WorldObject("Camera", reality.Bounds((-0.2, -0.2, -0.2), (0.2, 0.2, 0.2))),
            reality.WorldObject(
                "Target",
                reality.Bounds((-0.2, -0.5, -0.5), (0.2, 0.5, 0.5)),
                reality.Transform(position=(5.0, 0.0, 0.0)),
            ),
            reality.WorldObject(
                "Blocker",
                reality.Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5)),
                reality.Transform(position=(2.5, 0.0, 0.0)),
            ),
            reality.WorldObject(
                "Other",
                reality.Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5)),
                reality.Transform(position=(0.5, 3.5, 0.5)),
            ),
        ]
    )


def test_futures_are_compact_and_lazy() -> None:
    world = _scene()
    futures = world.futures(32)
    assert len(futures) == 32
    assert futures.shared_snapshot is world.snapshot()
    assert futures.delta_bytes == 0
    assert futures[0].materialize().object("Other").mesh is world.object("Other").mesh


def test_position_randomization_is_reproducible_and_branches_are_independent() -> None:
    world = _scene()
    first = world.futures(16).randomize_position("Blocker", x=(1.0, 3.0), y=(0.0, 0.0), seed=7)
    second = world.futures(16).randomize_position("Blocker", x=(1.0, 3.0), y=(0.0, 0.0), seed=7)
    first_positions = [first[index].materialize().object("Blocker").position for index in range(16)]
    second_positions = [
        second[index].materialize().object("Blocker").position for index in range(16)
    ]
    assert first_positions == second_positions
    first.set_positions("Blocker", np.zeros((16, 3), dtype=np.float64))
    assert (
        first[0].materialize().object("Blocker").position
        != second[0].materialize().object("Blocker").position
    )
    assert world.object("Blocker").position == (2.5, 0.0, 0.0)


def test_multi_predicate_evaluation_filtering_and_ranking() -> None:
    world = _scene()
    futures = world.futures(20).randomize_position("Blocker", x=(1.0, 4.0), y=(0.0, 0.0), seed=3)
    evaluated = futures.evaluate(
        [
            collision("Blocker", "Target"),
            distance("Blocker", "Target"),
            visibility("Target", from_="Camera"),
        ]
    )
    assert evaluated.values["collision:Blocker:Target"].shape == (20,)
    assert evaluated.values["distance:Blocker:Target"].shape == (20,)
    visible = futures.evaluate([visibility("Target", from_="Camera")]).values[
        "visibility:Target:Camera"
    ]
    assert np.asarray(visible, dtype=np.bool_).shape == (20,)
    selection = evaluated.where(no_collision("Blocker", "Target"))
    assert len(selection) <= len(futures)
    ranked = evaluated.rank(objectives=[maximize(distance("Blocker", "Target"))])
    assert ranked.best(3)[0].score >= ranked.best(3)[-1].score


def test_visibility_changes_when_blocker_moves() -> None:
    world = _scene()
    futures = world.futures(2).set_positions(
        "Blocker", np.asarray([[2.5, 0.0, 0.0], [2.5, 3.0, 0.0]], dtype=np.float64)
    )
    values = futures.evaluate([visibility("Target", from_="Camera")]).values[
        "visibility:Target:Camera"
    ]
    assert values.tolist() == [False, True]


def test_selected_future_materializes_and_reports_consequences() -> None:
    world = _scene()
    futures = world.futures(4).set_positions(
        "Other", np.asarray([[0.0, 3.0, 0.0], [0.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 3.0, 0.0]])
    )
    candidate = futures.evaluate([collision("Other", "Camera")]).where(
        no_collision("Other", "Camera")
    )[0]
    branch = candidate.materialize()
    assert branch.object("Other").position == (0.0, 3.0, 0.0)
    report = candidate.consequences()
    assert report.to_dict()["consequences"]
