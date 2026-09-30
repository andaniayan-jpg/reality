"""Generate evidence-backed Reality v2 CAD ingestion audit artefacts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _run(*command: str) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-8000:],
        "stderr": completed.stderr[-8000:],
    }


def audit() -> dict[str, Any]:
    tests = _run(sys.executable, "-m", "pytest", "tests/test_file_models.py", "-q")
    benchmark = _run(sys.executable, "benchmarks/file_ingestion.py")
    cad_available = importlib.util.find_spec("cadquery") is not None
    try:
        benchmark_results: list[dict[str, Any]] | None = json.loads(benchmark["stdout"])
    except json.JSONDecodeError:
        benchmark_results = None

    # A functional CAD backend and passing evidence are necessary, but are not
    # sufficient for PASS: the current adapter intentionally has no XDE label
    # reader, so it cannot promise imported STEP assembly names/hierarchy.
    status = "PARTIAL"
    if tests["returncode"] != 0 or benchmark["returncode"] != 0:
        status = "FAIL"
    return {
        "status": status,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cad_backend": {"available": cad_available, "name": "CadQuery/OCP"},
        "mesh_backend": "Trimesh",
        "formats": ["OBJ", "STL", "PLY", "GLB", "GLTF", "STEP", "STP"],
        "tests": tests,
        "benchmark": {**benchmark, "results": benchmark_results},
        "limitations": [
            "CAD-to-mesh export is explicitly lossy and warns about topology/metadata loss.",
            "Model distance, clearance, containment, and intersections are deterministic AABB "
            "broad-phase results.",
            "STEP top-level B-rep solids are retained; full XDE assembly-label import is a "
            "future adapter capability.",
            "Hard parser cancellation requires a service worker process; parser_hook supports "
            "orchestration.",
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    tests = report["tests"]
    benchmark = report["benchmark"]
    benchmark_rows = benchmark["results"] or []
    timing_lines = [
        "| parts | faces/part | file bytes | open seconds | materialized relationships |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    timing_lines.extend(
        (
            "| {parts} | {faces_per_part} | {file_bytes} | {open_seconds:.6f} "
            "| {materialized_relationships} |"
        ).format(**row)
        for row in benchmark_rows
    )
    return (
        f"""# Reality CAD audit

`REALITY_CAD_STATUS={report["status"]}`

- Python: `{report["python"]}`
- Platform: `{report["platform"]}`
- Mesh backend: `{report["mesh_backend"]}`
- CAD backend: `{report["cad_backend"]["name"]}` available=`{report["cad_backend"]["available"]}`
- Structural ingestion tests: return code `{tests["returncode"]}`

## Supported formats

{", ".join(report["formats"])}

## Evidence

The audit executes `python -m pytest tests/test_file_models.py -q` against
programmatically created mesh and STEP fixtures. Full command output is stored
in `CAD_RESULTS.json`; it is not invented by this report.

## Ingestion benchmark

The audit also executes `python benchmarks/file_ingestion.py`. Timings include
file parsing, model construction, and eager graph materialization where bounded.
Scenes above 250 parts deliberately leave the graph dependency-ready but lazy,
so import does not trigger a quadratic all-pairs relationship calculation.

"""
        + "\n".join(timing_lines)
        + "\n"
        + "\n## Status rationale\n\n"
        + (
            "The executable ingestion evidence passed, but this is PARTIAL: the current "
            "STEP adapter preserves top-level B-rep solids without an XDE assembly-label "
            "reader, and service hard timeouts require worker-process orchestration.\n"
            if report["status"] == "PARTIAL"
            else "Executable evidence did not pass; see command outputs in `CAD_RESULTS.json`.\n"
        )
        + "\n## Known limitations\n\n"
        + "\n".join(f"- {item}" for item in report["limitations"])
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", type=Path, default=ROOT / "CAD_AUDIT.md")
    parser.add_argument("--json", type=Path, default=ROOT / "CAD_RESULTS.json")
    args = parser.parse_args()
    report = audit()
    args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(f"REALITY_CAD_STATUS={report['status']}")


if __name__ == "__main__":
    main()
