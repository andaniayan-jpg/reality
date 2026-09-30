"""Generate reproducible evidence for the navigation and articulation milestones."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _run(*command: str) -> dict[str, Any]:
    environment = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'};{ROOT / 'apps' / 'api'}"}
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12_000:],
        "stderr": completed.stderr[-12_000:],
    }


def report() -> dict[str, Any]:
    navigation_tests = _run(sys.executable, "-m", "pytest", "tests/test_navigation.py", "-q")
    articulation_tests = _run(sys.executable, "-m", "pytest", "tests/test_articulation.py", "-q")
    navigation_benchmark = _run(sys.executable, "benchmarks/navigation_scaling.py")
    articulation_benchmark = _run(sys.executable, "benchmarks/articulation.py")
    navigation_status = (
        "PASS"
        if all(item["returncode"] == 0 for item in (navigation_tests, navigation_benchmark))
        else "FAIL"
    )
    articulation_status = (
        "PASS"
        if all(item["returncode"] == 0 for item in (articulation_tests, articulation_benchmark))
        else "FAIL"
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "navigation": {
            "status": navigation_status,
            "tests": navigation_tests,
            "benchmark": navigation_benchmark,
            "assumptions": [
                "Navigation is deterministic 2D 8-connected A* over a query-local XY occupancy "
                "grid.",
                "World-space AABBs are inflated by agent radius; Z is used for obstacle height "
                "filtering.",
                "Navigation grids are cached lazily and invalidated after world changes.",
            ],
        },
        "articulation": {
            "status": articulation_status,
            "tests": articulation_tests,
            "benchmark": articulation_benchmark,
            "assumptions": [
                "Revolute and prismatic joints are explicit metadata, never inferred from "
                "arbitrary geometry.",
                "Motion checks sample swept world AABBs at 1 degree or 0.01 m by default.",
                "The first detected collision boundary is refined to 0.01 degree or 0.0001 m.",
            ],
        },
        "limitations": [
            "Navigation has no terrain slope evaluation or global spatial index.",
            "AABB navigation and swept AABB articulation are conservative approximations, not "
            "mesh-exact collision.",
            "Articulation supports explicit revolute/prismatic constraints only; no automatic "
            "hinge inference or simulated joints.",
        ],
    }


def markdown(data: dict[str, Any], category: str) -> str:
    section = data[category]
    title = "Reality Navigation Audit" if category == "navigation" else "Reality Articulation Audit"
    status_name = (
        "REALITY_NAVIGATION_STATUS" if category == "navigation" else "REALITY_ARTICULATION_STATUS"
    )
    assumptions = "\n".join(f"- {item}" for item in section["assumptions"])
    limitations = "\n".join(f"- {item}" for item in data["limitations"])
    return f"""# {title}

`{status_name}={section["status"]}`

- Generated: `{data["generated_at"]}`
- Python: `{data["python"]}`
- Platform: `{data["platform"]}`
- Test return code: `{section["tests"]["returncode"]}`
- Benchmark return code: `{section["benchmark"]["returncode"]}`

## Evidence

The exact command output and benchmark output are retained in
`NAVIGATION_ARTICULATION_RESULTS.json`; no timings are manually inserted here.

## Assumptions

{assumptions}

## Known limitations

{limitations}
"""


def main() -> None:
    data = report()
    (ROOT / "NAVIGATION_ARTICULATION_RESULTS.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    (ROOT / "NAVIGATION_AUDIT.md").write_text(markdown(data, "navigation"), encoding="utf-8")
    (ROOT / "ARTICULATION_AUDIT.md").write_text(markdown(data, "articulation"), encoding="utf-8")
    print(f"REALITY_NAVIGATION_STATUS={data['navigation']['status']}")
    print(f"REALITY_ARTICULATION_STATUS={data['articulation']['status']}")


if __name__ == "__main__":
    main()
