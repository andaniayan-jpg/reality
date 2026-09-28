"""Run deterministic fixed-step CPU physics through the backend-neutral API."""

from reality import Bounds, PhysicalProperties, Transform, World, WorldObject


def main() -> None:
    world = World(
        [
            WorldObject("Floor", Bounds((-5.0, -5.0, 0.0), (5.0, 5.0, 0.1))),
            WorldObject(
                "Ball",
                Bounds((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1)),
                Transform(position=(0.0, 0.0, 2.0)),
                physical=PhysicalProperties(dynamic=True),
            ),
        ]
    )
    result = world.simulate(seconds=1.0)
    print(result.body("Ball"))
    print(world.stable("Ball"))


if __name__ == "__main__":
    main()
