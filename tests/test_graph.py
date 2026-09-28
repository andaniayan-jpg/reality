from __future__ import annotations

from reality import Bounds, RelationshipType, Transform, World, WorldObject


def test_graph_creates_inside_contains_and_vertical_relationships(example_world: World) -> None:
    table_relationships = example_world.relationships("Table")
    lamp_relationships = example_world.relationships("Lamp")

    assert any(
        relationship.type is RelationshipType.INSIDE and relationship.target.name == "Room"
        for relationship in table_relationships
    )
    assert any(
        relationship.type is RelationshipType.CONTAINS and relationship.target.name == "Table"
        for relationship in example_world.relationships("Room")
    )
    assert any(
        relationship.type is RelationshipType.ABOVE and relationship.target.name == "Table"
        for relationship in lamp_relationships
    )
    assert any(
        relationship.type is RelationshipType.BELOW and relationship.target.name == "Lamp"
        for relationship in table_relationships
    )


def test_move_invalidates_and_rebuilds_only_incident_relationships(example_world: World) -> None:
    assert any(
        relationship.type is RelationshipType.NEAR
        for relationship in example_world.relationships("Chair")
    )
    table_edges = example_world.relationships("Table")
    unaffected_edge = next(
        relationship
        for relationship in example_world.relationships("Lamp")
        if relationship.type is RelationshipType.ABOVE and relationship.target.name == "Table"
    )

    example_world.move("Chair", x=10.0)

    assert not any(
        relationship.type is RelationshipType.NEAR
        for relationship in example_world.relationships("Chair")
    )
    assert any(
        relationship.type is RelationshipType.INSIDE and relationship.target.name == "Room"
        for relationship in example_world.relationships("Table")
    )
    assert unaffected_edge in example_world.relationships("Lamp")
    assert table_edges != example_world.relationships("Table")


def test_touching_relationship_is_created() -> None:
    bounds = Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    world = World(
        [
            WorldObject("Left", bounds),
            WorldObject("Right", bounds, Transform(position=(1.0, 0.0, 0.0))),
        ]
    )

    assert world.touching("Left", "Right").value
    assert any(
        relationship.type is RelationshipType.TOUCHING and relationship.target.name == "Right"
        for relationship in world.relationships("Left")
    )


def test_visible_when_no_object_blocks_line_of_sight() -> None:
    world = _visibility_world()

    result = world.visible("Television", from_="Sofa")

    assert result.value
    assert result.visibility_fraction == 1.0
    assert result.occluding_objects == ()
    assert any(
        relationship.type is RelationshipType.VISIBLE_FROM and relationship.target.name == "Sofa"
        for relationship in world.relationships("Television")
    )


def test_visible_reports_blocking_objects() -> None:
    world = _visibility_world(include_wall=True)

    result = world.visible("Television", from_="Sofa")

    assert not result.value
    assert result.visibility_fraction == 0.0
    assert [object_.name for object_ in result.occluding_objects] == ["Wall"]
    assert not any(
        relationship.type is RelationshipType.VISIBLE_FROM
        for relationship in world.relationships("Television")
    )


def _visibility_world(*, include_wall: bool = False) -> World:
    objects = [
        WorldObject("Sofa", Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))),
        WorldObject(
            "Television",
            Bounds((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
            Transform(position=(10.0, 0.0, 0.0)),
        ),
    ]
    if include_wall:
        objects.append(WorldObject("Wall", Bounds((4.5, -5.0, -5.0), (5.5, 5.0, 5.0))))
    return World(objects)
