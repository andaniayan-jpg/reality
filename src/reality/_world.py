"""The backend-neutral World query API."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime
from math import sqrt
from typing import TYPE_CHECKING, Literal, TypeAlias
from uuid import uuid4

from ._articulation import (
    ArticulatedObject,
    Articulation,
    MotionKey,
    MotionResult,
    PrismaticJoint,
    RevoluteJoint,
    analyze_motion,
)
from ._graph import RealityGraph, Relationship
from ._models import (
    Bounds,
    PhysicalProperties,
    PredicateResult,
    Transform,
    Vector3,
    WorldObject,
)
from ._navigation import (
    Agent,
    NavigationGrid,
    NavigationKey,
    PassageResult,
    PathResult,
    ReachabilityResult,
    find_path,
)
from ._physics import Contact, SimulationResult, StabilityResult, create_backend
from ._state import ConsequenceSet, WorldSnapshot, snapshot_indexes

if TYPE_CHECKING:
    from ._batch import BranchBatch, Futures
    from ._branch import WorldBranch
    from .backends.base import PhysicsBackend

ObjectReference: TypeAlias = str | WorldObject
AgentReference: TypeAlias = str | Agent
EntityReference: TypeAlias = str | WorldObject | Agent


class ObjectNotFoundError(LookupError):
    """Raised when an object name or id is absent from a world."""


class AmbiguousObjectError(LookupError):
    """Raised when a name identifies more than one object."""


class World:
    """An immutable-indexed collection of objects and deterministic AABB queries.

    Coordinates are interpreted in ``units`` (meters by default). Predicates use
    world-axis-aligned bounding boxes, which makes results deterministic and
    independent of the mesh/physics backend. Exact mesh predicates may be added
    later as explicit backend capabilities.
    """

    def __init__(
        self,
        objects: Iterable[WorldObject] = (),
        *,
        units: str = "m",
        navigation_resolution: float = 0.25,
        navigation_margin: float = 2.0,
        build_graph: bool = True,
        backend: Literal["cpu", "cuda"] = "cpu",
    ) -> None:
        if not units.strip():
            raise ValueError("units must not be empty")
        if navigation_resolution <= 0.0 or navigation_margin <= 0.0:
            raise ValueError("navigation resolution and margin must be positive")
        if backend == "cuda":
            from ._accelerators import require_cuda

            require_cuda()
        self.units = units
        self.compute_backend = backend
        self.navigation_resolution = float(navigation_resolution)
        self.navigation_margin = float(navigation_margin)
        self._build_graph = build_graph
        self._by_id: dict[str, WorldObject] = {}
        self._by_name: dict[str, list[WorldObject]] = {}
        self._agents_by_id: dict[str, Agent] = {}
        self._agent_names: dict[str, list[Agent]] = {}
        self._navigation_cache: dict[NavigationKey, PathResult] = {}
        self._articulations: dict[str, Articulation] = {}
        self._motion_cache: dict[MotionKey, MotionResult] = {}
        self._simulation_results: list[SimulationResult] = []
        self._physics_backends: dict[str, PhysicsBackend] = {}
        self._lineage_id = uuid4().hex
        self._version = 0
        self._snapshot_cache: WorldSnapshot | None = None
        self._snapshot_graph_revision = -1
        self.graph = RealityGraph(self)
        for object_ in objects:
            self.add(object_)

    @property
    def objects(self) -> tuple[WorldObject, ...]:
        """Objects in stable insertion order."""
        return tuple(self._by_id.values())

    def add(self, object_: WorldObject) -> WorldObject:
        """Add an object, assigning a predictable id if it has none."""
        visibility_queries = self.graph.visibility_query_keys()
        navigation_queries = tuple(self._navigation_cache)
        motion_queries = tuple(self._motion_cache)
        assigned_id = object_.id or f"object-{len(self._by_id) + 1}"
        if assigned_id in self._by_id:
            raise ValueError(f"duplicate object id: {assigned_id!r}")
        registered = replace(object_, id=assigned_id)
        self._by_id[registered.id] = registered
        self._by_name.setdefault(registered.name, []).append(registered)
        if self._build_graph:
            self.graph.refresh_object(registered)
        for target_id, viewer_id in visibility_queries:
            self.visible(target_id, from_=viewer_id)
        self._recalculate_navigation(navigation_queries)
        self._recalculate_motion(motion_queries)
        self._version += 1
        self._snapshot_cache = None
        return registered

    def update_transform(self, reference: ObjectReference, transform: Transform) -> WorldObject:
        """Replace an object's transform and incrementally refresh its graph edges."""
        current = self.object(reference)
        visibility_queries = self.graph.visibility_query_keys()
        navigation_queries = tuple(self._navigation_cache)
        motion_queries = tuple(self._motion_cache)
        updated = replace(current, transform=transform)
        self._by_id[updated.id] = updated
        self._by_name[updated.name] = [
            updated if object_.id == updated.id else object_
            for object_ in self._by_name[updated.name]
        ]
        self.graph.refresh_object(updated)
        self._restore_articulation_relationships((updated,))
        for target_id, viewer_id in visibility_queries:
            self.visible(target_id, from_=viewer_id)
        self._recalculate_navigation(navigation_queries)
        self._recalculate_motion(motion_queries)
        self._version += 1
        self._snapshot_cache = None
        return updated

    def move(
        self,
        reference: ObjectReference,
        *,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
    ) -> WorldObject:
        """Translate one object without introducing world branching semantics."""
        current = self.object(reference)
        position = current.position
        transform = Transform(
            position=(position[0] + x, position[1] + y, position[2] + z),
            rotation=current.rotation,
            scale=current.scale,
        )
        return self.update_transform(current, transform)

    def object(self, reference: ObjectReference) -> WorldObject:
        """Resolve an object by id, unique name, or already-resolved object."""
        if isinstance(reference, WorldObject):
            if reference.id and reference.id in self._by_id:
                return self._by_id[reference.id]
            raise ObjectNotFoundError(f"object is not registered: {reference.name!r}")
        if reference in self._by_id:
            return self._by_id[reference]
        matches = self._by_name.get(reference, [])
        if not matches:
            raise ObjectNotFoundError(f"no object named or identified {reference!r}")
        if len(matches) > 1:
            raise AmbiguousObjectError(
                f"name {reference!r} identifies {len(matches)} objects; use an id"
            )
        return matches[0]

    def __getitem__(self, reference: str) -> WorldObject | ArticulatedObject:
        object_ = self.object(reference)
        articulation = self._articulations.get(object_.id)
        return (
            ArticulatedObject(object_, articulation, self) if articulation is not None else object_
        )

    def articulate(
        self,
        reference: ObjectReference,
        *,
        joint: str,
        axis: Vector3,
        limits: tuple[float, float],
        pivot: Vector3 = (0.0, 0.0, 0.0),
        current: float = 0.0,
        angular_resolution: float = 1.0,
        linear_resolution: float = 0.01,
    ) -> ArticulatedObject:
        """Attach explicit deterministic joint metadata to an object."""
        object_ = self.object(reference)
        if len(limits) != 2:
            raise ValueError("limits must contain minimum and maximum")
        if joint == "revolute":
            joint_value: RevoluteJoint | PrismaticJoint = RevoluteJoint(
                axis=axis,
                minimum=float(limits[0]),
                maximum=float(limits[1]),
                current=float(current),
                pivot=pivot,
                angular_resolution=float(angular_resolution),
            )
        elif joint == "prismatic":
            joint_value = PrismaticJoint(
                axis=axis,
                minimum=float(limits[0]),
                maximum=float(limits[1]),
                current=float(current),
                linear_resolution=float(linear_resolution),
            )
        else:
            raise ValueError("joint must be 'revolute' or 'prismatic'")
        articulation = Articulation(object_.id, joint_value)
        self._articulations[object_.id] = articulation
        self.graph.record_articulation(object_, articulation)
        self._snapshot_cache = None
        return ArticulatedObject(object_, articulation, self)

    def _motion_query(self, object_id: str, kind: str, requested: float) -> MotionResult:
        key = (object_id, kind, requested)
        cached = self._motion_cache.get(key)
        if cached is not None:
            return cached
        object_ = self.object(object_id)
        articulation = self._articulations.get(object_id)
        if articulation is None:
            raise ValueError(f"object {object_.name!r} has no articulation metadata")
        if articulation.joint.kind != kind:
            raise TypeError(f"object {object_.name!r} uses a {articulation.joint.kind} joint")
        result = analyze_motion(self, object_, articulation, requested)
        self._motion_cache[key] = result
        self.graph.record_motion(object_, result)
        return result

    def can_open(self, reference: ObjectReference, *, degrees: float) -> MotionResult:
        return self._motion_query(self.object(reference).id, "revolute", float(degrees))

    def can_extend(self, reference: ObjectReference, *, distance: float) -> MotionResult:
        return self._motion_query(self.object(reference).id, "prismatic", float(distance))

    def set_physics(
        self,
        reference: ObjectReference,
        *,
        mass: float = 1.0,
        dynamic: bool = False,
        collision_shape: Literal["box"] = "box",
        friction: float = 0.5,
        restitution: float = 0.0,
        center_of_mass: Vector3 = (0.0, 0.0, 0.0),
    ) -> WorldObject:
        """Set explicit backend-neutral rigid-body properties on one object."""
        current = self.object(reference)
        updated = replace(
            current,
            physical=PhysicalProperties(
                mass=mass,
                dynamic=dynamic,
                collision_shape=collision_shape,
                friction=friction,
                restitution=restitution,
                center_of_mass=center_of_mass,
            ),
        )
        return self._replace_object(current, updated)

    def simulate(
        self,
        *,
        seconds: float,
        time_step: float = 1.0 / 240.0,
        backend: str = "cpu",
        gravity: Vector3 = (0.0, 0.0, -9.81),
        forces: dict[str, tuple[Vector3, float]] | None = None,
    ) -> SimulationResult:
        """Run an isolated fixed-step backend simulation and apply dynamic outcomes."""
        engine = self._physics_backends.get(backend)
        if engine is None:
            engine = create_backend(backend)
            self._physics_backends[backend] = engine
        result = engine.simulate(
            self.objects,
            seconds=float(seconds),
            time_step=float(time_step),
            gravity=gravity,
            forces=forces or {},
        )
        self._apply_simulation_transforms(
            {body.object_id: body.final_transform for body in result.bodies}
        )
        self._simulation_results.append(result)
        return result

    def drop(
        self,
        reference: ObjectReference,
        *,
        height: float,
        seconds: float = 2.0,
        backend: str = "cpu",
    ) -> SimulationResult:
        """Raise an object, make it dynamic, and simulate its fall."""
        if height < 0.0:
            raise ValueError("height must be non-negative")
        object_ = self.object(reference)
        if not object_.dynamic:
            self.set_physics(
                object_,
                mass=object_.mass,
                dynamic=True,
                friction=object_.friction,
                restitution=object_.restitution,
                center_of_mass=object_.center_of_mass,
            )
        self.move(reference, z=height)
        return self.simulate(seconds=seconds, backend=backend)

    def push(
        self,
        reference: ObjectReference,
        *,
        force: Vector3,
        duration: float = 0.2,
        seconds: float = 1.0,
        backend: str = "cpu",
    ) -> SimulationResult:
        """Apply a constant world-space force for part of a simulation."""
        if duration < 0.0:
            raise ValueError("duration must be non-negative")
        object_ = self.object(reference)
        if not object_.dynamic:
            self.set_physics(
                object_,
                mass=object_.mass,
                dynamic=True,
                friction=object_.friction,
                restitution=object_.restitution,
                center_of_mass=object_.center_of_mass,
            )
            object_ = self.object(reference)
        return self.simulate(
            seconds=max(seconds, duration),
            backend=backend,
            forces={object_.id: (force, duration)},
        )

    def contacts(self, reference: ObjectReference) -> tuple[Contact, ...]:
        """Return deterministic current AABB contacts, including the z=0 ground."""
        object_ = self.object(reference)
        contacts: list[Contact] = []
        if object_.bounds.minimum[2] <= 1e-8:
            contacts.append(
                Contact(
                    object_a_id=object_.id,
                    object_b_id=None,
                    point=(object_.bounds.center[0], object_.bounds.center[1], 0.0),
                    normal=(0.0, 0.0, 1.0),
                    separation=object_.bounds.minimum[2],
                )
            )
        for candidate in self.objects:
            if candidate.id != object_.id and object_.bounds.touching(candidate.bounds):
                contacts.append(
                    Contact(
                        object_a_id=object_.id,
                        object_b_id=candidate.id,
                        point=object_.bounds.center,
                        normal=(0.0, 0.0, 1.0),
                        separation=0.0,
                    )
                )
        return tuple(contacts)

    def stable(self, reference: ObjectReference) -> StabilityResult:
        """Check whether the projected center of mass lies in a rectangular support union."""
        object_ = self.object(reference)
        center = tuple(
            object_.bounds.center[index] + object_.center_of_mass[index] for index in range(3)
        )
        supports = tuple(
            candidate
            for candidate in self.objects
            if candidate.id != object_.id
            and abs(candidate.bounds.maximum[2] - object_.bounds.minimum[2]) <= 1e-3
            and candidate.bounds.minimum[0] <= center[0] <= candidate.bounds.maximum[0]
            and candidate.bounds.minimum[1] <= center[1] <= candidate.bounds.maximum[1]
        )
        if object_.bounds.minimum[2] <= 1e-3:
            return StabilityResult(
                True,
                object_,
                (),
                "The projected center of mass is supported by the ground plane.",
                center,  # type: ignore[arg-type]
                None,
            )
        if supports:
            region = (
                min(item.bounds.minimum[0] for item in supports),
                max(item.bounds.maximum[0] for item in supports),
                min(item.bounds.minimum[1] for item in supports),
                max(item.bounds.maximum[1] for item in supports),
            )
            return StabilityResult(
                True,
                object_,
                supports,
                "The projected center of mass lies within a supporting surface.",
                center,  # type: ignore[arg-type]
                region,
            )
        return StabilityResult(
            False,
            object_,
            (),
            "The center of mass has no supporting surface beneath it.",
            center,  # type: ignore[arg-type]
            None,
        )

    def _replace_object(self, current: WorldObject, updated: WorldObject) -> WorldObject:
        """Replace metadata without treating it as a geometric transform mutation."""
        self._by_id[updated.id] = updated
        self._by_name[updated.name] = [
            updated if object_.id == updated.id else object_
            for object_ in self._by_name[updated.name]
        ]
        self._version += 1
        self._snapshot_cache = None
        return updated

    def _apply_simulation_transform(self, object_id: str, transform: Transform) -> None:
        self._apply_simulation_transforms({object_id: transform})

    def _apply_simulation_transforms(self, transforms: dict[str, Transform]) -> None:
        """Apply one simulation result atomically before refreshing graph edges.

        A fixed-step solve can move many bodies.  Updating them one-by-one would
        repeatedly recompute relationships between bodies that all changed in the
        same solve.  Applying the value-object replacements first lets the graph
        refresh their combined dependency frontier exactly once.
        """
        updated: list[WorldObject] = []
        for object_id, transform in transforms.items():
            current = self.object(object_id)
            if transform == current.transform:
                continue
            replacement = replace(current, transform=transform)
            self._by_id[object_id] = replacement
            self._by_name[replacement.name] = [
                replacement if object_.id == object_id else object_
                for object_ in self._by_name[replacement.name]
            ]
            updated.append(replacement)
        if not updated:
            return
        if self._build_graph:
            visibility_queries = self.graph.visibility_query_keys()
            navigation_queries = tuple(self._navigation_cache)
            motion_queries = tuple(self._motion_cache)
            self.graph.refresh_objects(tuple(updated))
            self._restore_articulation_relationships(updated)
            for target_id, viewer_id in visibility_queries:
                self.visible(target_id, from_=viewer_id)
            self._recalculate_navigation(navigation_queries)
            self._recalculate_motion(motion_queries)
        self._version += 1
        self._snapshot_cache = None

    def _restore_articulation_relationships(self, objects: Iterable[WorldObject]) -> None:
        """Restore semantic joint edges after geometric graph invalidation."""
        for object_ in objects:
            articulation = self._articulations.get(object_.id)
            if articulation is not None:
                self.graph.record_articulation(object_, articulation)

    def _recalculate_motion(self, queries: tuple[MotionKey, ...]) -> None:
        if not queries:
            return
        self._motion_cache.clear()
        self.graph.invalidate_motion_relationships()
        for object_id, kind, requested in queries:
            self._motion_query(object_id, kind, requested)

    def agent(
        self,
        name: str,
        *,
        height: float | None = None,
        radius: float | None = None,
        position: Vector3 = (0.0, 0.0, 0.0),
        step_height: float = 0.0,
        max_slope: float | None = None,
    ) -> Agent:
        """Create an agent, or look one up by name when dimensions are omitted."""
        if height is None and radius is None:
            matches = self._agent_names.get(name, [])
            if not matches:
                raise ObjectNotFoundError(f"no agent named {name!r}")
            if len(matches) > 1:
                raise AmbiguousObjectError(f"name {name!r} identifies multiple agents; use an id")
            return matches[0]
        if height is None or radius is None:
            raise ValueError("height and radius must both be provided when creating an agent")
        assigned_id = f"agent-{len(self._agents_by_id) + 1}"
        created = Agent(
            id=assigned_id,
            name=name,
            position=tuple(float(value) for value in position),  # type: ignore[arg-type]
            height=float(height),
            radius=float(radius),
            step_height=float(step_height),
            max_slope=float(max_slope) if max_slope is not None else None,
            _world=self,
        )
        self._agents_by_id[created.id] = created
        self._agent_names.setdefault(created.name, []).append(created)
        self._version += 1
        self._snapshot_cache = None
        return created

    def resolve_agent(self, reference: AgentReference) -> Agent:
        if isinstance(reference, Agent):
            if reference.id in self._agents_by_id:
                return self._agents_by_id[reference.id]
            raise ObjectNotFoundError(f"agent is not registered: {reference.name!r}")
        if reference in self._agents_by_id:
            return self._agents_by_id[reference]
        return self.agent(reference)

    def entity(self, reference: EntityReference) -> WorldObject | Agent:
        if isinstance(reference, Agent):
            return self.resolve_agent(reference)
        if isinstance(reference, WorldObject):
            return self.object(reference)
        try:
            return self.object(reference)
        except ObjectNotFoundError:
            return self.resolve_agent(reference)

    def navigation_grid(self, agent: AgentReference, target: ObjectReference) -> NavigationGrid:
        resolved_agent = self.resolve_agent(agent)
        target_object = self.object(target)
        return NavigationGrid.build(
            self,
            resolved_agent,
            target_object,
            resolution=self.navigation_resolution,
            margin=self.navigation_margin,
        )

    def _path_for_agent(self, agent: Agent, target: ObjectReference) -> PathResult:
        resolved_agent = self.resolve_agent(agent)
        target_object = self.object(target)
        key = (resolved_agent.id, target_object.id)
        cached = self._navigation_cache.get(key)
        if cached is not None:
            return cached
        grid = self.navigation_grid(resolved_agent, target_object)
        result = find_path(grid, resolved_agent, target_object)
        self._navigation_cache[key] = result
        self.graph.record_navigation(resolved_agent, target_object, result)
        return result

    def reachable(self, agent: AgentReference, target: ObjectReference) -> ReachabilityResult:
        resolved_agent = self.resolve_agent(agent)
        path = self._path_for_agent(resolved_agent, target)
        available = (
            2.0 * (resolved_agent.radius + path.minimum_clearance)
            if path.reachable and path.minimum_clearance is not None
            else (None if path.reachable else 0.0)
        )
        return ReachabilityResult(
            reachable=path.reachable,
            path=path,
            required_clearance=resolved_agent.radius * 2.0,
            available_clearance=available,
            blocked_by=path.blocked_by,
            reason=path.reason,
            evidence={"agent_id": resolved_agent.id, "path": path},
        )

    def can_pass(self, agent: AgentReference, opening: ObjectReference) -> PassageResult:
        resolved_agent = self.resolve_agent(agent)
        opening_object = self.object(opening)
        extents = opening_object.bounds.extents
        available_width = max(extents[0], extents[1])
        available_height = extents[2]
        required_width = resolved_agent.radius * 2.0
        passes = available_width >= required_width and available_height >= resolved_agent.height
        return PassageResult(
            can_pass=passes,
            required_width=required_width,
            available_width=available_width,
            required_height=resolved_agent.height,
            available_height=available_height,
            reason=(
                "Opening provides the required width and height."
                if passes
                else "Opening is narrower or shorter than the agent's physical dimensions."
            ),
            objects=(opening_object,),
            evidence={"agent_id": resolved_agent.id, "opening_bounds": opening_object.bounds},
        )

    def _recalculate_navigation(self, queries: tuple[NavigationKey, ...]) -> None:
        if not queries:
            return
        self._navigation_cache.clear()
        self.graph.invalidate_navigation_relationships()
        for agent_id, target_id in queries:
            self._path_for_agent(self.resolve_agent(agent_id), target_id)

    def distance(self, a: ObjectReference, b: ObjectReference) -> PredicateResult[float]:
        first, second = self._pair(a, b)
        distance = first.bounds.distance_to(second.bounds)
        return PredicateResult(
            value=distance,
            measurement=distance,
            units=self.units,
            reason="Euclidean separation between world-axis-aligned bounding boxes.",
            objects=(first, second),
            evidence={"bounds_a": first.bounds, "bounds_b": second.bounds},
        )

    def intersects(self, a: ObjectReference, b: ObjectReference) -> PredicateResult[bool]:
        first, second = self._pair(a, b)
        value = first.bounds.intersects(second.bounds)
        return self._boolean_result(
            value,
            first,
            second,
            (
                "World-axis-aligned bounding boxes overlap or touch."
                if value
                else "Bounding boxes are disjoint."
            ),
        )

    def above(self, a: ObjectReference, b: ObjectReference) -> PredicateResult[bool]:
        first, second = self._pair(a, b)
        clearance = first.bounds.minimum[2] - second.bounds.maximum[2]
        return self._boolean_result(
            clearance >= 0.0,
            first,
            second,
            "First object is at or above the second object's top Z plane.",
            measurement=clearance,
        )

    def below(self, a: ObjectReference, b: ObjectReference) -> PredicateResult[bool]:
        first, second = self._pair(a, b)
        clearance = second.bounds.minimum[2] - first.bounds.maximum[2]
        return self._boolean_result(
            clearance >= 0.0,
            first,
            second,
            "First object is at or below the second object's bottom Z plane.",
            measurement=clearance,
        )

    def inside(self, a: ObjectReference, b: ObjectReference) -> PredicateResult[bool]:
        first, second = self._pair(a, b)
        value = second.bounds.contains(first.bounds)
        return self._boolean_result(
            value,
            first,
            second,
            "First object's bounds are fully contained by the second object's bounds."
            if value
            else "First object's bounds extend outside the second object's bounds.",
        )

    def contains(self, a: ObjectReference, b: ObjectReference) -> PredicateResult[bool]:
        """Return whether the first object's bounds fully contain the second's."""
        first, second = self._pair(a, b)
        value = first.bounds.contains(second.bounds)
        return self._boolean_result(
            value,
            first,
            second,
            "First object's bounds fully contain the second object's bounds."
            if value
            else "Second object's bounds extend outside the first object's bounds.",
        )

    def touching(self, a: ObjectReference, b: ObjectReference) -> PredicateResult[bool]:
        """Return whether two AABBs share a boundary without volumetric overlap."""
        first, second = self._pair(a, b)
        value = first.bounds.touching(second.bounds)
        return self._boolean_result(
            value,
            first,
            second,
            "Bounding boxes touch at a boundary without overlapping in volume."
            if value
            else "Bounding boxes do not have boundary-only contact.",
        )

    def near(
        self, a: ObjectReference, b: ObjectReference, *, within: float = 1.0
    ) -> PredicateResult[bool]:
        if within < 0:
            raise ValueError("within must be non-negative")
        first, second = self._pair(a, b)
        distance = first.bounds.distance_to(second.bounds)
        return PredicateResult(
            value=distance <= within,
            measurement=distance,
            units=self.units,
            reason=(
                "Bounding-box separation is "
                f"{'within' if distance <= within else 'outside'} {within:g} {self.units}."
            ),
            objects=(first, second),
            evidence={"threshold": within, "bounds_a": first.bounds, "bounds_b": second.bounds},
        )

    def visible(self, target: ObjectReference, *, from_: ObjectReference) -> PredicateResult[bool]:
        """Test deterministic line-of-sight from a viewer's centre to target samples.

        Rays are intersected with world-axis-aligned bounds. This gives a
        backend-neutral, reproducible baseline. Mesh-exact visibility is a
        future opt-in capability rather than a silent change in semantics.
        """
        target_object, viewer = self._pair(target, from_)
        origin = viewer.bounds.center
        samples = (target_object.bounds.center, *target_object.bounds.corners)
        occluders: set[WorldObject] = set()
        visible_count = 0
        for sample in samples:
            direction, length = _ray_to(origin, sample)
            blocked = False
            if length > 1e-12:
                for candidate in self.objects:
                    if candidate.id in {target_object.id, viewer.id}:
                        continue
                    hit = _ray_bounds_distance(origin, direction, candidate.bounds)
                    if hit is not None and 1e-9 < hit < length - 1e-9:
                        occluders.add(candidate)
                        blocked = True
                if not blocked:
                    visible_count += 1
            else:
                visible_count += 1
        fraction = visible_count / len(samples)
        result = PredicateResult(
            value=fraction > 0.0,
            measurement=target_object.bounds.distance_to(viewer.bounds),
            units=self.units,
            reason=(
                "At least one deterministic target sample has unobstructed line of sight."
                if fraction > 0.0
                else "Every deterministic target sample is blocked by scene geometry."
            ),
            objects=(target_object, viewer),
            evidence={
                "visibility_fraction": fraction,
                "occluding_objects": tuple(sorted(occluders, key=lambda object_: object_.id)),
                "sample_count": len(samples),
            },
        )
        self.graph.record_visibility(target_object, viewer, result)
        return result

    def relationships(self, reference: EntityReference) -> tuple[Relationship, ...]:
        """Return graph relationships involving an object."""
        return self.graph.relationships(reference)

    def snapshot(self) -> WorldSnapshot:
        """Capture immutable state while sharing frozen object and mesh references."""
        if self._snapshot_cache is None or self._snapshot_graph_revision != self.graph.revision:
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
                motion=tuple(
                    (object_id, kind, requested, result)
                    for (object_id, kind, requested), result in self._motion_cache.items()
                ),
                relationships=self.graph.all_relationships(),
                visibility=self.graph.visibility_records(),
                created_at=datetime.now(UTC),
            )
            self._snapshot_graph_revision = self.graph.revision
        return self._snapshot_cache

    def branch(self) -> WorldBranch:
        """Create an O(1)-state copy-on-write alternate world from a cached snapshot."""
        from ._branch import WorldBranch

        return WorldBranch(self.snapshot())

    def branches(self, count: int, *, backend: Literal["cpu", "cuda"] | None = None) -> BranchBatch:
        """Create a compact batch of translation deltas over one shared snapshot."""
        from ._batch import BranchBatch

        selected = backend or self.compute_backend
        return BranchBatch(self, count, backend=selected)

    def futures(self, count: int, *, backend: Literal["cpu", "cuda"] | None = None) -> Futures:
        """Create compact, lazily materialized alternate futures over one snapshot."""
        from ._batch import Futures

        selected = backend or self.compute_backend
        return Futures(self, count, backend=selected)

    def compare(self, branch_a: WorldBranch, branch_b: WorldBranch) -> ConsequenceSet:
        """Compare two branches descended from this world."""
        from ._branch import compare_states

        if branch_a._lineage_id != self._lineage_id or branch_b._lineage_id != self._lineage_id:
            raise ValueError("both branches must descend from this world")
        first = {object_.id: object_ for object_ in branch_a.objects}
        second = {object_.id: object_ for object_ in branch_b.objects}
        changed_ids = {
            object_id
            for object_id in first.keys() & second.keys()
            if first[object_id].transform != second[object_id].transform
        }
        return compare_states(
            branch_a.objects,
            branch_b.objects,
            changed_ids,
            branch_a.graph.visibility_records(),
            branch_b.graph.visibility_records(),
            branch_a._navigation_records(),
            branch_b._navigation_records(),
            branch_a._motion_records(),
            branch_b._motion_records(),
            instrumentation=branch_a.instrumentation + branch_b.instrumentation,
        )

    def _pair(self, a: ObjectReference, b: ObjectReference) -> tuple[WorldObject, WorldObject]:
        return self.object(a), self.object(b)

    def _boolean_result(
        self,
        value: bool,
        first: WorldObject,
        second: WorldObject,
        reason: str,
        *,
        measurement: float | None = None,
    ) -> PredicateResult[bool]:
        return PredicateResult(
            value=value,
            measurement=measurement,
            units=self.units if measurement is not None else None,
            reason=reason,
            objects=(first, second),
            evidence={"bounds_a": first.bounds, "bounds_b": second.bounds},
        )


def _ray_to(origin: Vector3, target: Vector3) -> tuple[Vector3, float]:
    vector = tuple(target[index] - origin[index] for index in range(3))
    length = sqrt(sum(component * component for component in vector))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0), 0.0
    return tuple(component / length for component in vector), length  # type: ignore[return-value]


def _ray_bounds_distance(origin: Vector3, direction: Vector3, bounds: Bounds) -> float | None:
    """Return first ray/AABB hit distance using the slab algorithm."""
    enter, exit_ = float("-inf"), float("inf")
    for index in range(3):
        component = direction[index]
        if abs(component) <= 1e-12:
            if origin[index] < bounds.minimum[index] or origin[index] > bounds.maximum[index]:
                return None
            continue
        first = (bounds.minimum[index] - origin[index]) / component
        second = (bounds.maximum[index] - origin[index]) / component
        enter = max(enter, min(first, second))
        exit_ = min(exit_, max(first, second))
        if enter > exit_:
            return None
    return exit_ if enter < 0.0 else enter
