# reality

`reality` is a small, typed foundation for treating a physical 3D scene as a Python object. It loads common mesh formats today and exposes deterministic spatial queries without committing the public API to a physics or rendering engine.

## 3D files as physical objects

`perceive.from_3d()` is a measured, uncertainty-aware entry point to the
existing mesh/CAD model, Reality Graph, and spatial queries:

```python
import reality

obj = reality.perceive.from_3d("bracket.stl", units="mm", density_kg_m3=2700)
print(obj.summary)
print(obj.surface_area, obj.volume, obj.centre_of_mass)
print(obj.estimated_mass)  # kg; estimate from the supplied density
print(obj.weak_points)     # screening candidates, not a stress calculation

# The imported mesh/B-rep, parts, hierarchy, graph and World are shared.
print(obj.model.parts, obj.graph, obj.world)

assessment = reality.reason.predict(
    "will this fail under 500 kg?", obj,
    load_axis="z", load_case="axial_compression", support="opposed_face",
    yield_strength_pa=250_000_000, yield_source="your material certificate",
)
print(assessment.safety_factor, assessment.will_fail)
```

OBJ, STL, PLY, GLB and glTF use Trimesh; STEP/STP/IGES retain B-reps with the
optional `cad` extra. URDF and SDF read supported link geometry and declared
joint hierarchy at the zero-joint pose. Static mesh USD needs the `usd` extra;
FBX/DAE/3DS need the `assimp` extra **plus native libassimp**. Native BLEND is
not parsed; Reality generates a script for a reviewed Blender export.
`reason.predict` above is a narrow sampled axial-yield screen, not FEA or a
general failure verdict. Without sufficient evidence it returns `None` for
`will_fail` and `safety_factor`. `from_3d(..., enrich=True)` may
add advisory text from a configured local model, but never changes measured
geometry. `reality.copilot("question", obj)` can use the same factual context.
No Ollama installation or model download happens during `pip install reality`.
See [3D perception guide](docs/3d-perception.md) for units, format support,
estimates and limits.

## Optional AI runtime foundation

The package now includes a provider-neutral `reality.copilot()` text entry point,
`reality.perceive.from_image()`, file-only `reality.reality.capture()`, bounded
`reality.twin.from_video()`, hardware inspection, local model discovery, and
an injectable model router. These are separate from Reality's authoritative
geometry/physics queries; generated text is never presented as a measured fact.

```python
import reality

print(reality.detect_mode())       # local unless an API key is configured
print(reality.local_setup_plan())  # inspection only; installs nothing
answer = reality.copilot("Explain how to measure this assembly")
print(answer.text)

image = reality.perceive.from_image("photo.jpg")
capture = reality.reality.capture(source="photo.jpg")
# Video support uses an optional decoder: pip install "reality[video]"
observations = reality.twin.from_video("scan.mp4")
```

`copilot()` needs an already running local Ollama engine with a compatible
installed model, or a deployed Reality AI gateway configured with
`REALITY_API_BASE` and `REALITY_API_KEY`. There is no public AI gateway in this
repository, and `pip install reality` does not install a model or guarantee an
answer. Image analysis uses the configured cloud vision provider when available,
then an installed local vision model; photos can provide observations, not
measured masses or an exact 3D world. Video currently samples at most four
frames and returns observations, not a geometric digital twin. There is no
webcam or live frame capture. See [AI runtime guide](docs/ai-runtime.md) for setup, adapters,
security, and current gaps. The [next-release plan](NEXT_RELEASE.md) gives
explicit pass/fail gates for a real cloud AI preview. The existing geometry
APIs work without AI.

## Reality Cloud developer platform

`apps/api` adds a FastAPI service that invokes this package for hosted model
analysis. It includes tenant-scoped API keys, persistent job records, local/S3
storage adapters, a responsive dashboard in `apps/web`, and official Python and
server-side JavaScript clients. See [API docs](docs/api.md),
[security](docs/security.md), and [deployment](docs/deployment.md).
The dashboard can create one-time-reveal API keys, upload and inspect models,
run geometry queries, preview GLB models, and submit edits. Mobile-number
sign-in uses Twilio Verify and requires server-side provider credentials; email
sign-in still works without them. Neither the site nor these v3/v4 foundations
are claimed as a deployed public service in this repository.
The [website guide](apps/web/README.md) explains its locally bundled WebGL
homepage, cursor-responsive 3D geometry, timed light/dark theme, and browser
verification.

## v0.2 structural 3D/CAD reading

`reality.open()` adds a model-oriented reader without changing the existing
`reality.load()` → `World` API. OBJ, STL, PLY, GLB and glTF use Trimesh; STEP/STP
uses the optional B-rep backend (`pip install "reality[cad]"`) and retains its
native CAD solids/topology.

