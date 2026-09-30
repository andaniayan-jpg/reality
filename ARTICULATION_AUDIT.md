# Reality Articulation Audit

`REALITY_ARTICULATION_STATUS=PASS`

- Generated: `2026-09-29T20:32:19.723045+00:00`
- Python: `3.11.9`
- Platform: `Windows-10-10.0.26200-SP0`
- Test return code: `0`
- Benchmark return code: `0`

## Evidence

The exact command output and benchmark output are retained in
`NAVIGATION_ARTICULATION_RESULTS.json`; no timings are manually inserted here.

## Assumptions

- Revolute and prismatic joints are explicit metadata, never inferred from arbitrary geometry.
- Motion checks sample swept world AABBs at 1 degree or 0.01 m by default.
- The first detected collision boundary is refined to 0.01 degree or 0.0001 m.

## Known limitations

- Navigation has no terrain slope evaluation or global spatial index.
- AABB navigation and swept AABB articulation are conservative approximations, not mesh-exact collision.
- Articulation supports explicit revolute/prismatic constraints only; no automatic hinge inference or simulated joints.
