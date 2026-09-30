# Reality Navigation Audit

`REALITY_NAVIGATION_STATUS=PASS`

- Generated: `2026-09-29T20:32:19.723045+00:00`
- Python: `3.11.9`
- Platform: `Windows-10-10.0.26200-SP0`
- Test return code: `0`
- Benchmark return code: `0`

## Evidence

The exact command output and benchmark output are retained in
`NAVIGATION_ARTICULATION_RESULTS.json`; no timings are manually inserted here.

## Assumptions

- Navigation is deterministic 2D 8-connected A* over a query-local XY occupancy grid.
- World-space AABBs are inflated by agent radius; Z is used for obstacle height filtering.
- Navigation grids are cached lazily and invalidated after world changes.

## Known limitations

- Navigation has no terrain slope evaluation or global spatial index.
- AABB navigation and swept AABB articulation are conservative approximations, not mesh-exact collision.
- Articulation supports explicit revolute/prismatic constraints only; no automatic hinge inference or simulated joints.