```python
import reality

model = reality.open("motor.step")
print(model.summary())
print(model.measure("solid-1"))
print(model.topology())
```

Source units are reported rather than guessed. CAD-to-mesh export warns about
lost B-rep/assembly semantics; mesh-to-STEP export is refused. See
[docs/3d-files.md](docs/3d-files.md).

## Deterministic editing

`RealityModel.edit()` creates a copy-on-write transaction over a real source
mesh or CAD B-rep. The original import stays unchanged; a commit returns a new
model, structured history, and validation evidence.

```python
model = reality.open("bracket.step")
result = model.edit().hole("bracket", radius=3, depth=20).commit()
assert result.validate().valid
result.export("bracket-revised.step")
```

CAD edits use CadQuery/OpenCascade without flattening solids to meshes; mesh
edits use Trimesh. See [editing documentation](docs/editing.md) for supported
operations, selection, transactions, and hosted edit jobs.

## Agent and MCP integration

`RealityAgent` provides typed, provider-neutral plan → validate → preview →
execute orchestration over real Reality models. It never accepts LLM-invented
measurements as geometry evidence, and rejected edits roll back.

```python
agent = reality.RealityAgent(reality.open("fixture.glb"))
plan = agent.plan("move block x=200 mm")
preview = agent.preview(plan)
result = agent.execute(plan)
```

The MCP adapter in `apps/mcp` calls Reality Cloud rather than duplicating
geometry. It supports tenant-scoped inspection, measurement, topology,
preview/export, versioned edit plans, confirmation-gated apply, and undo. See
[agent documentation](docs/agent.md) and [MCP documentation](docs/mcp.md).

## v3 physical-AI integration foundation

`reality.integrations` provides capability-checked contracts for future Blender,
game-engine, robotics, and simulator bridges. The included `reality-scene/v1`
adapter is a strict, portable JSON interchange for explicit world bounds,
transforms, units, and rigid-body inputs. It does not claim mesh, CAD, material,
or simulator fidelity. See [V3.md](V3.md) for real-host validation gates and
[V4.md](V4.md) for the deliberately unimplemented platform design.

With the optional `reality[physics]` dependency, `MuJoCoSceneIntegration`
compiles real MJCF scenes, exchanges supported primitive geom bounds, inspects
joint/actuator/sensor declarations, and runs isolated control-range-validated
local rollouts. It cannot command hardware. Run
`python examples/mujoco_rollout.py` after installing `reality[physics]`.

The first v4 foundation is `WorldLedger`: an immutable local provenance ledger
for `WorldSnapshot` state and branch transitions. It records supplied source
digests and coordinate frames but never silently infers either. Run
`python examples/world_ledger.py` for a JSON example.

## 60-second start

```bash
python -m pip install reality
```

After installation, run `reality` (or `python -m reality`) for the package greeting.

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

For deterministic alternate-world searches, use one shared snapshot and compact deltas:

```python
from reality.predicates import collision, distance, maximize, no_collision

futures = world.futures(10_000).randomize_position(
    "Table", x=(-1.0, 1.0), y=(-0.5, 0.5), z=(0.0, 0.0), seed=7
)
ranked = futures.evaluate([collision("Table", "Sofa"), distance("Table", "Sofa")]).rank(
    constraints=[no_collision("Table", "Sofa")],
    objectives=[maximize(distance("Table", "Sofa"))],
)
selected = ranked.best(5)[0].materialize()  # only this candidate becomes a branch
```

`World.explore()` is the higher-level deterministic search API. It creates compact
futures, applies hard constraints, ranks exact predicate results, and materializes only
the returned candidates. Its default backend is CUDA when a validated CUDA device is
available, otherwise the same CPU reference semantics are used.

```python
from reality.predicates import distance, maximize, no_collision

result = world.explore(
    possibilities=100_000,
    changes=[reality.position("Table", x=(-1.0, 1.0), y=(-1.0, 1.0))],
    constraints=[no_collision("Table", "Sofa")],
    objectives=[maximize(distance("Table", "Sofa"))],
    seed=42,
)
print(result.backend, result.best(1)[0].score)
print(result.to_json())
```

Every query returns a `PredicateResult`, so callers can inspect `value`, `measurement`, `units`, `reason`, `evidence`, and the involved `objects`.

## Current scope

- Python 3.11+ and typed public APIs
- GLB, glTF, and OBJ loading through Trimesh
- Structural OBJ, STL, PLY, GLB, glTF, STEP and STP reading through `reality.open()`
- `World`, `WorldObject`, `Transform`, `Bounds`, and `PredicateResult`
- Deterministic AABB-based `distance`, `intersects`, `above`, `below`, `inside`, and `near` queries
- An incrementally maintainable `RealityGraph` with `near`, `above`, `below`,
  `inside`, `contains`, `intersects`, `touching`, and queried `visible_from` edges
