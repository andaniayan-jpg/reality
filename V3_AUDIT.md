# Reality v3 audit

`V3_STATUS=PARTIAL`

This is a development audit, not a release certification. It reports only work
verified in this repository and on the local machine.

## Verified foundation

- `reality.integrations` provides an explicit, capability-checked adapter
  registry. Unregistered or unsupported integration operations fail with typed
  errors rather than silently falling back.
- `reality-scene/v1` is a strict JSON interchange for world object IDs, AABB
  bounds, transforms, units, and explicit rigid-body properties. It does not
  claim to preserve meshes, CAD solids, materials, animation, or physics.
- `MuJoCoSceneIntegration` was verified using **MuJoCo 3.14.0**. It compiles
  real MJCF, imports supported primitive bounds, exports an MJCF file that
  MuJoCo compiles, and exposes source joint/actuator/sensor declarations.
- Its local `rollout()` validates named controls against declared MuJoCo
  `ctrlrange` values, runs an isolated simulation, and returns body states and
  sensor readings. Its evidence explicitly records
  `hardware_commanded: false` and `source_modified: false`.

## Verification evidence

On 2026-10-01, `python -m pytest -q --junitxml=outputs/v3-pytest.xml`
produced 119 tests: 114 passed, 0 failures, 0 errors, and 5 expected CUDA skips
in 16.690 seconds. Ruff formatting and linting passed; strict mypy passed for
24 Reality source modules. `python examples/mujoco_rollout.py` produced a
nonzero real MuJoCo joint-position sensor sample after a validated local motor
control.

## Deliberate limitations

- The MuJoCo bridge represents supported primitive geometry as bounds. It does
  not preserve mesh/CAD geometry, material/contact configuration, kinematic
  trees, joint state, actuator dynamics, or sensor semantics in a `World`.
- The rollout is simulator-only. It is not robot hardware control or a safety
  certification.
- No Blender installation was available on the development machine, so no
  Blender add-on is implemented or claimed.
- No Unity, Unreal, ROS 2, Isaac, Gazebo, or hardware runtime has been
  validated. They remain v3 milestones, not existing features.
- Five existing CUDA tests were skipped because this machine has no NVIDIA CUDA
  driver/device. This is unrelated to the MuJoCo validation.

## V4 foundation

[V4.md](V4.md) defines the shared world-identity, provenance, collaboration,
digital-twin, and verified-planning contract. It is a documented foundation;
V4 is not an implemented release.
