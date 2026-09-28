from __future__ import annotations

import json

import pytest

from reality import (
    Bounds,
    MoveObject,
    RelationshipType,
    RotateObject,
    ScaleObject,
    Transform,
    World,
    WorldObject,
)


def test_snapshot_is_immutable_cached_state_and_shares_objects() -> None:
    world = _branch_world()

    snapshot = world.snapshot()

    assert snapshot is world.snapshot()
    assert snapshot.objects[0] is world.objects[0]
    assert snapshot.relationships == world.graph.all_relationships()


def test_branch_move_never_mutates_base_and_survives_later_base_change() -> None:
    world = _branch_world()
    branch = world.branch()

    branch.move("B", x=-2.0)
    world.move("B", x=5.0)

    assert branch.object("B").position == (1.0, 0.0, 0.0)
    assert world.object("B").position == (8.0, 0.0, 0.0)
    assert branch.snapshot().objects[0] is world.snapshot().objects[0]


def test_multiple_branches_are_independent_and_share_unchanged_geometry() -> None:
    world = _branch_world()
    first = world.branch()
    second = world.branch()

    first.move("B", x=-2.0)
    second.move("B", x=4.0)

    assert first.object("B").position == (1.0, 0.0, 0.0)
    assert second.object("B").position == (7.0, 0.0, 0.0)
    assert world.object("B").position == (3.0, 0.0, 0.0)
    assert first.object("A") is world.object("A") is second.object("A")
    assert first.object("B").mesh is world.object("B").mesh
    assert first.object("B").local_bounds is world.object("B").local_bounds


def test_changes_are_typed_ordered_and_structured() -> None:
    branch = _branch_world().branch()

    branch.move("A", x=1.0)
    branch.rotate("A", z=0.5)
    branch.scale("A", x=2.0)

    assert [type(change) for change in branch.changes] == [
        MoveObject,
        RotateObject,
        ScaleObject,
    ]
    assert [change.order for change in branch.changes] == [1, 2, 3]
    assert branch.changes.changes[0].parameters == {"x": 1.0, "y": 0.0, "z": 0.0}
    assert branch.changes.changes[-1].new_state.scale == (2.0, 1.0, 1.0)


def test_graph_recalculates_affected_edges_and_reuses_unaffected_edge() -> None:
    world = _branch_world()
    branch = world.branch()
    shared_edge = next(
        relationship
        for relationship in world.relationships("C")
        if relationship.type is RelationshipType.NEAR and relationship.target.name == "D"
    )

    branch.move("B", x=-2.0)

    assert branch.touching("A", "B").value
    assert any(
        relationship.type is RelationshipType.TOUCHING and relationship.target.name == "A"
        for relationship in branch.relationships("B")
    )
    assert any(edge is shared_edge for edge in branch.relationships("C"))
    assert branch.instrumentation.invalidated == 42
    assert branch.instrumentation.recalculated == 42
    assert branch.instrumentation.reused == 42


def test_snapshot_relationship_that_becomes_false_stays_suppressed() -> None:
    bounds = Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    world = World(
        [
            WorldObject("NearA", bounds),
            WorldObject("NearB", bounds, Transform(position=(1.5, 0.0, 0.0))),
        ]
    )
    branch = world.branch()

    branch.move("NearB", x=10.0)

    assert world.near("NearA", "NearB").value
    assert not branch.near("NearA", "NearB").value
    assert not any(
        relationship.type is RelationshipType.NEAR for relationship in branch.relationships("NearA")
    )


def test_consequences_describe_predicate_changes_and_serialize() -> None:
    branch = _branch_world().branch()
    branch.move("B", x=-2.0)

    report = branch.consequences()
    data = report.to_dict()
    decoded = json.loads(report.to_json())

    assert any(
        consequence.what_changed == "near"
        and consequence.previous_value is False
        and consequence.new_value is True
        for consequence in report
    )
    distance = next(consequence for consequence in report if consequence.what_changed == "distance")
    assert distance.previous_value == pytest.approx(2.0)
    assert distance.new_value == pytest.approx(0.0)
    assert distance.magnitude == pytest.approx(2.0)
    assert data["changes"][0]["type"] == "MoveObject"
    assert decoded["instrumentation"]["recalculated"] == 42


def test_visibility_change_from_moved_occluder_is_downstream() -> None:
    world = _visibility_branch_world()
    assert world.visible("Target", from_="Viewer").value
    branch = world.branch()

    branch.move("Wall", y=-10.0)
    report = branch.consequences()

    visibility = next(
        consequence for consequence in report if consequence.what_changed == "visible_from"
    )
    assert visibility.previous_value is True
    assert visibility.new_value is False
    assert visibility.classification == "downstream"
    assert branch.instrumentation.recalculated == 29


def test_world_compares_independent_branches() -> None:
    world = _branch_world()
    left = world.branch()
    right = world.branch()
    left.move("B", x=-2.0)
    right.move("B", x=2.0)

    comparison = world.compare(left, right)

    assert any(consequence.what_changed == "distance" for consequence in comparison)
    assert json.loads(comparison.to_json())["consequences"]


def _branch_world() -> World:
    mesh_reference = object()
    bounds = Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    return World(
        [
            WorldObject("A", bounds, mesh=mesh_reference),
            WorldObject("B", bounds, Transform(position=(3.0, 0.0, 0.0)), mesh=mesh_reference),
            WorldObject("C", bounds, Transform(position=(10.0, 0.0, 0.0))),
            WorldObject("D", bounds, Transform(position=(11.5, 0.0, 0.0))),
        ]
    )


def _visibility_branch_world() -> World:
    return World(
        [
            WorldObject("Viewer", Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))),
            WorldObject(
                "Target",
                Bounds((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
                Transform(position=(10.0, 0.0, 0.0)),
            ),
            WorldObject(
                "Wall",
                Bounds((-0.5, -5.0, -5.0), (0.5, 5.0, 5.0)),
                Transform(position=(5.0, 10.0, 0.0)),
            ),
        ]
    )
