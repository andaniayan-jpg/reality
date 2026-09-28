"""Immutable snapshots, structured changes, and consequence reports."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Literal

from ._articulation import Articulation, MotionRecord
from ._graph import GraphUpdateStats, Relationship, VisibilityRecord
from ._models import Bounds, PredicateResult, Transform, WorldObject
from ._navigation import AgentSpec, NavigationRecord


@dataclass(frozen=True, slots=True)
class WorldSnapshot:
    """An immutable world-state view that shares frozen object and mesh references."""

    lineage_id: str
    version: int
    units: str
    objects: tuple[WorldObject, ...]
    objects_by_id: Mapping[str, WorldObject]
    object_ids_by_name: Mapping[str, tuple[str, ...]]
    agents: tuple[AgentSpec, ...]
    navigation: tuple[NavigationRecord, ...]
    navigation_resolution: float
    navigation_margin: float
    compute_backend: Literal["cpu", "cuda"]
    build_graph: bool
    articulations: tuple[Articulation, ...]
    motion: tuple[MotionRecord, ...]
    relationships: tuple[Relationship, ...]
    visibility: tuple[VisibilityRecord, ...]
    created_at: datetime

    def object(self, object_id: str) -> WorldObject:
        return self.objects_by_id[object_id]


def snapshot_indexes(
    objects: tuple[WorldObject, ...],
) -> tuple[Mapping[str, WorldObject], Mapping[str, tuple[str, ...]]]:
    """Build immutable lookup indexes once for all branches of a snapshot."""
    by_id = {object_.id: object_ for object_ in objects}
    names: dict[str, list[str]] = {}
    for object_ in objects:
        names.setdefault(object_.name, []).append(object_.id)
    by_name = {name: tuple(object_ids) for name, object_ids in names.items()}
    return MappingProxyType(by_id), MappingProxyType(by_name)


@dataclass(frozen=True, slots=True)
class Change:
    """One ordered transform mutation inside a branch."""

    object_id: str
    object_name: str
    old_state: Transform
    new_state: Transform
    parameters: Mapping[str, float]
    order: int
    timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))

    @property
    def kind(self) -> str:
        return type(self).__name__

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.kind,
            "object_id": self.object_id,
            "object_name": self.object_name,
            "old_state": _json_value(self.old_state),
            "new_state": _json_value(self.new_state),
            "parameters": dict(self.parameters),
            "order": self.order,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class MoveObject(Change):
    """An additive translation change."""


@dataclass(frozen=True, slots=True)
class RotateObject(Change):
    """An additive XYZ Euler-angle change in radians."""


@dataclass(frozen=True, slots=True)
class ScaleObject(Change):
    """A multiplicative XYZ scale change."""


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """An immutable ordered sequence of branch changes."""

    changes: tuple[Change, ...] = ()

    def __iter__(self) -> Iterator[Change]:
        return iter(self.changes)

    def __len__(self) -> int:
        return len(self.changes)

    def to_dict(self) -> list[dict[str, object]]:
        return [change.to_dict() for change in self.changes]


@dataclass(frozen=True, slots=True)
class Consequence:
    """A material predicate or relationship difference between two world states."""

    what_changed: str
    previous_value: object
    new_value: object
    magnitude: float | None
    objects: tuple[WorldObject, ...]
    classification: Literal["direct", "downstream", "simulation_observed"]
    reason: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    def __str__(self) -> str:
        names = "/".join(object_.name for object_ in self.objects)
        return f"{names} {self.what_changed}: {self.previous_value!r} -> {self.new_value!r}"

    def to_dict(self) -> dict[str, object]:
        return {
            "what_changed": self.what_changed,
            "previous_value": _json_value(self.previous_value),
            "new_value": _json_value(self.new_value),
            "magnitude": self.magnitude,
            "objects": [{"id": object_.id, "name": object_.name} for object_ in self.objects],
            "classification": self.classification,
            "reason": self.reason,
            "evidence": _json_value(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class ConsequenceSet:
    """Iterable, serializable output of a branch or branch comparison."""

    consequences: tuple[Consequence, ...]
    changes: ChangeSet = field(default_factory=ChangeSet)
    instrumentation: GraphUpdateStats = field(default_factory=lambda: GraphUpdateStats(0, 0, 0, 0))

    def __iter__(self) -> Iterator[Consequence]:
        return iter(self.consequences)

    def __len__(self) -> int:
        return len(self.consequences)

    def to_dict(self) -> dict[str, object]:
        return {
            "changes": self.changes.to_dict(),
            "consequences": [consequence.to_dict() for consequence in self.consequences],
            "instrumentation": {
                "predicates_before": self.instrumentation.predicates_before,
                "invalidated": self.instrumentation.invalidated,
                "recalculated": self.instrumentation.recalculated,
                "reused": self.instrumentation.reused,
            },
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def _json_value(value: Any) -> Any:
    if isinstance(value, Transform):
        return {
            "position": list(value.position),
            "rotation": list(value.rotation),
            "scale": list(value.scale),
        }
    if isinstance(value, Bounds):
        return {"minimum": list(value.minimum), "maximum": list(value.maximum)}
    if isinstance(value, WorldObject):
        return {"id": value.id, "name": value.name}
    if isinstance(value, PredicateResult):
        return {
            "value": _json_value(value.value),
            "measurement": value.measurement,
            "units": value.units,
            "reason": value.reason,
            "objects": [_json_value(object_) for object_ in value.objects],
            "evidence": _json_value(value.evidence),
        }
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return repr(value)
