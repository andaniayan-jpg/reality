"""Deterministic CPU navigation for dimensioned agents."""

from __future__ import annotations

import heapq
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import ceil, hypot, inf, isfinite
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, TypeAlias

from ._models import Bounds, Vector3, WorldObject

if TYPE_CHECKING:
    from ._world import ObjectReference, World

GridCell: TypeAlias = tuple[int, int]
Point2: TypeAlias = tuple[float, float]
NavigationKey: TypeAlias = tuple[str, str]
NavigationRecord: TypeAlias = tuple[str, str, "PathResult"]


@dataclass(frozen=True, slots=True)
class NavigationObstacle:
    """A projected obstacle used by a navigation query."""

    object: WorldObject
    minimum: Point2
    maximum: Point2


@dataclass(frozen=True, slots=True)
class NavigationDebug:
    """Geometry required to inspect a path query without a graphical UI."""

    minimum: Point2
    maximum: Point2
    resolution: float
    obstacles: tuple[NavigationObstacle, ...]
    start: Vector3
    target: Vector3


@dataclass(frozen=True, slots=True)
class PathResult:
    """Structured output of deterministic A* navigation."""

    reachable: bool
    points: tuple[Vector3, ...]
    distance: float | None
    minimum_clearance: float | None
    narrowest_point: Vector3 | None
    blocked_by: tuple[WorldObject, ...]
    reason: str
    evidence: Mapping[str, object] = field(default_factory=dict)
    _debug: NavigationDebug | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    @property
    def value(self) -> bool:
        return self.reachable

    def to_dict(self) -> dict[str, object]:
        return {
            "reachable": self.reachable,
            "points": [list(point) for point in self.points],
            "distance": self.distance,
            "minimum_clearance": self.minimum_clearance,
            "narrowest_point": list(self.narrowest_point) if self.narrowest_point else None,
            "blocked_by": [{"id": object_.id, "name": object_.name} for object_ in self.blocked_by],
            "reason": self.reason,
            "evidence": _serializable_evidence(self.evidence),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def export_debug(self, path: str | Path) -> Path:
        """Write a standalone SVG of walkable space, obstacles, and the path."""
        if self._debug is None:
            raise ValueError("debug geometry is unavailable for this result")
        destination = Path(path)
        destination.write_text(_debug_svg(self, self._debug), encoding="utf-8")
        return destination


@dataclass(frozen=True, slots=True)
class ReachabilityResult:
    reachable: bool
    path: PathResult
    required_clearance: float
    available_clearance: float | None
    blocked_by: tuple[WorldObject, ...]
    reason: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    @property
    def value(self) -> bool:
        return self.reachable


@dataclass(frozen=True, slots=True)
class PassageResult:
    can_pass: bool
    required_width: float
    available_width: float
    required_height: float
    available_height: float
    reason: str
    objects: tuple[WorldObject, ...]
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    @property
    def value(self) -> bool:
        return self.can_pass


@dataclass(frozen=True, slots=True)
class ClearanceResult:
    reachable: bool
    minimum_clearance: float | None
    narrowest_point: Vector3 | None
    nearby_blocking_objects: tuple[WorldObject, ...]
    reason: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@dataclass(frozen=True, slots=True)
class AgentSpec:
    id: str
    name: str
    position: Vector3
    height: float
    radius: float
    step_height: float
    max_slope: float | None


@dataclass(frozen=True, slots=True)
class Agent:
    """A dimensioned entity that can query navigation in its owning world."""

    id: str
    name: str
    position: Vector3
    height: float
    radius: float
    step_height: float = 0.0
    max_slope: float | None = None
    _world: World = field(compare=False, repr=False, hash=False, default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.id or not self.name.strip():
            raise ValueError("agent id and name must not be empty")
        if self.height <= 0.0 or self.radius <= 0.0:
            raise ValueError("agent height and radius must be positive")
        if self.step_height < 0.0:
            raise ValueError("step_height must be non-negative")
        if self.max_slope is not None and self.max_slope < 0.0:
            raise ValueError("max_slope must be non-negative")
        if len(self.position) != 3 or not all(isfinite(value) for value in self.position):
            raise ValueError("position must contain three finite values")

    def path_to(self, target: ObjectReference) -> PathResult:
        return self._world._path_for_agent(self, target)

    def can_reach(self, target: ObjectReference) -> ReachabilityResult:
        return self._world.reachable(self, target)

    def can_pass(self, opening: ObjectReference) -> PassageResult:
        return self._world.can_pass(self, opening)

    def clearance_to(self, target: ObjectReference) -> ClearanceResult:
        path = self.path_to(target)
        return ClearanceResult(
            reachable=path.reachable,
            minimum_clearance=path.minimum_clearance,
            narrowest_point=path.narrowest_point,
            nearby_blocking_objects=path.blocked_by,
            reason=path.reason,
            evidence={"path": path},
        )

    def specification(self) -> AgentSpec:
        return AgentSpec(
            id=self.id,
            name=self.name,
            position=self.position,
            height=self.height,
            radius=self.radius,
            step_height=self.step_height,
            max_slope=self.max_slope,
        )


@dataclass(frozen=True, slots=True)
class NavigationGrid:
    """A query-local 2D grid of agent-centre positions."""

    minimum: Point2
    maximum: Point2
    resolution: float
    width: int
    height: int
    blocked: frozenset[GridCell]
    obstacles: tuple[NavigationObstacle, ...]
    start: GridCell
    target: GridCell
    ground_z: float

    @classmethod
    def build(
        cls,
        world: World,
        agent: Agent,
        target: WorldObject,
        *,
        resolution: float,
        margin: float,
    ) -> NavigationGrid:
        start_xy = agent.position[:2]
        target_xy = target.bounds.center[:2]
        minimum = (
            min(start_xy[0], target_xy[0]) - margin,
            min(start_xy[1], target_xy[1]) - margin,
        )
        maximum = (
            max(start_xy[0], target_xy[0]) + margin,
            max(start_xy[1], target_xy[1]) + margin,
        )
        width = int(ceil((maximum[0] - minimum[0]) / resolution)) + 1
        height = int(ceil((maximum[1] - minimum[1]) / resolution)) + 1
        obstacles: list[NavigationObstacle] = []
        blocked: set[GridCell] = set()
        for object_ in world.objects:
            if object_.id == target.id or not _blocks_agent(object_.bounds, agent):
                continue
            obstacle_minimum = (
                object_.bounds.minimum[0] - agent.radius,
                object_.bounds.minimum[1] - agent.radius,
            )
            obstacle_maximum = (
                object_.bounds.maximum[0] + agent.radius,
                object_.bounds.maximum[1] + agent.radius,
            )
            if not _rectangles_overlap(minimum, maximum, obstacle_minimum, obstacle_maximum):
                continue
            obstacle = NavigationObstacle(object_, obstacle_minimum, obstacle_maximum)
            obstacles.append(obstacle)
            x_start = max(0, int((obstacle_minimum[0] - minimum[0]) // resolution))
            x_end = min(width - 1, int(ceil((obstacle_maximum[0] - minimum[0]) / resolution)))
            y_start = max(0, int((obstacle_minimum[1] - minimum[1]) // resolution))
            y_end = min(height - 1, int(ceil((obstacle_maximum[1] - minimum[1]) / resolution)))
            for x_index in range(x_start, x_end + 1):
                x_value = minimum[0] + x_index * resolution
                if not obstacle_minimum[0] <= x_value <= obstacle_maximum[0]:
                    continue
                for y_index in range(y_start, y_end + 1):
                    y_value = minimum[1] + y_index * resolution
                    if obstacle_minimum[1] <= y_value <= obstacle_maximum[1]:
                        blocked.add((x_index, y_index))
        start = _point_to_cell(start_xy, minimum, resolution, width, height)
        target_cell = _point_to_cell(target_xy, minimum, resolution, width, height)
        blocked.discard(start)
        blocked.discard(target_cell)
        return cls(
            minimum=minimum,
            maximum=maximum,
            resolution=resolution,
            width=width,
            height=height,
            blocked=frozenset(blocked),
            obstacles=tuple(obstacles),
            start=start,
            target=target_cell,
            ground_z=agent.position[2],
        )

    def point(self, cell: GridCell) -> Vector3:
        return (
            self.minimum[0] + cell[0] * self.resolution,
            self.minimum[1] + cell[1] * self.resolution,
            self.ground_z,
        )


def find_path(grid: NavigationGrid, agent: Agent, target: WorldObject) -> PathResult:
    """Run deterministic A* and calculate body-to-obstacle clearance."""
    if grid.start == grid.target:
        point = agent.position
        minimum_clearance, narrowest, nearby = _path_clearance((point,), grid, agent)
        return PathResult(
            reachable=True,
            points=(point,),
            distance=0.0,
            minimum_clearance=minimum_clearance,
            narrowest_point=narrowest,
            blocked_by=nearby,
            reason="Target is already at the agent position.",
            evidence=_evidence(grid, agent, target, visited=1),
            _debug=_debug(grid, agent, target),
        )

    frontier: list[tuple[float, float, int, GridCell]] = []
    order = 0
    heapq.heappush(frontier, (_heuristic(grid.start, grid.target), 0.0, order, grid.start))
    came_from: dict[GridCell, GridCell] = {}
    cost: dict[GridCell, float] = {grid.start: 0.0}
    visited = 0
    found = False
    while frontier:
        _, current_cost, _, current = heapq.heappop(frontier)
        if current_cost > cost.get(current, inf):
            continue
        visited += 1
        if current == grid.target:
            found = True
            break
        for neighbor, movement_cost in _neighbors(current, grid):
            candidate_cost = current_cost + movement_cost * grid.resolution
            if candidate_cost >= cost.get(neighbor, inf):
                continue
            cost[neighbor] = candidate_cost
            came_from[neighbor] = current
            order += 1
            priority = candidate_cost + _heuristic(neighbor, grid.target) * grid.resolution
            heapq.heappush(frontier, (priority, candidate_cost, order, neighbor))

    if not found:
        blockers = _blocking_objects(agent.position, target.bounds.center, grid)
        return PathResult(
            reachable=False,
            points=(),
            distance=None,
            minimum_clearance=None,
            narrowest_point=None,
            blocked_by=blockers,
            reason=(
                f"No collision-free path; blocked by {', '.join(item.name for item in blockers)}."
                if blockers
                else "No collision-free path exists inside the navigation query bounds."
            ),
            evidence=_evidence(grid, agent, target, visited=visited),
            _debug=_debug(grid, agent, target),
        )

    cells = [grid.target]
    while cells[-1] != grid.start:
        cells.append(came_from[cells[-1]])
    cells.reverse()
    points = tuple(grid.point(cell) for cell in cells)
    distance = sum(
        hypot(second[0] - first[0], second[1] - first[1])
        for first, second in zip(points, points[1:], strict=False)
    )
    minimum_clearance, narrowest, nearby = _path_clearance(points, grid, agent)
    return PathResult(
        reachable=True,
        points=points,
        distance=distance,
        minimum_clearance=minimum_clearance,
        narrowest_point=narrowest,
        blocked_by=nearby,
        reason="A collision-free path was found using deterministic A*.",
        evidence=_evidence(grid, agent, target, visited=visited),
        _debug=_debug(grid, agent, target),
    )


def _neighbors(cell: GridCell, grid: NavigationGrid) -> tuple[tuple[GridCell, float], ...]:
    candidates: list[tuple[GridCell, float]] = []
    for x_offset, y_offset, cost in (
        (-1, 0, 1.0),
        (1, 0, 1.0),
        (0, -1, 1.0),
        (0, 1, 1.0),
        (-1, -1, 2**0.5),
        (-1, 1, 2**0.5),
        (1, -1, 2**0.5),
        (1, 1, 2**0.5),
    ):
        neighbor = (cell[0] + x_offset, cell[1] + y_offset)
        if not (0 <= neighbor[0] < grid.width and 0 <= neighbor[1] < grid.height):
            continue
        if neighbor in grid.blocked:
            continue
        if x_offset and y_offset:
            if (cell[0] + x_offset, cell[1]) in grid.blocked:
                continue
            if (cell[0], cell[1] + y_offset) in grid.blocked:
                continue
        candidates.append((neighbor, cost))
    return tuple(candidates)


def _path_clearance(
    points: tuple[Vector3, ...], grid: NavigationGrid, agent: Agent
) -> tuple[float | None, Vector3 | None, tuple[WorldObject, ...]]:
    best = inf
    narrowest: Vector3 | None = None
    nearest: tuple[WorldObject, ...] = ()
    for point in points:
        distances = [
            (_point_rectangle_distance(point[:2], obstacle.minimum, obstacle.maximum), obstacle)
            for obstacle in grid.obstacles
        ]
        if not distances:
            continue
        distance = min(item[0] for item in distances)
        body_clearance = max(0.0, distance)
        if body_clearance < best:
            best = body_clearance
            narrowest = point
            nearest = tuple(
                item[1].object
                for item in distances
                if item[0] <= distance + grid.resolution + 1e-12
            )
    return (None, None, ()) if best == inf else (best, narrowest, nearest)


def _blocking_objects(
    start: Vector3, target: Vector3, grid: NavigationGrid
) -> tuple[WorldObject, ...]:
    blockers = [
        obstacle.object
        for obstacle in grid.obstacles
        if _segment_intersects_rectangle(start[:2], target[:2], obstacle.minimum, obstacle.maximum)
    ]
    if blockers:
        return tuple(sorted(set(blockers), key=lambda object_: object_.id))
    midpoint = ((start[0] + target[0]) / 2, (start[1] + target[1]) / 2)
    nearest = sorted(
        grid.obstacles,
        key=lambda obstacle: _point_rectangle_distance(
            midpoint, obstacle.minimum, obstacle.maximum
        ),
    )
    return tuple(obstacle.object for obstacle in nearest[:3])


def _blocks_agent(bounds: Bounds, agent: Agent) -> bool:
    feet = agent.position[2]
    return (
        bounds.maximum[2] > feet + agent.step_height + 1e-9
        and bounds.minimum[2] < feet + agent.height - 1e-9
    )


def _point_to_cell(
    point: Point2,
    minimum: Point2,
    resolution: float,
    width: int,
    height: int,
) -> GridCell:
    return (
        min(width - 1, max(0, round((point[0] - minimum[0]) / resolution))),
        min(height - 1, max(0, round((point[1] - minimum[1]) / resolution))),
    )


def _heuristic(first: GridCell, second: GridCell) -> float:
    return hypot(second[0] - first[0], second[1] - first[1])


def _point_rectangle_distance(point: Point2, minimum: Point2, maximum: Point2) -> float:
    x_gap = max(0.0, minimum[0] - point[0], point[0] - maximum[0])
    y_gap = max(0.0, minimum[1] - point[1], point[1] - maximum[1])
    return hypot(x_gap, y_gap)


def _rectangles_overlap(
    first_minimum: Point2,
    first_maximum: Point2,
    second_minimum: Point2,
    second_maximum: Point2,
) -> bool:
    return not (
        first_maximum[0] < second_minimum[0]
        or second_maximum[0] < first_minimum[0]
        or first_maximum[1] < second_minimum[1]
        or second_maximum[1] < first_minimum[1]
    )


def _segment_intersects_rectangle(
    start: Point2, target: Point2, minimum: Point2, maximum: Point2
) -> bool:
    enter, exit_ = 0.0, 1.0
    for index in range(2):
        delta = target[index] - start[index]
        if abs(delta) <= 1e-12:
            if start[index] < minimum[index] or start[index] > maximum[index]:
                return False
            continue
        first = (minimum[index] - start[index]) / delta
        second = (maximum[index] - start[index]) / delta
        enter = max(enter, min(first, second))
        exit_ = min(exit_, max(first, second))
        if enter > exit_:
            return False
    return True


def _evidence(
    grid: NavigationGrid, agent: Agent, target: WorldObject, *, visited: int
) -> dict[str, object]:
    return {
        "algorithm": "A* (8-connected occupancy grid)",
        "coordinate_system": "XY ground plane, Z up",
        "resolution": grid.resolution,
        "grid_size": (grid.width, grid.height),
        "visited_cells": visited,
        "required_clearance": agent.radius * 2.0,
        "target_id": target.id,
        "max_slope": agent.max_slope,
    }


def _debug(grid: NavigationGrid, agent: Agent, target: WorldObject) -> NavigationDebug:
    return NavigationDebug(
        minimum=grid.minimum,
        maximum=grid.maximum,
        resolution=grid.resolution,
        obstacles=grid.obstacles,
        start=agent.position,
        target=target.bounds.center,
    )


def _serializable_evidence(evidence: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in evidence.items():
        if value is None or isinstance(value, str | int | float | bool):
            result[key] = value
        elif isinstance(value, tuple):
            result[key] = list(value)
        else:
            result[key] = repr(value)
    return result


def _debug_svg(result: PathResult, debug: NavigationDebug) -> str:
    width, height = 1000.0, 700.0
    x_span = max(1e-9, debug.maximum[0] - debug.minimum[0])
    y_span = max(1e-9, debug.maximum[1] - debug.minimum[1])

    def project(point: Point2) -> Point2:
        return (
            (point[0] - debug.minimum[0]) / x_span * width,
            height - (point[1] - debug.minimum[1]) / y_span * height,
        )

    rectangles = []
    for obstacle in debug.obstacles:
        left, bottom = project(obstacle.minimum)
        right, top = project(obstacle.maximum)
        rectangles.append(
            f'<rect x="{left:.2f}" y="{top:.2f}" width="{right - left:.2f}" '
            f'height="{bottom - top:.2f}" fill="#ef4444" fill-opacity="0.55">'
            f"<title>{obstacle.object.name}</title></rect>"
        )
    path_points = result.points or (debug.start, debug.target)
    polyline = " ".join(
        f"{x:.2f},{y:.2f}" for x, y in (project(point[:2]) for point in path_points)
    )
    dash = "" if result.reachable else ' stroke-dasharray="12 8"'
    start_x, start_y = project(debug.start[:2])
    target_x, target_y = project(debug.target[:2])
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="700" '
        'viewBox="0 0 1000 700">'
        '<rect width="1000" height="700" fill="#ecfdf5"/>'
        + "".join(rectangles)
        + f'<polyline points="{polyline}" fill="none" stroke="#2563eb" stroke-width="5"{dash}/>'
        + f'<circle cx="{start_x:.2f}" cy="{start_y:.2f}" r="9" fill="#16a34a"/>'
        + f'<circle cx="{target_x:.2f}" cy="{target_y:.2f}" r="9" fill="#7c3aed"/>'
        + f'<text x="16" y="28" font-family="sans-serif" font-size="18">{result.reason}</text>'
        + "</svg>"
    )
