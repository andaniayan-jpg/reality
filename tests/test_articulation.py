from __future__ import annotations

import pytest

from reality import Bounds, RelationshipType, Transform, World, WorldObject


def test_unobstructed_revolute_door_and_joint_limits() -> None:
    world = World([_door()])
    door = world.articulate(
        "Door", joint="revolute", pivot=(0, 0, 0), axis=(0, 0, 1), limits=(0, 110)
    )

    result = door.can_rotate(90)
    beyond_limit = door.can_rotate(120)

    assert result.possible
    assert result.maximum_collision_free == 90
    assert door.motion_range() == (0, 110)
    assert not beyond_limit.possible
    assert beyond_limit.maximum_collision_free == 110


def test_partially_blocked_door_reports_blocker_and_graph_relationship() -> None:
    plant = WorldObject("Plant", Bounds((0.55, 0.55, 0.0), (0.75, 0.75, 2.0)))
    world = World([_door(), plant])
    door = world.articulate(
        "Door", joint="revolute", pivot=(0, 0, 0), axis=(0, 0, 1), limits=(0, 110)
    )

    result = door.can_rotate(90)

    assert not result.possible
    assert 20 < result.maximum_collision_free < 90
    assert [object_.name for object_ in result.collides_with] == ["Plant"]
    assert "Plant" in result.reason
    assert any(
        relationship.type is RelationshipType.BLOCKS_MOTION_OF
        for relationship in world.relationships("Plant")
    )


def test_prismatic_drawer_unrestricted_and_blocked_at_motion_boundary() -> None:
    drawer = WorldObject("Drawer", Bounds((0.0, 0.0, 0.0), (1.0, 0.5, 0.3)))
    world = World([drawer])
    handle = world.articulate("Drawer", joint="prismatic", axis=(1, 0, 0), limits=(0.0, 0.5))
    assert handle.can_extend(0.4).possible

    blocked_world = World([drawer, WorldObject("Pipe", Bounds((1.3, 0.0, 0.0), (1.5, 0.5, 0.3)))])
    blocked = blocked_world.articulate(
        "Drawer", joint="prismatic", axis=(1, 0, 0), limits=(0.0, 0.5)
    ).can_extend(0.4)

    assert not blocked.possible
    assert blocked.maximum_collision_free == pytest.approx(0.30, abs=0.002)
    assert blocked.collides_with[0].name == "Pipe"


def test_branch_removes_obstruction_and_reports_downstream_motion_consequence() -> None:
    plant = WorldObject("Plant", Bounds((0.55, 0.55, 0.0), (0.75, 0.75, 2.0)))
    world = World([_door(), plant])
    world.articulate("Door", joint="revolute", pivot=(0, 0, 0), axis=(0, 0, 1), limits=(0, 110))
    before = world.can_open("Door", degrees=90)
    future = world.branch()

    future.move("Plant", x=2.0)
    after = future.can_open("Door", degrees=90)
    report = future.consequences()

    assert not before.possible
    assert after.possible
    consequence = next(item for item in report if item.what_changed == "revolute_motion")
    assert consequence.classification == "downstream"
    assert consequence.new_value == 90
    assert world.object("Plant").position == (0.0, 0.0, 0.0)


def test_branch_can_introduce_motion_obstruction() -> None:
    plant = WorldObject(
        "Plant",
        Bounds((0.55, 0.55, 0.0), (0.75, 0.75, 2.0)),
        Transform(position=(2.0, 0.0, 0.0)),
    )
    world = World([_door(), plant])
    world.articulate("Door", joint="revolute", pivot=(0, 0, 0), axis=(0, 0, 1), limits=(0, 110))
    assert world.can_open("Door", degrees=90).possible
    future = world.branch()

    future.move("Plant", x=-2.0)

    assert not future.can_open("Door", degrees=90).possible
    assert any(item.what_changed == "revolute_motion" for item in future.consequences())


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"joint": "fixed", "axis": (0, 0, 1), "limits": (0, 1)}, "joint must"),
        ({"joint": "revolute", "axis": (0, 0, 0), "limits": (0, 1)}, "axis"),
        ({"joint": "prismatic", "axis": (1, 0, 0), "limits": (1, 0)}, "minimum"),
    ],
)
def test_invalid_articulation_metadata(kwargs: dict[str, object], message: str) -> None:
    world = World([_door()])

    with pytest.raises(ValueError, match=message):
        world.articulate("Door", **kwargs)  # type: ignore[arg-type]


def test_articulation_relationship_survives_a_transform_refresh() -> None:
    world = World([_door()])
    world.articulate("Door", joint="revolute", axis=(0, 0, 1), limits=(0, 90))

    world.move("Door", x=1.0)

    assert any(
        relationship.type is RelationshipType.ARTICULATED_WITH
        for relationship in world.relationships("Door")
    )


def _door() -> WorldObject:
    return WorldObject("Door", Bounds((0.0, 0.0, 0.0), (1.0, 0.1, 2.0)))
