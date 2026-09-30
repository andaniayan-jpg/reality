# Reality CPU Physics Audit

`REALITY_PHYSICS_STATUS=PASS`

- Generated: `2026-09-29T20:36:52.773848+00:00`
- Python: `3.11.9`
- Platform: `Windows-10-10.0.26200-SP0`
- Backend: `mujoco-cpu`
- MuJoCo available/version: `True` / `3.14.0`
- Physics-test return code: `0`
- Benchmark return code: `0`

## Evidence

- The public API delegates to the isolated PhysicsBackend protocol implementation.
- Tests cover gravity, ground contact, pushes, drop, stability, branch isolation, and simulation-observed consequences.
- The benchmark measures 100 dynamic bodies with fixed stepping and 1,000-body backend initialization.

The exact test and benchmark command outputs are saved in
`PHYSICS_RESULTS.json`; this report does not invent backend or timing results.

## Assumptions

- MuJoCo runs deterministic fixed-step Euler integration in the CPU reference backend.
- Current colliders are oriented boxes derived from local bounds and a z=0 plane is included.
- Compiled topology is cached per world backend, while every run creates fresh MuJoCo state.

## Known limitations

- Only box collision shapes are currently mapped to MuJoCo.
- Simulation joints, mesh colliders, and GPU physics are not implemented.
- MuJoCo contact compliance is not a direct mapping of Reality restitution.
- The 1,000-body benchmark records initialization only because stepped simulation exceeded the host budget.
