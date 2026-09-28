from __future__ import annotations

from math import pi, sqrt

import numpy as np
import pytest

from reality import Bounds, Transform, WorldObject


def test_transform_matrix_and_apply() -> None:
    transform = Transform(position=(3, 4, 5), rotation=(0, 0, pi / 2), scale=(2, 1, 1))

    assert transform.apply((1, 0, 0)) == pytest.approx((3, 6, 5))
    assert transform.matrix.shape == (4, 4)


def test_transform_round_trips_without_shear() -> None:
    transform = Transform(position=(3, 4, 5), rotation=(0.2, -0.4, 0.7), scale=(2, 3, 4))

    assert Transform.from_matrix(transform.matrix).matrix == pytest.approx(transform.matrix)


def test_transform_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="non-zero"):
        Transform(scale=(1, 0, 1))
    with pytest.raises(ValueError, match="shear"):
        Transform.from_matrix(np.array([[1, 0.5, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]))


def test_bounds_geometry_and_transform() -> None:
    bounds = Bounds((-1, -2, -3), (1, 2, 3))

    assert bounds.center == (0, 0, 0)
    assert bounds.extents == (2, 4, 6)
    assert bounds.volume == 48
    assert bounds.transformed(Transform(position=(3, 0, 0))).minimum == (2, -2, -3)


def test_bounds_relationships_and_distance() -> None:
    first = Bounds((0, 0, 0), (1, 1, 1))
    touching = Bounds((1, 0, 0), (2, 1, 1))
    separate = Bounds((3, 4, 0), (4, 5, 1))

    assert first.intersects(touching)
    assert first.distance_to(touching) == 0
    assert first.distance_to(separate) == pytest.approx(sqrt(13))
    assert Bounds((-1, -1, -1), (2, 2, 2)).contains(first)


def test_world_object_exposes_transform_conveniences() -> None:
    object_ = WorldObject("Cube", Bounds((0, 0, 0), (1, 1, 1)), Transform(position=(2, 3, 4)))

    assert object_.position == (2, 3, 4)
    assert object_.rotation == (0, 0, 0)
    assert object_.scale == (1, 1, 1)
    assert object_.bounds == Bounds((2, 3, 4), (3, 4, 5))
