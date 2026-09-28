from __future__ import annotations

import pytest

from reality import AmbiguousObjectError, Bounds, ObjectNotFoundError, World, WorldObject


def test_object_lookup_and_stable_assigned_ids(example_world: World) -> None:
    chair = example_world.object("Chair")

    assert chair.id == "object-2"
    assert example_world.object("object-2") is chair
    assert example_world.object(chair) is chair
    with pytest.raises(ObjectNotFoundError):
        example_world.object("Missing")


def test_duplicate_names_require_id() -> None:
    world = World([WorldObject("Cube", Bounds((0, 0, 0), (1, 1, 1)))])
    second = world.add(WorldObject("Cube", Bounds((2, 0, 0), (3, 1, 1))))

    with pytest.raises(AmbiguousObjectError):
        world.object("Cube")
    assert world.object(second.id) is second


def test_distance_has_measurement_evidence_and_objects(example_world: World) -> None:
    result = example_world.distance("Chair", "Table")

    assert result.value == result.distance == pytest.approx(1.0)
    assert result.measurement == pytest.approx(1.0)
    assert result.units == "m"
    assert result.objects[0].name == "Chair"
    assert "bounding boxes" in result.reason
    assert "bounds_a" in result.evidence


def test_intersects_predicate(example_world: World) -> None:
    assert example_world.intersects("Table", "Overlap").value
    assert not example_world.intersects("Table", "Chair").value


def test_vertical_predicates_report_clearance(example_world: World) -> None:
    above = example_world.above("Lamp", "Table")
    below = example_world.below("Table", "Lamp")

    assert above.value and below.value
    assert above.measurement == below.measurement == pytest.approx(1.0)
    assert above.units == "m"


def test_inside_predicate(example_world: World) -> None:
    assert example_world.inside("Table", "Room").value
    assert not example_world.inside("Room", "Table").value


def test_near_predicate_uses_explicit_threshold(example_world: World) -> None:
    nearby = example_world.near("Table", "Chair")
    distant = example_world.near("Table", "Chair", within=0.9)

    assert nearby.value
    assert nearby.distance == pytest.approx(1.0)
    assert nearby.evidence["threshold"] == 1.0
    assert not distant.value
    with pytest.raises(ValueError, match="non-negative"):
        example_world.near("Table", "Chair", within=-1)
