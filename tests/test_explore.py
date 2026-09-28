from __future__ import annotations

import json

import reality
from reality.predicates import collision, distance, maximize, no_collision


def _world() -> reality.World:
    box = reality.Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    return reality.World(
        [
            reality.WorldObject("Table", box),
            reality.WorldObject("Chair", box, reality.Transform(position=(3.0, 0.0, 0.0))),
            reality.WorldObject("Wall", box, reality.Transform(position=(1.5, 0.0, 0.0))),
        ]
    )


def test_explore_is_deterministic_and_materializes_only_selected_futures() -> None:
    world = _world()
    kwargs = {
        "possibilities": 100,
        "changes": [reality.position("Table", x=(-2.0, 2.0), y=(0.0, 0.0), z=(0.0, 0.0))],
        "constraints": [no_collision("Table", "Wall")],
        "objectives": [maximize(distance("Table", "Chair"))],
        "seed": 42,
        "best": 3,
        "backend": "cpu",
    }
    first = world.explore(**kwargs)
    second = world.explore(**kwargs)

    assert first.valid_count > 0
    assert [item.future_index for item in first.best] == [item.future_index for item in second.best]
    assert [item.score for item in first.best] == [item.score for item in second.best]
    assert first.futures.shared_snapshot is world.snapshot()
    assert first.best[0].materialize().object("Chair") is world.object("Chair")
    assert world.object("Table").position == (0.0, 0.0, 0.0)


def test_explore_exposes_exact_evidence_and_accepts_mapping_changes() -> None:
    world = _world()
    result = world.explore(
        possibilities=12,
        changes=[{"object": "Table", "x": (-2.0, 2.0), "y": (0.0, 0.0), "z": (0.0, 0.0)}],
        constraints=[no_collision("Table", "Wall")],
        objectives=[maximize(distance("Table", "Chair"))],
        seed=9,
        best=2,
        backend="cpu",
    )

    payload = result.to_dict()
    assert payload["valid_count"] == result.valid_count
    assert len(payload["candidates"]) == 2
    assert all(candidate.constraints_satisfied for candidate in result.best)
    assert json.loads(result.to_json())["seed"] == 9


def test_explore_rejects_invalid_input() -> None:
    world = _world()
    try:
        world.explore(possibilities=1, changes=[], backend="cpu")
    except ValueError as error:
        assert "changes" in str(error)
    else:  # pragma: no cover - assertion readability
        raise AssertionError("expected an informative empty-change error")

    try:
        world.explore(
            possibilities=1,
            changes=[reality.position("Table", x=(1.0, -1.0), y=(0.0, 0.0))],
            backend="cpu",
        )
    except ValueError as error:
        assert "ordered" in str(error)
    else:  # pragma: no cover - assertion readability
        raise AssertionError("expected an informative invalid-range error")


def test_explore_only_ranks_candidates_that_pass_constraints() -> None:
    world = _world()
    result = world.explore(
        possibilities=16,
        changes=[reality.position("Table", x=(1.0, 2.0), y=(0.0, 0.0), z=(0.0, 0.0))],
        constraints=[no_collision("Table", "Wall")],
        objectives=[maximize(distance("Table", "Chair"))],
        seed=4,
        best=16,
        backend="cpu",
    )
    values = result.evaluation.values[collision("Table", "Wall").key]
    assert all(not values[candidate.future_index] for candidate in result.best)
