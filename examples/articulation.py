"""Explicit joints, swept motion, and branch consequences."""

from reality import Bounds, World, WorldObject


def main() -> None:
    world = World(
        [
            WorldObject("Room", Bounds((-3.0, -3.0, -0.1), (3.0, 3.0, -0.01))),
            WorldObject("Door", Bounds((0.0, 0.0, 0.0), (1.0, 0.08, 2.0))),
            WorldObject("Plant", Bounds((0.5, 0.5, 0.0), (0.8, 0.8, 1.0))),
            WorldObject("Cabinet", Bounds((-3.0, 1.0, 0.0), (-2.0, 2.0, 1.0))),
            WorldObject("Drawer", Bounds((-1.8, 0.8, 0.4), (-1.2, 1.2, 0.8))),
            WorldObject("Obstacle", Bounds((-0.9, 0.8, 0.4), (-0.7, 1.2, 0.8))),
        ]
    )
    door = world.articulate(
        "Door", joint="revolute", pivot=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), limits=(0, 110)
    )
    drawer = world.articulate("Drawer", joint="prismatic", axis=(1.0, 0.0, 0.0), limits=(0.0, 0.4))
    print(door.can_rotate(90).to_dict())
    print(drawer.can_extend(0.4).to_dict())

    future = world.branch()
    future.move("Plant", x=1.0)
    for consequence in future.consequences():
        print(consequence)


if __name__ == "__main__":
    main()
