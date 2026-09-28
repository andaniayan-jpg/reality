from __future__ import annotations

import pytest

from reality import Bounds, Transform, World, WorldObject


@pytest.fixture
def example_world() -> World:
    """A programmatic scene: no test needs an external binary asset."""
    box = Bounds((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    return World(
        [
            WorldObject("Table", box, Transform(position=(0.0, 0.0, 0.0))),
            WorldObject("Chair", box, Transform(position=(2.0, 0.0, 0.0))),
            WorldObject("Lamp", box, Transform(position=(0.0, 0.0, 2.0))),
            WorldObject("Room", Bounds((-5.0, -5.0, -1.0), (5.0, 5.0, 5.0))),
            WorldObject("Overlap", box, Transform(position=(0.5, 0.0, 0.0))),
        ]
    )
