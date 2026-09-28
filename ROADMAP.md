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

## Next milestones (not implemented)

1. Capability interfaces and optional exact mesh-query backends.
2. Scene metadata, units, and richer import diagnostics.
3. Explicit physical affordance and visibility capabilities.
4. Optional simulation, navigation, and counterfactual world APIs.

Each milestone must preserve the baseline API and document its numerical semantics.

## 0.4–0.6 — articulation, CPU physics, and batching (current)

- Explicit revolute/prismatic articulation and swept-AABB analysis
- Replaceable backend protocol and MuJoCo CPU reference simulation
- Compact CPU batched branch collision evaluation
- Two custom NVIDIA Warp kernels with CPU oracles and synchronized timing harnesses
- CUDA correctness and scale validation notebook/audit; final GPU validation remains
  blocked by unavailable CUDA hardware on the development machine

## Performance path

The current graph build compares all object pairs and evaluates several AABB predicates per pair: it is intentionally simple and O(n²). The included `benchmarks/graph_200_objects.py` provides a repeatable baseline. Object movement already refreshes only incident edges, but it still compares the changed object against every other object. `benchmarks/branching_1000_objects.py` measures persistent branch creation, memory, incremental recomputation, consequence calculation, and a conservative naive deep-copy comparison.

Before expanding GPU coverage, a CPU broad-phase spatial index should reduce candidate
pairs and candidate occluders. The current optional GPU kernels are most appropriate for
large batched transforms and AABB overlap tests; thousands of ray/AABB or ray/mesh
intersections remain future candidates. GPU behavior must remain an explicit capability
with results compatible with the documented deterministic baseline.

Navigation currently scans every object to construct each query-local grid and rasterizes qualifying AABBs cell by cell. Large scenes will first benefit from CPU spatial indexing, shared/tiled grid caches, and more precise invalidation. Later GPU candidates are batched obstacle projection, occupancy/voxel rasterization, clearance fields, and many simultaneous path queries. A GPU backend must preserve the CPU semantics and evidence contract.
