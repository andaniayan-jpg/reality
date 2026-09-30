# Reality CAD audit

`REALITY_CAD_STATUS=PARTIAL`

- Python: `3.11.9`
- Platform: `Windows-10-10.0.26200-SP0`
- Mesh backend: `Trimesh`
- CAD backend: `CadQuery/OCP` available=`True`
- Structural ingestion tests: return code `0`

## Supported formats

OBJ, STL, PLY, GLB, GLTF, STEP, STP

## Evidence

The audit executes `python -m pytest tests/test_file_models.py -q` against
programmatically created mesh and STEP fixtures. Full command output is stored
in `CAD_RESULTS.json`; it is not invented by this report.

## Ingestion benchmark

The audit also executes `python benchmarks/file_ingestion.py`. Timings include
file parsing, model construction, and eager graph materialization where bounded.
Scenes above 250 parts deliberately leave the graph dependency-ready but lazy,
so import does not trigger a quadratic all-pairs relationship calculation.

| parts | faces/part | file bytes | open seconds | materialized relationships |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 20 | 1152 | 0.009720 | 0 |
| 100 | 20 | 24740 | 0.856718 | 0 |
| 1000 | 20 | 244108 | 2.385195 | 0 |
| 1 | 20480 | 369364 | 0.013143 | 0 |

## Status rationale

The executable ingestion evidence passed, but this is PARTIAL: the current STEP adapter preserves top-level B-rep solids without an XDE assembly-label reader, and service hard timeouts require worker-process orchestration.

## Known limitations

- CAD-to-mesh export is explicitly lossy and warns about topology/metadata loss.
- Model distance, clearance, containment, and intersections are deterministic AABB broad-phase results.
- STEP top-level B-rep solids are retained; full XDE assembly-label import is a future adapter capability.
- Hard parser cancellation requires a service worker process; parser_hook supports orchestration.