- Deterministic AABB ray visibility through `world.visible(target, from_=viewer)`
- Immutable snapshots, copy-on-write world branches, typed transform changes,
  dependency-aware recomputation, and serializable consequence reports
- Compact `World.futures()` batches with deterministic CPU collision, distance, and
  AABB visibility predicates, filtering, ranking, and lazy materialization
- `World.explore()` for seeded, exact constraint search with structured scores,
  deltas, constraints, evidence, and selected future materialization
- Optional Warp CUDA batch transforms, collision, distance, and centre-ray AABB
  visibility, always checked against NumPy CPU oracles on CUDA-capable test hosts
- `RealityAgent` typed inspect/measure/edit/create-box orchestration with
  provider-neutral intent selection and transactional rollback
- MCP-shaped, tenant-scoped adapter over Reality Cloud; it delegates all
  geometry authority to the `reality` package through the existing API
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

## Runnable v0.1 demos

All demos construct a scene programmatically and write a single JSON document to stdout:

```bash
python examples/room_layout_optimization.py
python examples/game_level_clearance.py
python examples/mechanism_feasibility.py
python examples/robot_planning.py
```

The optional learned candidate prioritizer is intentionally isolated behind
`pip install "reality[learn]"`. It can only propose ordering; final candidates are
always checked using the exact Reality predicate/physics path. See
`tools/generate_explore_dataset.py` and `tools/train_explore_predictor.py`.

The current geometry layer intentionally uses world-axis-aligned bounding boxes. This is predictable, fast, and backend-neutral; it is not an exact triangle-mesh collision system.

Run the examples with `python examples/query_room.py`, `python examples/visibility.py`, and `python examples/relationships.py` after substituting your scene path and object names.

## Development

```bash
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
python -m mypy src/reality
pytest -q
```

See [PROJECT.md](PROJECT.md), [ARCHITECTURE.md](ARCHITECTURE.md), [API_DESIGN.md](API_DESIGN.md), [ROADMAP.md](ROADMAP.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

Licensed under [Apache-2.0](LICENSE).

## Articulation, physics, and batch branches

Joints are explicit. Reality samples the entire swept AABB path and refines the first
collision boundary; it does not infer hinges from arbitrary meshes.

```python
door = world.articulate(
    "Door", joint="revolute", pivot=(0, 0, 0), axis=(0, 0, 1), limits=(0, 110)
)
print(door.can_rotate(90).reason)
```

### Import explicit metadata

For a portable imported scene, place a `room.reality.json` file next to
`room.glb`/`room.gltf` (or use `extras.reality` in glTF/GLB). Metadata is explicit;
Reality does not infer a hinge, mass, or material behavior from object names.

```json
{
  "units": "m",
  "objects": {
    "Door": {
      "articulation": {
        "joint": "revolute",
        "axis": [0, 0, 1],
        "pivot": [0, 0, 0],
        "limits": [0, 110]
      },
      "physics": {"mass": 12, "dynamic": true, "friction": 0.5}
    }
  }
}
```

You may instead pass this mapping directly: `reality.load("room.glb", metadata=metadata)`.
An explicit `metadata=` argument overrides the embedded document, which overrides the
sidecar. `units` labels mesh coordinates; it never silently rescales geometry.

Install the replaceable MuJoCo CPU physics backend with `pip install -e ".[physics]"`:

```python
world.set_physics("Box", mass=2.0, dynamic=True)
result = world.push("Box", force=(20, 0, 0), duration=0.2)
print(result.body("Box").final_transform)
```

Physical defaults are explicit: static, 1 kg, local-bounds box collider, friction 0.5,
restitution 0, and center-of-mass offset `(0, 0, 0)`. Semantic materials are not
inferred. The CPU backend maps orientation and center-of-mass data into MuJoCo. It
caches compiled topology locally and reports setup/step timing in `result.evidence`.
MuJoCo contact compliance is not a literal restitution mapping, and simulation joints
are still outside the current scope.

`world.branches(10_000)` shares one immutable snapshot and stores only `N x 3`
translation arrays for changed objects. CPU collision-batch evaluation is implemented.
Warp is optional. Reality contains custom Warp kernels for batched transforms, AABB
overlap, AABB distance, and centre-ray AABB visibility, with CPU reference
implementations and synchronized validation tools. CUDA is never claimed active without
a usable driver, successful launches, and CPU/GPU parity evidence. GPU AABB visibility is
not mesh-exact visibility.

## Distribution status

The package metadata uses the distributable name `reality` and keeps the import name
`reality`. Before publishing, run `python -m build`, install the generated wheel in a
fresh virtual environment, then reserve/upload the name. A PyPI name probe is inherently
time-sensitive and is recorded in `RELEASE_RESULTS.json` rather than asserted in prose.
