from __future__ import annotations

import json
from pathlib import Path

import pytest

from reality import Bounds, RelationshipType, Transform, World, WorldObject


def test_straight_unobstructed_path_and_world_reachable_api() -> None:
    world = _world_with_target()
    person = world.agent(name="Person", height=1.75, radius=0.30)

    path = person.path_to("Exit")
    reachable = world.reachable("Person", "Exit")

    assert path.reachable
    assert path.distance == pytest.approx(6.0)
    assert path.points[0] == pytest.approx(person.position)
    assert path.points[-1][:2] == pytest.approx(world.object("Exit").bounds.center[:2])
    assert path.points[-1][2] == person.position[2]
    assert reachable.reachable
    assert reachable.required_clearance == pytest.approx(0.60)
    assert any(
        relationship.type is RelationshipType.REACHABLE_BY
        for relationship in world.relationships(person)
    )


def test_blocked_path_explains_blocking_object() -> None:
    world = _world_with_target(_barrier("Shelf"))
    person = world.agent(name="Person", height=1.75, radius=0.30)

    path = person.path_to("Exit")

    assert not path.reachable
    assert path.distance is None
    assert [object_.name for object_ in path.blocked_by] == ["Shelf"]
    assert "Shelf" in path.reason
    assert any(
        relationship.type is RelationshipType.BLOCKS_PATH_OF and relationship.source.name == "Shelf"
        for relationship in world.relationships(person)
    )


def test_astar_finds_alternate_route_around_obstacle() -> None:
    obstacle = WorldObject("Island", Bounds((2.5, -0.75, 0.0), (3.5, 0.75, 2.0)))
    world = _world_with_target(obstacle)
    person = world.agent(name="Person", height=1.75, radius=0.30)

    path = person.path_to("Exit")

    assert path.reachable
    assert path.distance is not None and path.distance > 6.0
    assert any(abs(point[1]) > 1.0 for point in path.points)


def test_doorway_width_depends_only_on_agent_dimensions() -> None:
    door = WorldObject("Door", Bounds((0.0, 0.0, 0.0), (0.8, 0.1, 2.1)))
    world = World([door])
    human = world.agent(name="Human", height=1.75, radius=0.30)
    wheelchair = world.agent(name="Wheelchair", height=1.30, radius=0.45)

    human_result = human.can_pass("Door")
    wheelchair_result = wheelchair.can_pass("Door")

    assert human_result.can_pass
    assert not wheelchair_result.can_pass
    assert wheelchair_result.required_width == pytest.approx(0.90)
    assert wheelchair_result.available_width == pytest.approx(0.80)


def test_same_corridor_has_different_results_for_agent_sizes() -> None:
    world = _corridor_world()
    child = world.agent(name="Child", height=1.20, radius=0.20)
    adult = world.agent(name="Adult", height=1.75, radius=0.30)
    wheelchair = world.agent(name="Wheelchair", height=1.30, radius=0.45)
    robot = world.agent(name="LargeRobot", height=1.80, radius=0.65)

    assert child.can_reach("Exit").reachable
    assert adult.can_reach("Exit").reachable
    assert wheelchair.can_reach("Exit").reachable
    assert not robot.can_reach("Exit").reachable


def test_clearance_reports_narrowest_point_and_nearby_obstacles() -> None:
    world = _corridor_world()
    person = world.agent(name="Person", height=1.75, radius=0.30)

    clearance = person.clearance_to("Exit")

    assert clearance.reachable
    assert clearance.minimum_clearance == pytest.approx(0.30)
    assert clearance.narrowest_point is not None
    assert {object_.name for object_ in clearance.nearby_blocking_objects} == {
        "NorthWall",
        "SouthWall",
    }


def test_target_at_agent_position_returns_zero_length_path() -> None:
    target = WorldObject("Here", Bounds((-0.1, -0.1, 0.0), (0.1, 0.1, 0.2)))
    world = World([target])
    agent = world.agent(name="Person", height=1.75, radius=0.30)

    result = agent.path_to("Here")

    assert result.reachable
    assert result.distance == 0.0
    assert result.points == ((0.0, 0.0, 0.0),)


def test_debug_visualization_exports_svg(tmp_path: Path) -> None:
    world = _world_with_target(_barrier("Shelf"))
    path = world.agent(name="Person", height=1.75, radius=0.30).path_to("Exit")

    output = path.export_debug(tmp_path / "navigation.svg")

    content = output.read_text(encoding="utf-8")
    assert content.startswith("<svg")
    assert "Shelf" in content
    assert "stroke-dasharray" in content


def test_branch_movement_can_make_exit_unreachable_without_changing_base() -> None:
    shelf = WorldObject(
        "Shelf",
        Bounds((-0.5, -3.0, 0.0), (0.5, 3.0, 2.0)),
        Transform(position=(3.0, 6.0, 0.0)),
    )
    world = _world_with_target(shelf)
    person = world.agent(name="Person", height=1.75, radius=0.30)
    assert person.can_reach("Exit").reachable
    future = world.branch()

    future.move("Shelf", y=-6.0)
    future_result = future.agent("Person").can_reach("Exit")
    report = future.consequences()

    assert not future_result.reachable
    assert person.can_reach("Exit").reachable
    consequence = next(item for item in report if item.what_changed == "reachable_by")
    assert consequence.previous_value is True
    assert consequence.new_value is False
    assert consequence.classification == "downstream"
    assert "Shelf" in consequence.reason
    assert json.loads(report.to_json())["consequences"]


def test_branch_movement_can_restore_reachability() -> None:
    world = _world_with_target(_barrier("Shelf"))
    person = world.agent(name="Person", height=1.75, radius=0.30)
    assert not person.can_reach("Exit").reachable
    future = world.branch()

    future.move("Shelf", y=6.0)

    assert future.agent("Person").can_reach("Exit").reachable
    assert any(
        consequence.what_changed == "reachable_by"
        and consequence.previous_value is False
        and consequence.new_value is True
        for consequence in future.consequences()
    )


def _world_with_target(*objects: WorldObject) -> World:
    target = WorldObject(
        "Exit",
        Bounds((-0.1, -0.1, 0.0), (0.1, 0.1, 0.2)),
        Transform(position=(6.0, 0.0, 0.0)),
    )
    return World([target, *objects], navigation_resolution=0.25)


def _barrier(name: str) -> WorldObject:
    return WorldObject(name, Bounds((2.5, -3.0, 0.0), (3.5, 3.0, 2.0)))


def _corridor_world() -> World:
    target = WorldObject(
        "Exit",
        Bounds((-0.1, -0.1, 0.0), (0.1, 0.1, 0.2)),
        Transform(position=(6.0, 0.0, 0.0)),
    )
    north = WorldObject("NorthWall", Bounds((-2.0, 0.6, 0.0), (8.0, 3.0, 2.5)))
    south = WorldObject("SouthWall", Bounds((-2.0, -3.0, 0.0), (8.0, -0.6, 2.5)))
    return World([target, north, south], navigation_resolution=0.1)
