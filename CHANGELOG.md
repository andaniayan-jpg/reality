# Changelog

All notable changes are documented here. This project follows Semantic Versioning from
its first public release.

## 0.1.0 — Unreleased

- Deterministic world loading and AABB spatial predicates.
- Reality Graph, visibility evidence, snapshots, copy-on-write branches, and consequences.
- Navigation, articulation, metadata ingestion, and optional CPU MuJoCo simulation.
- Compact Futures plus `World.explore()` exact layout search.
- Optional Warp kernels with CPU-oracle validation and optional learned candidate prioritization.

## Release policy

Public APIs documented in `API_DESIGN.md` are additive within the 0.1 series. Geometry and
visibility semantics remain explicit: AABB predicates never silently become mesh-exact.
