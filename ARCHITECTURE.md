# Architecture

```
public API: reality.load, World, WorldObject, Transform, Bounds, PredicateResult
                              |
                      backend-neutral core
                              |
                       RealityGraph (edges reference WorldObjects)
                              |
              snapshots -> branch delta/graph overlay -> consequences
                              |
                  Trimesh loader adapter (today)
```

`_models.py` contains immutable data/value objects. `World` owns lookup indexes and evaluates spatial predicates using the world-space axis-aligned bounds of its objects. `_loaders.py` is the only module that imports Trimesh; it turns a Trimesh scene graph into `WorldObject` instances while retaining the source mesh as an opaque reference.

This split means a future USD, Omniverse, renderer, or physics adapter can produce the same core objects without changing application code. Exact mesh queries should arrive as explicitly named capabilities rather than silently changing the existing AABB semantics.

The Z axis is vertical for `above` and `below`. The default coordinate unit is metres (`m`), configurable when constructing a `World`.

## Reality Graph and updates

`World.graph` is a `RealityGraph` built from known deterministic spatial facts. `Relationship` stores references to the already-loaded `WorldObject` instances, never copied mesh data. `world.relationships("Cup")` returns all incident graph edges.

The graph indexes each edge by both object ids. `World.update_transform()` and `World.move()` invalidate only edges incident to the changed object, then recompute that object against the rest of the scene. Relationships entirely between unaffected objects stay in place. Visibility edges are query-driven and are invalidated with either involved object; they are deliberately not eagerly recomputed.

Visibility casts rays from the viewer AABB centre to the target centre and corners, treating all other world AABBs as occluders. It returns the visible sample fraction and the objects that blocked at least one ray. This is deterministic but conservative/approximate compared with future mesh-exact visibility.

## Snapshots and persistent branches

`World.snapshot()` returns an immutable `WorldSnapshot`. Its object tuple, lookup indexes, relationships, and known visibility results are stable views. Because `WorldObject`, transforms, and bounds are immutable, snapshots safely retain references to existing objects and opaque mesh data instead of copying geometry.

`World.branch()` creates a `WorldBranch` over a cached snapshot. The branch maintains:

- an object-id-to-replacement delta for changed objects;
- an ordered `ChangeSet` containing `MoveObject`, `RotateObject`, and `ScaleObject` records;
- a `RealityGraph` overlay that points at snapshot edges and stores only recalculated edges;
- `GraphUpdateStats` for predicates present before changes, invalidated, recalculated, and reused.

On a transform change, only pairs involving the changed object are recalculated. Base graph edges between unchanged objects remain the same Python objects. Known visibility queries are recalculated because any moved object may become or cease to be an occluder; such a result is classified as downstream when neither visibility endpoint moved.

Branches use the exact snapshot they were created from, so later mutations to the source `World` cannot alter an existing branch.

## Consequence comparison

`WorldBranch.consequences()` compares its current state with its base snapshot. It evaluates distance and existing graph predicates only across the union of changed-object dependency frontiers, then compares known visibility results. `World.compare(a, b)` applies the same engine to two sibling branches.

`ConsequenceSet` contains typed `Consequence` records plus the branch `ChangeSet` and recomputation instrumentation. `to_dict()` and `to_json()` intentionally serialize object identity and geometric evidence without attempting to serialize backend mesh instances.

## Navigation backend

The initial navigation backend is deliberately replaceable and CPU-only. Each query projects relevant world AABBs onto an XY occupancy grid, expands obstacles by the querying agent’s radius, and runs deterministic 8-connected A*. Z is up; the agent position’s Z value is its foot/ground elevation. Geometry blocks movement when it overlaps the volume between step height and agent height.

The grid covers the start/target rectangle plus `World.navigation_margin` (2 m by default), at `World.navigation_resolution` (0.25 m by default). The target object is treated as a destination marker and excluded from obstacles. This finite query envelope is an explicit assumption: callers needing larger detours should increase the margin.

`max_slope` is retained in the agent model and evidence, but the current projected grid is flat and does not yet evaluate terrain slope. `can_pass()` interprets an opening object’s largest horizontal AABB extent as aperture width and its Z extent as aperture height.

Navigation queries are lazy and cached by agent/target id. Their `reachable_by`, `unreachable_by`, and `blocks_path_of` edges are stored in the Reality Graph only after a query. Any object move invalidates known navigation queries because any object may become an obstacle; only those known queries are recalculated. Branch consequence analysis compares their reachability and minimum-clearance results as downstream state.

`PathResult.export_debug()` writes a standalone SVG: green is query-local walkable space, red rectangles are radius-inflated obstacle regions, the blue polyline is the path, and a dashed line indicates a blocked direct route.

## Articulation and replaceable physics

`_articulation.py` stores explicit revolute/prismatic joints. It samples swept
world-AABBs at 1 degree or 0.01 m by default and binary-refines the first collision to
0.01 degree or 0.0001 m. Conservative AABBs can produce mesh-shape false positives;
features thinner than a sampling interval can be missed. Known motion queries are lazy
graph dependencies and are recalculated after relevant geometry changes.

`backends/base.py` defines Reality's narrow `PhysicsBackend` protocol.
`backends/mujoco.py` is the CPU reference: explicit properties become headless MuJoCo
box rigid bodies and results return through backend-neutral values. Current limitations
include AABB colliders, a z=0 plane, and no rotational state mapping or simulated joints.

## Batched branch memory layout and CUDA boundary

`_batch.py` keeps one shared snapshot, immutable base bounds, and one dense
`branch_count x 3` float64 translation array per changed object. It never builds a
complete `World` per alternative. Vectorized CPU broad-phase collision is implemented.
`_warp_ops.py` adds two custom Warp kernels: branch/object transform application and
batched AABB overlap. They have separate NumPy reference implementations and explicit
CUDA synchronization. `_accelerators.py` probes optional Warp lazily; this host cannot
validate CUDA, so the GPU audit remains `PARTIAL` until a real NVIDIA device runs it.
Graph and explanation logic remains CPU-resident by design.
