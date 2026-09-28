"""Copy-on-write world branches and generic consequence comparison."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from math import isclose
from typing import Literal, TypeAlias

from ._articulation import MotionRecord
from ._graph import GraphUpdateStats, RealityGraph, VisibilityRecord
from ._models import Transform, WorldObject
from ._navigation import Agent, NavigationRecord
from ._physics import SimulationResult
from ._state import (
    Change,
    ChangeSet,
    Consequence,
    ConsequenceSet,
    MoveObject,
    RotateObject,
    ScaleObject,
    WorldSnapshot,
    snapshot_indexes,
)
from ._world import AmbiguousObjectError, ObjectNotFoundError, ObjectReference, World

ChangeType: TypeAlias = type[MoveObject] | type[RotateObject] | type[ScaleObject]


class WorldBranch(World):
    """An alternate world state backed by an immutable snapshot and object deltas."""

    def __init__(self, snapshot: WorldSnapshot) -> None:
        self.units = snapshot.units
        self.navigation_resolution = snapshot.navigation_resolution
        self.navigation_margin = snapshot.navigation_margin
        self.compute_backend = snapshot.compute_backend
        self._build_graph = snapshot.build_graph
        self._base_snapshot = snapshot
        self._lineage_id = snapshot.lineage_id
        self._base_by_id = snapshot.objects_by_id
        self._base_names = snapshot.object_ids_by_name
        self._overrides: dict[str, WorldObject] = {}
        self._agents_by_id: dict[str, Agent] = {}
        self._agent_names: dict[str, list[Agent]] = {}
        for specification in snapshot.agents:
            agent = Agent(
                id=specification.id,
                name=specification.name,
                position=specification.position,
                height=specification.height,
                radius=specification.radius,
                step_height=specification.step_height,
                max_slope=specification.max_slope,
                _world=self,
            )
            self._agents_by_id[agent.id] = agent
            self._agent_names.setdefault(agent.name, []).append(agent)
        self._navigation_cache = {
            (agent_id, target_id): result for agent_id, target_id, result in snapshot.navigation
        }
        self._articulations = {
            articulation.object_id: articulation for articulation in snapshot.articulations
        }
        self._motion_cache = {
            (object_id, kind, requested): result
            for object_id, kind, requested, result in snapshot.motion
        }
        self._simulation_results: list[SimulationResult] = []
        self._physics_backends = {}
        self._changes: list[Change] = []
        self._updates: list[GraphUpdateStats] = []
        self._version = snapshot.version
        self._snapshot_cache: WorldSnapshot | None = None
        self.graph = RealityGraph.fork(self, snapshot.relationships, snapshot.visibility)

    @property
    def objects(self) -> tuple[WorldObject, ...]:
        return tuple(
            self._overrides.get(object_.id, object_) for object_ in self._base_snapshot.objects
        )

    @property
    def changes(self) -> ChangeSet:
        return ChangeSet(tuple(self._changes))

    @property
    def instrumentation(self) -> GraphUpdateStats:
        total = GraphUpdateStats(0, 0, 0, 0)
        for update in self._updates:
            total += update
        return total

    def object(self, reference: ObjectReference) -> WorldObject:
        if isinstance(reference, WorldObject):
            object_id = reference.id
            if object_id in self._base_by_id:
                return self._overrides.get(object_id, self._base_by_id[object_id])
            raise ObjectNotFoundError(f"object is not registered: {reference.name!r}")
        if reference in self._base_by_id:
            return self._overrides.get(reference, self._base_by_id[reference])
        matches: tuple[str, ...] = self._base_names.get(reference, ())
        if not matches:
            raise ObjectNotFoundError(f"no object named or identified {reference!r}")
        if len(matches) > 1:
            raise AmbiguousObjectError(
                f"name {reference!r} identifies {len(matches)} objects; use an id"
            )
        object_id = matches[0]
        return self._overrides.get(object_id, self._base_by_id[object_id])

    def add(self, object_: WorldObject) -> WorldObject:
        raise NotImplementedError("adding objects to a branch is not part of this milestone")

    def update_transform(self, reference: ObjectReference, transform: Transform) -> WorldObject:
        current = self.object(reference)
        changes: list[tuple[ChangeType, Mapping[str, float]]] = []
        if transform.position != current.position:
            changes.append(
                (
                    MoveObject,
                    {
                        "x": transform.position[0] - current.position[0],
                        "y": transform.position[1] - current.position[1],
                        "z": transform.position[2] - current.position[2],
                    },
                )
            )
        if transform.rotation != current.rotation:
            changes.append(
                (
                    RotateObject,
                    {
                        "x": transform.rotation[0] - current.rotation[0],
                        "y": transform.rotation[1] - current.rotation[1],
                        "z": transform.rotation[2] - current.rotation[2],
                    },
                )
            )
        if transform.scale != current.scale:
            changes.append(
                (
                    ScaleObject,
                    {
                        "x": transform.scale[0] / current.scale[0],
                        "y": transform.scale[1] / current.scale[1],
                        "z": transform.scale[2] / current.scale[2],
                    },
                )
            )
        return self._commit_transform(current, transform, changes)

    def move(
        self,
        reference: ObjectReference,
        *,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
    ) -> WorldObject:
        current = self.object(reference)
        transform = Transform(
            position=(current.position[0] + x, current.position[1] + y, current.position[2] + z),
            rotation=current.rotation,
            scale=current.scale,
        )
        return self._commit_transform(current, transform, [(MoveObject, {"x": x, "y": y, "z": z})])

    def rotate(
        self,
        reference: ObjectReference,
        *,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
    ) -> WorldObject:
        current = self.object(reference)
        transform = Transform(
            position=current.position,
            rotation=(current.rotation[0] + x, current.rotation[1] + y, current.rotation[2] + z),
            scale=current.scale,
        )
        return self._commit_transform(
            current, transform, [(RotateObject, {"x": x, "y": y, "z": z})]
        )

    def scale(
        self,
        reference: ObjectReference,
        *,
        x: float = 1.0,
        y: float = 1.0,
        z: float = 1.0,
    ) -> WorldObject:
        current = self.object(reference)
        transform = Transform(
            position=current.position,
            rotation=current.rotation,
            scale=(current.scale[0] * x, current.scale[1] * y, current.scale[2] * z),
        )
        return self._commit_transform(current, transform, [(ScaleObject, {"x": x, "y": y, "z": z})])

    def snapshot(self) -> WorldSnapshot:
        if self._snapshot_cache is None:
            objects = self.objects
            objects_by_id, object_ids_by_name = snapshot_indexes(objects)
            self._snapshot_cache = WorldSnapshot(
                lineage_id=self._lineage_id,
                version=self._version,
                units=self.units,
                objects=objects,
                objects_by_id=objects_by_id,
                object_ids_by_name=object_ids_by_name,
                agents=tuple(agent.specification() for agent in self._agents_by_id.values()),
                navigation=tuple(
                    (agent_id, target_id, result)
                    for (agent_id, target_id), result in self._navigation_cache.items()
                ),
                navigation_resolution=self.navigation_resolution,
                navigation_margin=self.navigation_margin,
                compute_backend=self.compute_backend,
                build_graph=self._build_graph,
                articulations=tuple(self._articulations.values()),
                motion=self._motion_records(),
                relationships=self.graph.all_relationships(),
                visibility=self.graph.visibility_records(),
                created_at=datetime.now(UTC),
            )
        return self._snapshot_cache

    def consequences(self) -> ConsequenceSet:
        changed_ids = {change.object_id for change in self._changes}
        compared = compare_states(
            self._base_snapshot.objects,
            self.objects,
            changed_ids,
            self._base_snapshot.visibility,
            self.graph.visibility_records(),
            self._base_snapshot.navigation,
            self._navigation_records(),
            self._base_snapshot.motion,
            self._motion_records(),
            changes=self.changes,
            instrumentation=self.instrumentation,
        )
        simulated = list(compared.consequences)
        for result in self._simulation_results:
            for body in result.bodies:
                if body.motion <= 1e-9:
                    continue
                simulated.append(
                    Consequence(
                        what_changed="fell" if body.fell else "simulation_motion",
                        previous_value=body.initial_transform,
                        new_value=body.final_transform,
                        magnitude=body.motion,
                        objects=(self.object(body.object_id),),
                        classification="simulation_observed",
                        reason=(
                            f"Observed during {result.backend} fixed-step simulation; "
                            "no unobserved causal chain is inferred."
                        ),
                        evidence={
                            "backend": result.backend,
                            "seconds": result.seconds,
                            "steps": result.steps,
                            "contact_count": body.contact_count,
                        },
                    )
                )
        return ConsequenceSet(tuple(simulated), compared.changes, compared.instrumentation)

    def _replace_object(self, current: WorldObject, updated: WorldObject) -> WorldObject:
        self._overrides[updated.id] = updated
        self._version += 1
        self._snapshot_cache = None
        return updated

    def _apply_simulation_transform(self, object_id: str, transform: Transform) -> None:
        self._apply_simulation_transforms({object_id: transform})

    def _apply_simulation_transforms(self, transforms: dict[str, Transform]) -> None:
        """Apply a solver result without recording synthetic user transform changes."""
        updated: list[WorldObject] = []
        for object_id, transform in transforms.items():
            current = self.object(object_id)
            if transform == current.transform:
                continue
            replacement = replace(current, transform=transform)
            self._overrides[object_id] = replacement
            updated.append(replacement)
        if not updated:
            return
        if self._build_graph:
            visibility_queries = self.graph.visibility_query_keys()
            navigation_queries = tuple(self._navigation_cache)
            motion_queries = tuple(self._motion_cache)
            stats = self.graph.refresh_objects(tuple(updated))
            self._restore_articulation_relationships(updated)
            for target_id, viewer_id in visibility_queries:
                self.visible(target_id, from_=viewer_id)
            self._recalculate_navigation(navigation_queries)
            self._recalculate_motion(motion_queries)
            if visibility_queries:
                stats = replace(stats, recalculated=stats.recalculated + len(visibility_queries))
            if navigation_queries:
                stats = replace(
                    stats,
                    invalidated=stats.invalidated + len(navigation_queries),
                    recalculated=stats.recalculated + len(navigation_queries),
                )
            if motion_queries:
                stats = replace(
                    stats,
                    invalidated=stats.invalidated + len(motion_queries),
                    recalculated=stats.recalculated + len(motion_queries),
                )
            self._updates.append(stats)
        self._version += 1
        self._snapshot_cache = None

    def _commit_transform(
        self,
        current: WorldObject,
        transform: Transform,
        changes: list[tuple[ChangeType, Mapping[str, float]]],
    ) -> WorldObject:
        if transform == current.transform:
            return current
        visibility_queries = self.graph.visibility_query_keys()
        navigation_queries = tuple(self._navigation_cache)
        motion_queries = tuple(self._motion_cache)
        updated = replace(current, transform=transform)
        self._overrides[updated.id] = updated
        stats = self.graph.refresh_object(updated)
        self._restore_articulation_relationships((updated,))
        for target_id, viewer_id in visibility_queries:
            self.visible(target_id, from_=viewer_id)
        self._recalculate_navigation(navigation_queries)
        self._recalculate_motion(motion_queries)
        if visibility_queries:
            stats = replace(stats, recalculated=stats.recalculated + len(visibility_queries))
        if navigation_queries:
            stats = replace(
                stats,
                invalidated=stats.invalidated + len(navigation_queries),
                recalculated=stats.recalculated + len(navigation_queries),
            )
        if motion_queries:
            stats = replace(
                stats,
                invalidated=stats.invalidated + len(motion_queries),
                recalculated=stats.recalculated + len(motion_queries),
            )
        self._updates.append(stats)
        for change_type, parameters in changes:
            self._changes.append(
                change_type(
                    object_id=updated.id,
                    object_name=updated.name,
                    old_state=current.transform,
                    new_state=transform,
                    parameters=parameters,
                    order=len(self._changes) + 1,
                    timestamp=datetime.now(UTC),
                )
            )
        self._version += 1
        self._snapshot_cache = None
        return updated

    def _navigation_records(self) -> tuple[NavigationRecord, ...]:
        return tuple(
            (agent_id, target_id, result)
            for (agent_id, target_id), result in self._navigation_cache.items()
        )

    def _motion_records(self) -> tuple[MotionRecord, ...]:
        return tuple(
            (object_id, kind, requested, result)
            for (object_id, kind, requested), result in self._motion_cache.items()
        )


@dataclass(frozen=True, slots=True)
class _Outcome:
    value: object
    measurement: float | None = None


def compare_states(
    before_objects: tuple[WorldObject, ...],
    after_objects: tuple[WorldObject, ...],
    changed_ids: set[str],
    before_visibility: tuple[VisibilityRecord, ...],
    after_visibility: tuple[VisibilityRecord, ...],
    before_navigation: tuple[NavigationRecord, ...] = (),
    after_navigation: tuple[NavigationRecord, ...] = (),
    before_motion: tuple[MotionRecord, ...] = (),
    after_motion: tuple[MotionRecord, ...] = (),
    *,
    changes: ChangeSet | None = None,
    instrumentation: GraphUpdateStats | None = None,
) -> ConsequenceSet:
    """Compare only pairs in the changed-object dependency frontier."""
    changes = changes or ChangeSet()
    instrumentation = instrumentation or GraphUpdateStats(0, 0, 0, 0)
    before = {object_.id: object_ for object_ in before_objects}
    after = {object_.id: object_ for object_ in after_objects}
    consequences: list[Consequence] = []
    unordered_pairs: set[tuple[str, str]] = set()
    for changed_id in changed_ids:
        for other_id in before.keys() & after.keys():
            if other_id != changed_id:
                pair = (changed_id, other_id) if changed_id < other_id else (other_id, changed_id)
                unordered_pairs.add(pair)

    for first_id, second_id in sorted(unordered_pairs):
        for predicate in ("distance", "near", "intersects", "touching"):
            _append_difference(
                consequences,
                predicate,
                _evaluate(predicate, before[first_id], before[second_id]),
                _evaluate(predicate, after[first_id], after[second_id]),
                (after[first_id], after[second_id]),
                "direct",
            )
        for source_id, target_id in ((first_id, second_id), (second_id, first_id)):
            for predicate in ("above", "below", "inside", "contains"):
                _append_difference(
                    consequences,
                    predicate,
                    _evaluate(predicate, before[source_id], before[target_id]),
                    _evaluate(predicate, after[source_id], after[target_id]),
                    (after[source_id], after[target_id]),
                    "direct",
                )

    before_vis = {(target, viewer): result for target, viewer, result in before_visibility}
    after_vis = {(target, viewer): result for target, viewer, result in after_visibility}
    for key in sorted(before_vis.keys() & after_vis.keys()):
        previous, new = before_vis[key], after_vis[key]
        target_id, viewer_id = key
        classification: Literal["direct", "downstream"] = (
            "direct" if changed_ids & {target_id, viewer_id} else "downstream"
        )
        previous_fraction = previous.visibility_fraction
        new_fraction = new.visibility_fraction
        if previous.value != new.value:
            consequences.append(
                Consequence(
                    what_changed="visible_from",
                    previous_value=previous.value,
                    new_value=new.value,
                    magnitude=_difference(previous_fraction, new_fraction),
                    objects=(after[target_id], after[viewer_id]),
                    classification=classification,
                    reason="Deterministic visibility changed after branch mutations.",
                    evidence={"previous": previous, "new": new},
                )
            )
        elif _different(previous_fraction, new_fraction):
            consequences.append(
                Consequence(
                    what_changed="visibility_fraction",
                    previous_value=previous_fraction,
                    new_value=new_fraction,
                    magnitude=_difference(previous_fraction, new_fraction),
                    objects=(after[target_id], after[viewer_id]),
                    classification=classification,
                    reason="The fraction of unobstructed target samples changed.",
                    evidence={"previous": previous, "new": new},
                )
            )
    _append_navigation_consequences(
        consequences,
        before_navigation,
        after_navigation,
        before,
        after,
        changed_ids,
    )
    _append_motion_consequences(
        consequences,
        before_motion,
        after_motion,
        after,
        changed_ids,
    )
    return ConsequenceSet(tuple(consequences), changes, instrumentation)


def _append_navigation_consequences(
    consequences: list[Consequence],
    before_records: tuple[NavigationRecord, ...],
    after_records: tuple[NavigationRecord, ...],
    before_objects: dict[str, WorldObject],
    after_objects: dict[str, WorldObject],
    changed_ids: set[str],
) -> None:
    before = {(agent_id, target_id): result for agent_id, target_id, result in before_records}
    after = {(agent_id, target_id): result for agent_id, target_id, result in after_records}
    for agent_id, target_id in sorted(before.keys() & after.keys()):
        previous = before[(agent_id, target_id)]
        new = after[(agent_id, target_id)]
        target = after_objects[target_id]
        involved = [target]
        blockers = new.blocked_by or previous.blocked_by
        involved.extend(
            after_objects[blocker.id]
            for blocker in blockers
            if blocker.id in after_objects and blocker.id != target.id
        )
        classification: Literal["direct", "downstream"] = (
            "direct" if target_id in changed_ids else "downstream"
        )
        if previous.reachable != new.reachable:
            consequences.append(
                Consequence(
                    what_changed="reachable_by",
                    previous_value=previous.reachable,
                    new_value=new.reachable,
                    magnitude=None,
                    objects=tuple(involved),
                    classification=classification,
                    reason=(
                        f"Navigation for {agent_id} changed after obstacle updates: {new.reason}"
                    ),
                    evidence={"previous": previous, "new": new, "agent_id": agent_id},
                )
            )
        elif _different(previous.minimum_clearance, new.minimum_clearance):
            consequences.append(
                Consequence(
                    what_changed="navigation_clearance",
                    previous_value=previous.minimum_clearance,
                    new_value=new.minimum_clearance,
                    magnitude=_difference(previous.minimum_clearance, new.minimum_clearance),
                    objects=tuple(involved),
                    classification=classification,
                    reason="Minimum body clearance along the cached route changed.",
                    evidence={"previous": previous, "new": new, "agent_id": agent_id},
                )
            )


def _append_motion_consequences(
    consequences: list[Consequence],
    before_records: tuple[MotionRecord, ...],
    after_records: tuple[MotionRecord, ...],
    after_objects: dict[str, WorldObject],
    changed_ids: set[str],
) -> None:
    before = {
        (object_id, kind, requested): result
        for object_id, kind, requested, result in before_records
    }
    after = {
        (object_id, kind, requested): result for object_id, kind, requested, result in after_records
    }
    for key in sorted(before.keys() & after.keys()):
        previous, new = before[key], after[key]
        object_id, kind, _ = key
        if previous.possible == new.possible and not _different(
            previous.maximum_collision_free, new.maximum_collision_free
        ):
            continue
        blockers = new.collides_with or previous.collides_with
        involved = [after_objects[object_id]]
        involved.extend(
            after_objects[blocker.id]
            for blocker in blockers
            if blocker.id in after_objects and blocker.id != object_id
        )
        classification: Literal["direct", "downstream"] = (
            "direct" if object_id in changed_ids else "downstream"
        )
        consequences.append(
            Consequence(
                what_changed=f"{kind}_motion",
                previous_value=previous.maximum_collision_free,
                new_value=new.maximum_collision_free,
                magnitude=_difference(previous.maximum_collision_free, new.maximum_collision_free),
                objects=tuple(involved),
                classification=classification,
                reason=f"Available articulated motion changed: {new.reason}",
                evidence={"previous": previous, "new": new},
            )
        )


def _evaluate(predicate: str, first: WorldObject, second: WorldObject) -> _Outcome:
    distance = first.bounds.distance_to(second.bounds)
    if predicate == "distance":
        return _Outcome(distance, distance)
    if predicate == "near":
        return _Outcome(distance <= 1.0, distance)
    if predicate == "intersects":
        return _Outcome(first.bounds.intersects(second.bounds))
    if predicate == "touching":
        return _Outcome(first.bounds.touching(second.bounds))
    if predicate == "above":
        clearance = first.bounds.minimum[2] - second.bounds.maximum[2]
        return _Outcome(clearance >= 0.0, clearance)
    if predicate == "below":
        clearance = second.bounds.minimum[2] - first.bounds.maximum[2]
        return _Outcome(clearance >= 0.0, clearance)
    if predicate == "inside":
        return _Outcome(second.bounds.contains(first.bounds))
    if predicate == "contains":
        return _Outcome(first.bounds.contains(second.bounds))
    raise ValueError(f"unknown predicate: {predicate}")


def _append_difference(
    consequences: list[Consequence],
    predicate: str,
    previous: _Outcome,
    new: _Outcome,
    objects: tuple[WorldObject, WorldObject],
    classification: Literal["direct", "downstream"],
) -> None:
    value_changed = previous.value != new.value
    measurement_changed = _different(previous.measurement, new.measurement)
    if not value_changed and not measurement_changed:
        return
    if value_changed:
        previous_value, new_value = previous.value, new.value
        what_changed = predicate
    else:
        previous_value, new_value = previous.measurement, new.measurement
        what_changed = f"{predicate}.measurement"
    consequences.append(
        Consequence(
            what_changed=what_changed,
            previous_value=previous_value,
            new_value=new_value,
            magnitude=_difference(previous.measurement, new.measurement),
            objects=objects,
            classification=classification,
            reason=f"{predicate} changed within the branch dependency frontier.",
            evidence={
                "previous_measurement": previous.measurement,
                "new_measurement": new.measurement,
            },
        )
    )


def _different(previous: float | None, new: float | None) -> bool:
    if previous is None or new is None:
        return previous != new
    return not isclose(previous, new, rel_tol=1e-12, abs_tol=1e-12)


def _difference(previous: float | None, new: float | None) -> float | None:
    if previous is None or new is None:
        return None
    return abs(new - previous)
