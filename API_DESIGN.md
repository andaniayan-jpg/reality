# API design

## Stable surface

```python
import reality

world = reality.load("room.glb")
object_ = world.object("Chair")
result = world.distance("Chair", "Table")
```

`World.object()` accepts an object id, a unique name, or a registered `WorldObject`. Duplicate names are permitted but require lookup by id.

`WorldObject` exposes `name`, `id`, `transform`, `position`, `rotation`, `scale`, `bounds`, and `mesh`. Bounds are world-space AABBs; `local_bounds` retains the geometry before applying its transform. Rotations are XYZ Euler angles in radians.

All predicate methods accept two object references. `near` additionally accepts `within`, defaulting to `1.0` in `World.units`. `distance` returns `PredicateResult[float]`; the remaining methods return `PredicateResult[bool]`.

## Graph and visibility

```python
visibility = world.visible("Television", from_="Sofa")
assert visibility.value
print(visibility.visibility_fraction)
print([object_.name for object_ in visibility.occluding_objects])

for edge in world.relationships("Cup"):
    print(edge.source.name, edge.type.value, edge.target.name)
```

`RelationshipType` includes `near`, `above`, `below`, `inside`, `contains`, `intersects`, `touching`, and `visible_from`. Graph construction records true deterministic spatial relationships. A successful `visible()` query additionally records a directed `visible_from` relationship from target to viewer.

Moving an object is explicit: `world.move("Chair", x=1.0)` or `world.update_transform("Chair", transform)`. Those methods only invalidate and refresh graph edges incident to the changed object.

## Result contract

`PredicateResult` has `value`, `measurement`, `units`, `reason`, `evidence`, and `objects`. `distance` is an alias for `measurement`, making this ergonomic:

```python
result = world.distance("Chair", "Table")
assert result.value == result.distance
```

Evidence always includes the world-space bounds involved. The immutable mapping prevents a caller accidentally altering an already-returned result.

For a visibility result, evidence additionally contains `visibility_fraction`, `occluding_objects`, and `sample_count`; the first two are surfaced as convenience properties.

## Snapshots, branches, and consequences

```python
before = world.snapshot()
future = world.branch()
future.move("Shelf", x=1.0)
future.rotate("Shelf", z=0.25)
future.scale("Shelf", x=1.1)

report = future.consequences()
for consequence in report:
    print(consequence)

payload = report.to_dict()
json_text = report.to_json()
```

`move` and `rotate` are additive; `scale` is multiplicative. Each call records an ordered, UTC-timestamped change with old/new transforms and the supplied parameters. An unchanged object returned by a branch is the same immutable `WorldObject` instance as in the snapshot. A changed object is a new value object that retains the same opaque mesh reference.

`world.compare(branch_a, branch_b)` compares sibling branches. It rejects branches from another world lineage.

## Agents and navigation

```python
person = world.agent(
    name="Person",
    position=(0.0, 0.0, 0.0),
    height=1.75,
    radius=0.30,
    step_height=0.15,
)

path = person.path_to("Exit")
reachability = world.reachable("Person", "Exit")
passage = person.can_pass("Door")
clearance = person.clearance_to("Exit")
```

`PathResult` contains `reachable`, path `points`, `distance`, `minimum_clearance`, `narrowest_point`, `blocked_by`, `reason`, and evidence. Path minimum clearance is free space from the agent body to the nearest inflated obstacle. `ReachabilityResult` adds required diameter and estimated available corridor width. Passage checks compare agent diameter and height with the opening AABB. Results expose `value` aliases where predicate-style use is convenient.

Agent category names have no behavioral meaning. Only dimensions and optional movement constraints affect navigation.

## Articulation

`World.articulate`, `can_open`, `can_extend`, and the `ArticulatedObject` handle return a
`MotionResult` with requested/maximum motion, blockers, units, reason, samples, and
evidence. Configuration is explicit, deterministic metadata. `reality.load` reads the
same schema from a `.reality.json` sidecar, glTF/GLB `extras.reality`, or an explicit
`metadata=` mapping. The schema supports `units`, `objects.<name>.articulation`, and
`objects.<name>.physics`; malformed or unknown fields raise `SceneMetadataError` rather
than being guessed or ignored. The object reference must resolve to a unique loaded
object. Later metadata sources override earlier articulation/physics fields; `units`
labels coordinates and never triggers implicit rescaling.

## Physics

`PhysicalProperties` describes mass, static/dynamic state, box collision shape,
friction, restitution, and center-of-mass offset. `simulate`, `drop`, `push`, `contacts`,
and `stable` return backend-neutral typed results. Simulation-observed consequences are
labeled separately from direct and downstream deterministic consequences. MuJoCo uses
oriented boxes built from local bounds and maps dynamic position and orientation back
to `Transform`. It caches immutable compiled topology per world/backend and creates a
fresh simulation state for every call, preserving branch isolation. Performance timing
and cache reuse are reported in `SimulationResult.evidence`.

## Branch batches

`World.branches(count)` returns a `BranchBatch`; `randomize("Object.position", ...)`
stores compact translation deltas and `evaluate(predicates=("collision",))` runs the CPU
reference batch. CUDA selection is capability-checked and never silently falls back.

`World.futures(count)` returns the named `Futures` form for large alternate-world search:

```python
from reality.predicates import collision, distance, maximize, no_collision

futures = world.futures(10_000).randomize_position(
    "Table", x=(-1.0, 1.0), y=(-0.5, 0.5), z=(0.0, 0.0), seed=7
)
evaluation = futures.evaluate([collision("Table", "Chair"), distance("Table", "Chair")])
ranked = evaluation.rank(
    constraints=[no_collision("Table", "Chair")],
    objectives=[maximize(distance("Table", "Chair"))],
)
candidate = ranked.best(1)[0]
branch = candidate.materialize()
```

`PredicateSpec` values are typed and reusable. `where()` applies hard `Condition`
constraints; `rank()` applies weighted `Objective` values; candidates stay compact until
`materialize()` or `consequences()` is called. `collision` and `distance` use world AABBs,
and batch `visibility` is a deterministic AABB ray experiment. Batched rotations/scales
are accepted and retained for future kernels, but currently raise `NotImplementedError`
when evaluated with non-default values. `BatchEvaluation.to_dict()` and
`RankedFutures.to_dict()` provide machine-readable summaries.

## Exact exploration

`World.explore()` is a convenience layer over `Futures`; it does not introduce a second
optimizer or different predicate semantics.

```python
result = world.explore(
    possibilities=100_000,
    changes=[reality.position("Shelf", x=(-1.0, 1.0))],
    constraints=[no_collision("Shelf", "Door")],
    objectives=[maximize(distance("Shelf", "Door"))],
    seed=42,
    best=10,
)
```

`PositionSearchChange` declares inclusive coordinate ranges. Candidate sampling is
deterministic for a seed, constraints are exact hard filters, and objective ties are
broken by candidate index. `ExplorationResult` exposes backend, counts, scores, compact
deltas, predicate evidence, `best()`, `to_dict()`, and `to_json()`. Returned candidates
remain lazy `FutureCandidate` values until `materialize()` is called.

`backend="auto"` selects CUDA only after the accelerator capability check succeeds;
`backend="cpu"` forces the NumPy reference path. CUDA evaluates the same documented
AABB semantics as CPU. Any future learned prioritizer is experimental, opt-in, and may
only order candidates before exact validation; it never changes valid/invalid results.
