# Changelog

All notable changes are documented here. This project follows Semantic Versioning from
its first public release.

## 0.2.0 — 2026-09-30

- Added `reality.open()` and backend-neutral `RealityModel`, `ModelPart`, and assembly APIs.
- Added OBJ, STL, PLY, GLB, glTF, STEP, and STP ingestion with source-unit reporting.
- Added optional CadQuery/OCP B-rep preservation, topology inspection, guarded exports,
  source-file validation, deterministic model inspection, and transactional CAD/mesh editing.
- Added copy-on-write editing sessions, typed history/validation, and asynchronous hosted edit jobs.
- Documented the FastAPI-hosted Reality Cloud service, storage/authentication boundaries, and
  official Python and server-side JavaScript clients.
- Added reproducible CAD, editing, navigation, articulation, and CPU-physics audits.
- Added provider-neutral `RealityAgent` orchestration with typed inspection,
  measurement, creation, transactional editing, preview, and rollback evidence.
- Added an API-backed MCP adapter, confirmation-gated versioned edit/undo tools,
  topology endpoint, and tenant-isolation integration coverage.

### Known v0.2 limitations

- CAD-to-mesh exports are explicitly lossy; mesh-to-STEP export is rejected.
- Model inspection, navigation, and swept motion use documented AABB approximations where an
  exact mesh/CAD kernel is unavailable.
- STEP hierarchy import retains top-level solids but does not yet implement an XDE label reader.
- CPU physics currently maps explicit box colliders to MuJoCo; mesh colliders and simulated
  joints are not included.

## 0.1.0

- Deterministic world loading and AABB spatial predicates.
- Reality Graph, visibility evidence, snapshots, copy-on-write branches, and consequences.
- Navigation, articulation, metadata ingestion, and optional CPU MuJoCo simulation.
- Compact Futures plus `World.explore()` exact layout search.
- Optional Warp kernels with CPU-oracle validation and optional learned candidate prioritization.

## Release policy

Public APIs documented in `API_DESIGN.md` are additive within the 0.2 series. Geometry and
visibility semantics remain explicit: AABB predicates never silently become mesh-exact.
