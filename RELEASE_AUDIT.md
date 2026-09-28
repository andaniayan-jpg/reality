# Reality v0.1 release audit

REALITY_RELEASE_STATUS=PARTIAL

## Evidence

- Commit: `e15e0dc390792784295ce0de8fc89c766119f1fa`
- Tests: `77 passed`, `5 skipped`, `0 failed`
- CUDA available: `False`
- CUDA device: `unavailable`
- Custom Warp kernels: `none`
- GPU parity: `NOT_RUN`
- GPU pytest: `0/0`
- GPU execution used: `False`

## Supported capabilities

- GLB/glTF/OBJ loading
- deterministic AABB predicates and Reality Graph
- visibility evidence
- snapshots, branches, consequences, and compact Futures
- exact World.explore optimization
- navigation, articulation, metadata, and optional MuJoCo physics
- optional Warp collision, distance, and AABB visibility kernels

## Optimization benchmark

| futures | generation s | predicates s | filter/rank s | end-to-end s | peak bytes |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.003115 | 0.000410 | 0.000526 | 0.004868 | 40222 |
| 1000 | 0.000339 | 0.000300 | 0.000249 | 0.001682 | 356672 |
| 10000 | 0.000427 | 0.001336 | 0.000847 | 0.003851 | 2948664 |
| 100000 | 0.003085 | 0.010839 | 0.006711 | 0.033806 | 28868656 |
| 1000000 | 0.029441 | 0.144119 | 0.076214 | 0.396807 | 288068648 |

The benchmark uses exact CPU AABB predicates and records `upload_seconds` as `null` because no
GPU transfer occurs on CPU. CUDA records are included only when a real CUDA validation succeeds.

## Demos

Each program completed with machine-readable JSON: `True`.

## Install verification

Clean wheel installation/import success: `True`.

PyPI name probe is included in `RELEASE_RESULTS.json`; availability can change between probe and
upload, so the final publish workflow must reserve the name before release.

## Correctness and reproduction

The test suite, all JSON demos, the exact optimization benchmark, and a wheel installed
into a temporary clean virtual environment were executed for this report. Reproduce with:

- `python -m pip install -e '.[dev,physics,gpu]'`
- `python -m ruff format --check . && python -m ruff check .`
- `python -m mypy src && python -m pytest -q`
- `python benchmarks/explore_scaling.py`
- `python tools/futures_audit.py --full --output FUTURES_AUDIT.md`
- `python tools/release_audit.py --output RELEASE_AUDIT.md`

## Known limitations

- All spatial predicates and batched visibility use AABBs, not exact triangle meshes.
- Batched rotation and scale storage exists but exact batched predicate evaluation is pending.
- The experimental predictor only prioritizes; every selected candidate requires exact validation.
