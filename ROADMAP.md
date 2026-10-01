# Roadmap

## 0.1 — foundation and graph

- Typed core data model and deterministic AABB spatial queries
- Trimesh adapters for GLB, glTF, and OBJ
- Tests, linting, editable installation, and CI
- Dependency-aware relationship graph and deterministic AABB visibility

## 0.2 — branchable worlds and consequences (current)

- Immutable, cached world snapshots
- Copy-on-write world branches with shared geometry and graph edges
- Structured move, rotate, and scale changes
- Dependency-frontier recomputation with instrumentation
- Direct and downstream consequence reports with JSON serialization
- Sibling-branch comparison

## 0.3 — agents and CPU navigation (current)

- First-class dimensioned agents
- Query-local radius-aware occupancy grids and deterministic A*
- Structured paths, reachability, passage, and clearance evidence
- Lazy Reality Graph navigation relationships
- Branch invalidation and downstream navigation consequences
- Standalone SVG navigation diagnostics

## Remaining next milestones

1. Capability interfaces and optional exact mesh-query backends.
2. Richer import diagnostics and unit conversion policy (metadata units are now read,
   but never implicitly converted).
3. Explicit physical affordance and visibility capabilities.
4. Simulated joints, additional collision shapes, and calibrated material behavior.

Each milestone must preserve the baseline API and document its numerical semantics.

## 0.4–0.6 — articulation, CPU physics, and batching (current)

- Explicit revolute/prismatic articulation and swept-AABB analysis
- Portable glTF/GLB/sidecar articulation and physics metadata ingestion
- Replaceable backend protocol and cached MuJoCo CPU reference simulation
- Orientation and center-of-mass mapping, observed-run contacts, and atomic
  multi-body graph refresh after simulation
- Compact CPU batched branch collision evaluation
- Two custom NVIDIA Warp kernels with CPU oracles and synchronized timing harnesses
- CUDA correctness and scale validation notebook/audit; final GPU validation remains
  blocked by unavailable CUDA hardware on the development machine

## 0.7 — parallel futures and consequence search (implemented for 0.1)

- Shared-snapshot `World.futures()` batches with copy-on-write candidate materialization
- Deterministic CPU collision, AABB distance, and bounding-volume visibility evaluation
- Typed filtering constraints, weighted objectives, ranking, and selected-future consequences
- Custom Warp AABB distance kernel with a NumPy oracle and CUDA parity test
- Reproducible 100–1,000,000 candidate exact CPU scaling audit
- `World.explore()` seeded constraint/objective search plus machine-readable demos
- Warp centre-ray AABB visibility with a CPU oracle and CUDA parity coverage

The next performance step is to retain immutable bounds and broad-phase data on the GPU
across independent evaluations, then add GPU filtering/ranking reductions. Exact triangle
visibility, batched rotations/scales, and GPU graph updates remain deliberately out of
scope until the CPU semantics are extended and benchmarked.

## Performance path

The current graph build compares all object pairs and evaluates several AABB predicates per pair: it is intentionally simple and O(n²). The included `benchmarks/graph_200_objects.py` provides a repeatable baseline. Object movement already refreshes only incident edges, but it still compares the changed object against every other object. `benchmarks/branching_1000_objects.py` measures persistent branch creation, memory, incremental recomputation, consequence calculation, and a conservative naive deep-copy comparison.

Before expanding GPU coverage, a CPU broad-phase spatial index should reduce candidate
pairs and candidate occluders. The current optional GPU kernels are most appropriate for
large batched transforms and AABB overlap tests; thousands of ray/AABB or ray/mesh
intersections remain future candidates. GPU behavior must remain an explicit capability
with results compatible with the documented deterministic baseline.

Navigation currently scans every object to construct each query-local grid and rasterizes qualifying AABBs cell by cell. Large scenes will first benefit from CPU spatial indexing, shared/tiled grid caches, and more precise invalidation. Later GPU candidates are batched obstacle projection, occupancy/voxel rasterization, clearance fields, and many simultaneous path queries. A GPU backend must preserve the CPU semantics and evidence contract.

## 0.3 — physical-AI integration layer (in progress)

- Capability-checked integration registry, strict `reality-scene/v1`
  interchange adapter, and validated MuJoCo MJCF primitive-geometry bridge are
  implemented.
- Blender, game-engine, robotics, and live simulation adapters are not yet
  claimed: each requires its native runtime and an end-to-end validation gate.
- The complete contract and acceptance gates are in [V3.md](V3.md); the future
  shared-platform design begins in [V4.md](V4.md).
