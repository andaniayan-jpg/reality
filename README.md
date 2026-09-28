# reality

`reality` is a small, typed foundation for treating a physical 3D scene as a Python object. It loads common mesh formats today and exposes deterministic spatial queries without committing the public API to a physics or rendering engine.

## 60-second start

```bash
python -m pip install reality
```

```python
import reality

world = reality.load("room.glb")

distance = world.distance("Chair", "Table")
print(distance.value, distance.units)  # 0.82 m

if world.near("Chair", "Table", within=1.0).value:
    print("The chair is within one metre of the table.")

visibility = world.visible("Television", from_="Sofa")
print(visibility.value, visibility.visibility_fraction)

for relationship in world.relationships("Chair"):
    print(relationship.type.value, relationship.target.name)

future = world.branch()
future.move("Table", x=1.0)

for consequence in future.consequences():
    print(consequence)
```

Every query returns a `PredicateResult`, so callers can inspect `value`, `measurement`, `units`, `reason`, `evidence`, and the involved `objects`.

## Current scope

- Python 3.11+ and typed public APIs
- GLB, glTF, and OBJ loading through Trimesh
- `World`, `WorldObject`, `Transform`, `Bounds`, and `PredicateResult`
- Deterministic AABB-based `distance`, `intersects`, `above`, `below`, `inside`, and `near` queries
- An incrementally maintainable `RealityGraph` with `near`, `above`, `below`,
  `inside`, `contains`, `intersects`, `touching`, and queried `visible_from` edges
- Deterministic AABB ray visibility through `world.visible(target, from_=viewer)`
- Immutable snapshots, copy-on-write world branches, typed transform changes,
  dependency-aware recomputation, and serializable consequence reports
- Dimensioned agents with deterministic CPU occupancy grids, A* paths,
  reachability, passage checks, clearance evidence, and SVG debug export

## Agents and navigation

```python
person = world.agent(name="Person", height=1.75, radius=0.30)

path = person.path_to("Exit")
print(path.reachable, path.distance, path.minimum_clearance)
print([object_.name for object_ in path.blocked_by])

person.can_reach("Kitchen")
person.can_pass("Door")
person.clearance_to("Exit")
```

See `examples/navigation.py` and `examples/navigation_branch.py` for runnable programmatic scenes.

The current geometry layer intentionally uses world-axis-aligned bounding boxes. This is predictable, fast, and backend-neutral; it is not an exact triangle-mesh collision system.

Run the examples with `python examples/query_room.py`, `python examples/visibility.py`, and `python examples/relationships.py` after substituting your scene path and object names.

## Development

```bash
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
pytest
```

See [PROJECT.md](PROJECT.md), [ARCHITECTURE.md](ARCHITECTURE.md), [API_DESIGN.md](API_DESIGN.md), [ROADMAP.md](ROADMAP.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

Licensed under [Apache-2.0](LICENSE).

## Articulation, physics, and batch branches

Joints are explicit. Reality samples the entire swept AABB path and refines the first
collision boundary; it does not claim to infer hinges from arbitrary meshes.

```python
door = world.articulate(
    "Door", joint="revolute", pivot=(0, 0, 0), axis=(0, 0, 1), limits=(0, 110)
)
print(door.can_rotate(90).reason)
```

Install the replaceable MuJoCo CPU physics backend with `pip install -e ".[physics]"`:

```python
world.set_physics("Box", mass=2.0, dynamic=True)
result = world.push("Box", force=(20, 0, 0), duration=0.2)
print(result.body("Box").final_transform)
```

Physical defaults are explicit: static, 1 kg, AABB box collider, friction 0.5,
restitution 0, and center-of-mass offset `(0, 0, 0)`. Semantic materials are not
inferred.

`world.branches(10_000)` shares one immutable snapshot and stores only `N x 3`
translation arrays for changed objects. CPU collision-batch evaluation is implemented.
Warp is optional. Reality now contains two custom Warp kernels for batched transforms and
AABB overlap, with CPU reference implementations and synchronized timing/validation
tools. CUDA is never claimed active without a usable driver, successful launches, and
CPU/GPU parity evidence.
