"""Value objects that define the public geometry vocabulary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import atan2, cos, isfinite, sin, sqrt
from types import MappingProxyType
from typing import Any, Generic, Literal, TypeAlias, TypeVar

import numpy as np
from numpy.typing import NDArray

Vector3: TypeAlias = tuple[float, float, float]
T = TypeVar("T")


def _vector3(value: Vector3, *, field_name: str) -> Vector3:
    if len(value) != 3:
        raise ValueError(f"{field_name} must contain exactly three values")
    converted = tuple(float(component) for component in value)
    if not all(isfinite(component) for component in converted):
        raise ValueError(f"{field_name} must contain only finite values")
    return converted  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class Transform:
    """Position, XYZ Euler rotation (radians), and scale of a world object."""

    position: Vector3 = (0.0, 0.0, 0.0)
    rotation: Vector3 = (0.0, 0.0, 0.0)
    scale: Vector3 = (1.0, 1.0, 1.0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", _vector3(self.position, field_name="position"))
        object.__setattr__(self, "rotation", _vector3(self.rotation, field_name="rotation"))
        scale = _vector3(self.scale, field_name="scale")
        if any(component == 0.0 for component in scale):
            raise ValueError("scale components must be non-zero")
        object.__setattr__(self, "scale", scale)

    @property
    def matrix(self) -> NDArray[np.float64]:
        """Return the homogeneous matrix for ``T @ Rz @ Ry @ Rx @ S``."""
        x, y, z = self.rotation
        cx, sx = cos(x), sin(x)
        cy, sy = cos(y), sin(y)
        cz, sz = cos(z), sin(z)
        rotation = np.array(
            [
                [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
                [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
                [-sy, cy * sx, cy * cx],
            ],
            dtype=np.float64,
        )
        matrix: NDArray[np.float64] = np.eye(4, dtype=np.float64)
        matrix[:3, :3] = rotation @ np.diag(self.scale)
        matrix[:3, 3] = self.position
        return matrix

    def apply(self, point: Vector3) -> Vector3:
        """Apply this transform to one point."""
        result = self.matrix[:3, :3] @ np.asarray(_vector3(point, field_name="point"))
        result += np.asarray(self.position)
        return tuple(float(component) for component in result)  # type: ignore[return-value]

    @classmethod
    def from_matrix(cls, matrix: NDArray[np.floating[Any]]) -> Transform:
        """Create a transform from an affine 4×4 matrix without shear."""
        array = np.asarray(matrix, dtype=np.float64)
        if array.shape != (4, 4) or not np.all(np.isfinite(array)):
            raise ValueError("matrix must be a finite 4x4 matrix")
        if not np.allclose(array[3], (0.0, 0.0, 0.0, 1.0), atol=1e-9):
            raise ValueError("matrix must be affine")
        basis = array[:3, :3]
        scale = np.linalg.norm(basis, axis=0)
        if np.any(scale < 1e-12):
            raise ValueError("matrix has a zero scale axis")
        rotation = basis / scale
        if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-7):
            raise ValueError("matrix contains shear, which Transform does not represent")
        if np.linalg.det(rotation) < 0:
            scale[0] *= -1
            rotation[:, 0] *= -1
        y = atan2(-rotation[2, 0], sqrt(rotation[0, 0] ** 2 + rotation[1, 0] ** 2))
        if abs(cos(y)) > 1e-8:
            x = atan2(rotation[2, 1], rotation[2, 2])
            z = atan2(rotation[1, 0], rotation[0, 0])
        else:
            x = atan2(-rotation[1, 2], rotation[1, 1])
            z = 0.0
        return cls(
            position=tuple(float(value) for value in array[:3, 3]),  # type: ignore[arg-type]
            rotation=(x, y, z),
            scale=tuple(float(value) for value in scale),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class Bounds:
    """An axis-aligned bounding box in a single coordinate space."""

    minimum: Vector3
    maximum: Vector3

    def __post_init__(self) -> None:
        minimum = _vector3(self.minimum, field_name="minimum")
        maximum = _vector3(self.maximum, field_name="maximum")
        if any(lower > upper for lower, upper in zip(minimum, maximum, strict=True)):
            raise ValueError("minimum must not exceed maximum on any axis")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    @classmethod
    def from_points(cls, points: NDArray[np.floating[Any]]) -> Bounds:
        """Return the tight axis-aligned bounds around one or more points."""
        array = np.asarray(points, dtype=np.float64)
        if array.ndim != 2 or array.shape[1] != 3 or len(array) == 0:
            raise ValueError("points must be a non-empty Nx3 array")
        return cls(tuple(array.min(axis=0)), tuple(array.max(axis=0)))

    @property
    def center(self) -> Vector3:
        return tuple((low + high) / 2 for low, high in zip(self.minimum, self.maximum, strict=True))  # type: ignore[return-value]

    @property
    def extents(self) -> Vector3:
        return tuple(high - low for low, high in zip(self.minimum, self.maximum, strict=True))  # type: ignore[return-value]

    @property
    def volume(self) -> float:
        x, y, z = self.extents
        return x * y * z

    @property
    def corners(self) -> tuple[Vector3, ...]:
        return tuple(
            (x, y, z)
            for x in (self.minimum[0], self.maximum[0])
            for y in (self.minimum[1], self.maximum[1])
            for z in (self.minimum[2], self.maximum[2])
        )

    def transformed(self, transform: Transform) -> Bounds:
        """Return the enclosing world-axis-aligned bounds after a transform."""
        return Bounds.from_points(np.asarray([transform.apply(corner) for corner in self.corners]))

    def intersects(self, other: Bounds) -> bool:
        return all(
            self.minimum[index] <= other.maximum[index]
            and self.maximum[index] >= other.minimum[index]
            for index in range(3)
        )

    def contains(self, other: Bounds) -> bool:
        return all(
            self.minimum[index] <= other.minimum[index]
            and self.maximum[index] >= other.maximum[index]
            for index in range(3)
        )

    def distance_to(self, other: Bounds) -> float:
        """Return Euclidean separation, or zero when the boxes touch/intersect."""
        gaps = [
            max(
                0.0,
                other.minimum[index] - self.maximum[index],
                self.minimum[index] - other.maximum[index],
            )
            for index in range(3)
        ]
        return sqrt(sum(gap * gap for gap in gaps))

    def touching(self, other: Bounds) -> bool:
        """Return whether boxes meet at a boundary without overlapping in volume."""
        if not self.intersects(other):
            return False
        overlaps = [
            min(self.maximum[index], other.maximum[index])
            - max(self.minimum[index], other.minimum[index])
            for index in range(3)
        ]
        return any(overlap == 0.0 for overlap in overlaps) and all(
            overlap >= 0.0 for overlap in overlaps
        )


@dataclass(frozen=True, slots=True)
class PhysicalProperties:
    """Explicit rigid-body inputs; no semantic material properties are inferred."""

    mass: float = 1.0
    dynamic: bool = False
    collision_shape: Literal["box"] = "box"
    friction: float = 0.5
    restitution: float = 0.0
    center_of_mass: Vector3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if not isfinite(self.mass) or self.mass <= 0.0:
            raise ValueError("mass must be finite and positive")
        if not isfinite(self.friction) or self.friction < 0.0:
            raise ValueError("friction must be finite and non-negative")
        if not isfinite(self.restitution) or not 0.0 <= self.restitution <= 1.0:
            raise ValueError("restitution must be between zero and one")
        object.__setattr__(
            self,
            "center_of_mass",
            _vector3(self.center_of_mass, field_name="center_of_mass"),
        )


@dataclass(frozen=True, slots=True)
class WorldObject:
    """A named object with backend-owned mesh data and backend-neutral geometry."""

    name: str
    local_bounds: Bounds
    transform: Transform = field(default_factory=Transform)
    id: str = ""
    mesh: Any = field(default=None, compare=False, repr=False)
    physical: PhysicalProperties = field(default_factory=PhysicalProperties)
    _world_bounds: Bounds = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        object.__setattr__(self, "_world_bounds", self.local_bounds.transformed(self.transform))

    @property
    def position(self) -> Vector3:
        return self.transform.position

    @property
    def rotation(self) -> Vector3:
        return self.transform.rotation

    @property
    def scale(self) -> Vector3:
        return self.transform.scale

    @property
    def bounds(self) -> Bounds:
        """World-space axis-aligned bounds calculated from local mesh bounds."""
        return self._world_bounds

    @property
    def mass(self) -> float:
        return self.physical.mass

    @property
    def dynamic(self) -> bool:
        return self.physical.dynamic

    @property
    def collision_shape(self) -> str:
        return self.physical.collision_shape

    @property
    def friction(self) -> float:
        return self.physical.friction

    @property
    def restitution(self) -> float:
        return self.physical.restitution

    @property
    def center_of_mass(self) -> Vector3:
        return self.physical.center_of_mass


@dataclass(frozen=True, slots=True)
class PredicateResult(Generic[T]):
    """A typed spatial-query result with measurements and inspectable evidence."""

    value: T
    measurement: float | None
    units: str | None
    reason: str
    objects: tuple[WorldObject, ...]
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    @property
    def distance(self) -> float | None:
        """Convenient alias for distance-like measurements."""
        return self.measurement

    @property
    def visibility_fraction(self) -> float | None:
        """Fraction of deterministic target samples visible to a visibility query."""
        value = self.evidence.get("visibility_fraction")
        return float(value) if isinstance(value, int | float) else None

    @property
    def occluding_objects(self) -> tuple[WorldObject, ...]:
        """Objects that blocked one or more visibility rays, if applicable."""
        value = self.evidence.get("occluding_objects", ())
        return value if isinstance(value, tuple) else ()
