"""Incrementally maintainable relationships between objects in a world."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias

from ._models import PredicateResult, WorldObject

if TYPE_CHECKING:
    from ._articulation import Articulation, MotionResult
    from ._navigation import Agent, PathResult
    from ._world import EntityReference, ObjectReference, World

RelationshipKey: TypeAlias = tuple[str, str, "RelationshipType"]
VisibilityKey: TypeAlias = tuple[str, str]
VisibilityRecord: TypeAlias = tuple[str, str, PredicateResult[bool]]


class RelationshipType(StrEnum):
    """Physical and spatial relationships represented by :class:`RealityGraph`."""

    NEAR = "near"
    ABOVE = "above"
    BELOW = "below"
    INSIDE = "inside"
    CONTAINS = "contains"
    INTERSECTS = "intersects"
    TOUCHING = "touching"
    VISIBLE_FROM = "visible_from"
    REACHABLE_BY = "reachable_by"
    UNREACHABLE_BY = "unreachable_by"
    BLOCKS_PATH_OF = "blocks_path_of"
    BLOCKS_MOTION_OF = "blocks_motion_of"
    ARTICULATED_WITH = "articulated_with"
    CONSTRAINED_BY = "constrained_by"


@dataclass(frozen=True, slots=True)
class Relationship:
    """A graph edge referencing existing source and target objects."""

    source: WorldObject | Agent
    target: WorldObject | Agent
    type: RelationshipType
    result: object

    @property
    def value(self) -> bool:
        """Whether the relationship currently holds."""
        return bool(getattr(self.result, "value", False))


@dataclass(frozen=True, slots=True)
class GraphUpdateStats:
    """Instrumentation for one dependency-aware graph update."""

    predicates_before: int
    invalidated: int
    recalculated: int
    reused: int

    def __add__(self, other: GraphUpdateStats) -> GraphUpdateStats:
        return GraphUpdateStats(
            predicates_before=self.predicates_before + other.predicates_before,
            invalidated=self.invalidated + other.invalidated,
            recalculated=self.recalculated + other.recalculated,
            reused=self.reused + other.reused,
        )


class RealityGraph:
    """A dependency-indexed graph with a persistent base and local overlay.

    A normal ``World`` stores edges locally. A branch points at immutable tuples
    captured by its base snapshot, then stores only recalculated edges in its
    local overlay. Invalidated base edges are hidden by object id or edge key.
    """

    PREDICATES_PER_PAIR = 14

    def __init__(
        self,
        world: World,
        *,
        base_relationships: tuple[Relationship, ...] = (),
        base_visibility: tuple[VisibilityRecord, ...] = (),
        persistent_base: bool = False,
    ) -> None:
        self._world = world
        self._base_relationships = base_relationships
        self._base_visibility = base_visibility
        self._persistent_base = persistent_base
        self._relationships: dict[RelationshipKey, Relationship] = {}
        self._by_object: dict[str, set[RelationshipKey]] = defaultdict(set)
        self._visibility: dict[VisibilityKey, PredicateResult[bool]] = {}
        self._invalidated: set[str] = set()
        self._suppressed_keys: set[RelationshipKey] = set()
        self._invalidated_visibility: set[VisibilityKey] = set()
        self._revision = 0

    @classmethod
    def fork(
        cls,
        world: World,
        relationships: tuple[Relationship, ...],
        visibility: tuple[VisibilityRecord, ...],
    ) -> RealityGraph:
        """Create an empty copy-on-write overlay over immutable snapshot data."""
        return cls(
            world,
            base_relationships=relationships,
            base_visibility=visibility,
            persistent_base=True,
        )

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def invalidated_object_ids(self) -> frozenset[str]:
        return frozenset(self._invalidated)

    @property
    def relationship_count(self) -> int:
        return len(self.all_relationships())

    @property
    def predicate_count(self) -> int:
        object_count = len(self._world.objects)
        pairs = object_count * (object_count - 1) // 2
        return pairs * self.PREDICATES_PER_PAIR + len(self.visibility_records())

    def all_relationships(self) -> tuple[Relationship, ...]:
        """Return active base edges followed by local overlay edges."""
        local_keys = set(self._relationships)
        base = (
            relationship
            for relationship in self._base_relationships
            if self._key(relationship) not in local_keys
            and self._key(relationship) not in self._suppressed_keys
            and relationship.source.id not in self._invalidated
            and relationship.target.id not in self._invalidated
        )
        return (*base, *self._relationships.values())

    def relationships(self, reference: EntityReference) -> tuple[Relationship, ...]:
        object_ = self._world.entity(reference)
        return tuple(
            relationship
            for relationship in self.all_relationships()
            if object_.id in {relationship.source.id, relationship.target.id}
        )

    def visibility_records(self) -> tuple[VisibilityRecord, ...]:
        """Return active visibility query results, including false results."""
        records: dict[VisibilityKey, PredicateResult[bool]] = {
            (target_id, viewer_id): result
            for target_id, viewer_id, result in self._base_visibility
            if (target_id, viewer_id) not in self._invalidated_visibility
        }
        records.update(self._visibility)
        return tuple((target, viewer, result) for (target, viewer), result in records.items())

    def visibility_query_keys(self) -> tuple[VisibilityKey, ...]:
        return tuple((target, viewer) for target, viewer, _ in self.visibility_records())

    def invalidate_object(self, reference: ObjectReference) -> int:
        """Hide/remove only edges dependent on an object and return their count."""
        object_ = self._world.object(reference)
        before = self.relationships(object_)
        for key in tuple(self._by_object.get(object_.id, ())):
            relationship = self._relationships.pop(key)
            self._by_object[relationship.source.id].discard(key)
            self._by_object[relationship.target.id].discard(key)
        self._invalidated.add(object_.id)
        self._revision += 1
        return len(before)

    def invalidate_visibility_queries(self) -> int:
        """Invalidate known visibility because any moved object can become an occluder."""
        records = self.visibility_records()
        for target_id, viewer_id, _ in records:
            key = (target_id, viewer_id)
            self._invalidated_visibility.add(key)
            self._visibility.pop(key, None)
            self._suppressed_keys.add((target_id, viewer_id, RelationshipType.VISIBLE_FROM))
        if records:
            self._revision += 1
        return len(records)

    def invalidate_navigation_relationships(self) -> int:
        """Invalidate lazy navigation edges because any obstacle may affect a path."""
        navigation_types = {
            RelationshipType.REACHABLE_BY,
            RelationshipType.UNREACHABLE_BY,
            RelationshipType.BLOCKS_PATH_OF,
        }
        active = tuple(
            relationship
            for relationship in self.all_relationships()
            if relationship.type in navigation_types
        )
        for relationship in active:
            key = self._key(relationship)
            self._suppressed_keys.add(key)
            self._remove_key(key)
        if active:
            self._revision += 1
        return len(active)

    def invalidate_motion_relationships(self) -> int:
        motion_types = {
            RelationshipType.BLOCKS_MOTION_OF,
            RelationshipType.CONSTRAINED_BY,
        }
        active = tuple(
            relationship
            for relationship in self.all_relationships()
            if relationship.type in motion_types
        )
        for relationship in active:
            key = self._key(relationship)
            self._suppressed_keys.add(key)
            self._remove_key(key)
        if active:
            self._revision += 1
        return len(active)

    def refresh_object(self, reference: ObjectReference) -> GraphUpdateStats:
        """Recalculate only one object's pair relationships."""
        return self.refresh_objects((reference,))

    def refresh_objects(self, references: tuple[ObjectReference, ...]) -> GraphUpdateStats:
        """Refresh the dependency frontier for several changed objects once.

        Simulation commonly changes many dynamic objects during one fixed-step run.
        Repeating a single-object refresh would evaluate changed/changed pairs twice
        and invalidate lazy query state many times.  This method preserves the
        existing incremental semantics while evaluating each affected pair once.
        """
        changed = tuple(dict.fromkeys(self._world.object(reference).id for reference in references))
        if not changed:
            return GraphUpdateStats(self.predicate_count, 0, 0, self.predicate_count)
        predicates_before = self.predicate_count
        visibility_count = len(self.visibility_records())
        for object_id in changed:
            self.invalidate_object(object_id)
        self.invalidate_visibility_queries()
        navigation_invalidated = self.invalidate_navigation_relationships()
        motion_invalidated = self.invalidate_motion_relationships()
        changed_ids = set(changed)
        pair_ids: set[tuple[str, str]] = set()
        for object_id in changed:
            for other in self._world.objects:
                if other.id == object_id:
                    continue
                first_id, second_id = sorted((object_id, other.id))
                pair_ids.add((first_id, second_id))
        for first_id, second_id in sorted(pair_ids):
            self._create_pair_relationships(
                self._world.object(first_id), self._world.object(second_id)
            )
        if not self._persistent_base:
            self._invalidated.difference_update(changed_ids)
        recalculated = len(pair_ids) * self.PREDICATES_PER_PAIR
        invalidated = recalculated + visibility_count + navigation_invalidated + motion_invalidated
        return GraphUpdateStats(
            predicates_before=predicates_before,
            invalidated=invalidated,
            recalculated=recalculated,
            reused=max(0, predicates_before - invalidated),
        )

    def refresh_all(self) -> GraphUpdateStats:
        predicates_before = self.predicate_count
        self._relationships.clear()
        self._by_object.clear()
        self._invalidated.clear()
        objects = self._world.objects
        pair_count = 0
        for index, first in enumerate(objects):
            for second in objects[index + 1 :]:
                self._create_pair_relationships(first, second)
                pair_count += 1
        self._revision += 1
        return GraphUpdateStats(
            predicates_before=predicates_before,
            invalidated=predicates_before,
            recalculated=pair_count * self.PREDICATES_PER_PAIR,
            reused=0,
        )

    def record_visibility(
        self,
        target: WorldObject,
        viewer: WorldObject,
        result: PredicateResult[bool],
    ) -> None:
        key = (target.id, viewer.id)
        relationship_key = (target.id, viewer.id, RelationshipType.VISIBLE_FROM)
        self._visibility[key] = result
        self._invalidated_visibility.discard(key)
        self._suppressed_keys.add(relationship_key)
        self._remove_key(relationship_key)
        if result.value:
            self._add(Relationship(target, viewer, RelationshipType.VISIBLE_FROM, result))
        self._revision += 1

    def record_navigation(self, agent: Agent, target: WorldObject, result: PathResult) -> None:
        """Cache lazy reachability and blocker relationships in the graph overlay."""
        navigation_types = {
            RelationshipType.REACHABLE_BY,
            RelationshipType.UNREACHABLE_BY,
            RelationshipType.BLOCKS_PATH_OF,
        }
        for relationship in self.all_relationships():
            if relationship.type in navigation_types and agent.id in {
                relationship.source.id,
                relationship.target.id,
            }:
                key = self._key(relationship)
                self._suppressed_keys.add(key)
                self._remove_key(key)
        relationship_type = (
            RelationshipType.REACHABLE_BY if result.reachable else RelationshipType.UNREACHABLE_BY
        )
        self._add(Relationship(target, agent, relationship_type, result))
        for blocker in result.blocked_by:
            self._add(Relationship(blocker, agent, RelationshipType.BLOCKS_PATH_OF, result))
        self._revision += 1

    def record_articulation(self, object_: WorldObject, articulation: Articulation) -> None:
        self._add(Relationship(object_, object_, RelationshipType.ARTICULATED_WITH, articulation))
        self._revision += 1

    def record_motion(self, object_: WorldObject, result: MotionResult) -> None:
        self.invalidate_motion_relationships()
        if result.collides_with:
            for blocker in result.collides_with:
                self._add(Relationship(blocker, object_, RelationshipType.BLOCKS_MOTION_OF, result))
                self._add(Relationship(object_, blocker, RelationshipType.CONSTRAINED_BY, result))
        self._revision += 1

    def _create_pair_relationships(self, first: WorldObject, second: WorldObject) -> None:
        tests = (
            (first, second, RelationshipType.NEAR, self._world.near(first, second)),
            (second, first, RelationshipType.NEAR, self._world.near(second, first)),
            (first, second, RelationshipType.INTERSECTS, self._world.intersects(first, second)),
            (second, first, RelationshipType.INTERSECTS, self._world.intersects(second, first)),
            (first, second, RelationshipType.TOUCHING, self._world.touching(first, second)),
            (second, first, RelationshipType.TOUCHING, self._world.touching(second, first)),
            (first, second, RelationshipType.ABOVE, self._world.above(first, second)),
            (second, first, RelationshipType.BELOW, self._world.below(second, first)),
            (first, second, RelationshipType.BELOW, self._world.below(first, second)),
            (second, first, RelationshipType.ABOVE, self._world.above(second, first)),
            (first, second, RelationshipType.INSIDE, self._world.inside(first, second)),
            (second, first, RelationshipType.CONTAINS, self._world.contains(second, first)),
            (second, first, RelationshipType.INSIDE, self._world.inside(second, first)),
            (first, second, RelationshipType.CONTAINS, self._world.contains(first, second)),
        )
        for source, target, relationship_type, result in tests:
            if result.value:
                self._add(Relationship(source, target, relationship_type, result))

    def _add(self, relationship: Relationship) -> None:
        key = self._key(relationship)
        self._relationships[key] = relationship
        self._by_object[relationship.source.id].add(key)
        self._by_object[relationship.target.id].add(key)

    def _remove_key(self, key: RelationshipKey) -> None:
        relationship = self._relationships.pop(key, None)
        if relationship is not None:
            self._by_object[relationship.source.id].discard(key)
            self._by_object[relationship.target.id].discard(key)

    @staticmethod
    def _key(relationship: Relationship) -> RelationshipKey:
        return (relationship.source.id, relationship.target.id, relationship.type)
