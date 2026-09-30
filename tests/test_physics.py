from __future__ import annotations

import pytest

from reality import (
    Bounds,
    PhysicalProperties,
    PhysicsBackendUnavailableError,
    Transform,
    World,
    WorldObject,
)


def _box(
    name: str,
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
    *,
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    dynamic: bool = False,
    mass: float = 1.0,
) -> WorldObject:
    return WorldObject(
        name,
        Bounds(minimum, maximum),
        Transform(position=position),
        physical=PhysicalProperties(mass=mass, dynamic=dynamic),
    )


def _falling_world() -> World:
    return World(
        [
            _box("Floor", (-5.0, -5.0, 0.0), (5.0, 5.0, 0.1)),
            _box(
                "Box",
                (-0.1, -0.1, -0.1),
                (0.1, 0.1, 0.1),
                position=(0.0, 0.0, 2.0),
                dynamic=True,
            ),
        ]
    )


def test_gravity_moves_dynamic_body_and_static_body_remains_fixed() -> None:
    world = _falling_world()
    floor_before = world.object("Floor").transform

    result = world.simulate(seconds=0.25)

    assert result.backend == "mujoco-cpu"
    assert result.body("Box").final_transform.position[2] < 2.0
    assert world.object("Floor").transform == floor_before


def test_falling_object_rests_on_floor_and_reports_contacts() -> None:
    world = _falling_world()

    result = world.simulate(seconds=1.0)
    body = result.body("Box")

    assert body.final_transform.position[2] == pytest.approx(0.2, abs=0.02)
    assert body.fell
    assert body.contact_count > 0
    assert {
        world.object("Box").id,
        world.object("Floor").id,
    } in [set(pair) for pair in result.collision_pairs]


def test_push_causes_motion_and_stronger_push_moves_farther() -> None:
    weak = World([_box("Box", (-0.2, -0.2, 0.0), (0.2, 0.2, 0.4), dynamic=True)])
    strong = World([_box("Box", (-0.2, -0.2, 0.0), (0.2, 0.2, 0.4), dynamic=True)])

    weak_result = weak.push("Box", force=(1.0, 0.0, 0.0), duration=0.1)
    strong_result = strong.push("Box", force=(10.0, 0.0, 0.0), duration=0.1)

    assert weak_result.body("Box").motion > 0.0
    assert (
        strong_result.body("Box").final_transform.position[0]
        > (weak_result.body("Box").final_transform.position[0])
    )


def test_drop_makes_an_object_dynamic_and_observes_a_fall() -> None:
    world = World([_box("Ball", (-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))])

    result = world.drop("Ball", height=1.0, seconds=0.5)

    assert world.object("Ball").dynamic
    assert result.body("Ball").fell
    assert result.body("Ball").final_transform.position[2] < 1.0


def test_contacts_and_static_stability_are_structured() -> None:
    world = World(
        [
            _box("Table", (-1.0, -1.0, 0.0), (1.0, 1.0, 1.0)),
            _box("Vase", (-0.1, -0.1, 1.0), (0.1, 0.1, 1.4)),
        ]
    )

    contacts = world.contacts("Vase")
    stability = world.stable("Vase")

    assert any(contact.object_b_id == world.object("Table").id for contact in contacts)
    assert stability.value
    assert stability.support_objects == (world.object("Table"),)


def test_static_stability_reports_an_unsupported_center_of_mass() -> None:
    world = World(
        [
            _box("Table", (-1.0, -1.0, 0.0), (1.0, 1.0, 1.0)),
            _box(
                "Vase",
                (-0.1, -0.1, 0.0),
                (0.1, 0.1, 0.4),
                position=(1.2, 0.0, 1.0),
            ),
        ]
    )

    stability = world.stable("Vase")

    assert not stability.stable
    assert "no supporting surface" in stability.reason


def test_independent_branch_simulations_do_not_mutate_base() -> None:
    world = World([_box("Box", (-0.2, -0.2, 0.0), (0.2, 0.2, 0.4), dynamic=True)])
    branch_a = world.branch()
    branch_b = world.branch()

    branch_a.push("Box", force=(10.0, 0.0, 0.0), duration=0.1)
    branch_b.push("Box", force=(2.0, 0.0, 0.0), duration=0.1)

    assert world.object("Box").position == (0.0, 0.0, 0.0)
    assert branch_a.object("Box").position[0] > branch_b.object("Box").position[0]


def test_simulation_outcome_is_a_typed_consequence() -> None:
    world = _falling_world()
    future = world.branch()

    future.simulate(seconds=0.25)
    report = future.consequences()

    observed = [item for item in report if item.classification == "simulation_observed"]
    assert observed
    assert observed[0].what_changed == "fell"
    assert observed[0].magnitude is not None


def test_backend_unavailable_error_is_explanatory() -> None:
    world = _falling_world()
    with pytest.raises(PhysicsBackendUnavailableError, match="available backend"):
        world.simulate(seconds=0.1, backend="not-a-backend")


def test_physical_property_validation() -> None:
    with pytest.raises(ValueError, match="mass"):
        PhysicalProperties(mass=0.0)
    with pytest.raises(ValueError, match="restitution"):
        PhysicalProperties(restitution=1.1)


def test_cpu_model_cache_reuses_topology_without_leaking_dynamic_state() -> None:
    world = _falling_world()

    first = world.simulate(seconds=0.0)
    second = world.simulate(seconds=0.0)

    assert first.evidence["model_reused"] is False
    assert second.evidence["model_reused"] is True
    assert second.body("Box").final_transform.position == pytest.approx((0.0, 0.0, 2.0))


def test_cpu_physics_preserves_orientation_mapping() -> None:
    world = World(
        [
            _box(
                "Box",
                (-0.2, -0.1, -0.1),
                (0.2, 0.1, 0.1),
                position=(0.0, 0.0, 2.0),
                dynamic=True,
            )
        ]
    )
    world.update_transform("Box", Transform(position=(0.0, 0.0, 2.0), rotation=(0.2, -0.1, 0.4)))

    result = world.simulate(seconds=0.0)

    assert result.body("Box").final_transform.rotation == pytest.approx((0.2, -0.1, 0.4))


def test_force_validation_rejects_unknown_or_static_objects() -> None:
    world = World([_box("Static", (-0.1, -0.1, 0.0), (0.1, 0.1, 0.2))])

    with pytest.raises(ValueError, match="non-dynamic or unknown"):
        world.simulate(seconds=0.1, forces={"object-1": ((1.0, 0.0, 0.0), 0.1)})
