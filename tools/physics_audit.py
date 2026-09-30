"""Generate evidence-backed audit files for Reality's CPU physics milestone."""

from __future__ import annotations

import importlib.util
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


def audit() -> dict[str, Any]:
    tests = _run(sys.executable, "-m", "pytest", "tests/test_physics.py", "-q")
    benchmark = _run(sys.executable, "benchmarks/physics_cpu.py")
    mujoco_available = importlib.util.find_spec("mujoco") is not None
    mujoco_version: str | None = None
    if mujoco_available:
        import mujoco

        mujoco_version = mujoco.__version__
    status = "PASS" if tests["returncode"] == 0 and benchmark["returncode"] == 0 else "FAIL"
    return {
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "backend": {
            "name": "mujoco-cpu",
            "available": mujoco_available,
            "version": mujoco_version,
        },
        "tests": tests,
        "benchmark": benchmark,
        "evidence": [
            "The public API delegates to the isolated PhysicsBackend protocol implementation.",
            "Tests cover gravity, ground contact, pushes, drop, stability, branch isolation, "
            "and simulation-observed consequences.",
            "The benchmark measures 100 dynamic bodies with fixed stepping and 1,000-body "
            "backend initialization.",
        ],
        "assumptions": [
            "MuJoCo runs deterministic fixed-step Euler integration in the CPU reference backend.",
            "Current colliders are oriented boxes derived from local bounds and a z=0 plane is "
            "included.",
            "Compiled topology is cached per world backend, while every run creates fresh MuJoCo "
            "state.",
        ],
        "limitations": [
            "Only box collision shapes are currently mapped to MuJoCo.",
            "Simulation joints, mesh colliders, and GPU physics are not implemented.",
            "MuJoCo contact compliance is not a direct mapping of Reality restitution.",
            "The 1,000-body benchmark records initialization only because stepped simulation "
            "exceeded the host budget.",
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    evidence = "\n".join(f"- {item}" for item in report["evidence"])
    assumptions = "\n".join(f"- {item}" for item in report["assumptions"])
    limitations = "\n".join(f"- {item}" for item in report["limitations"])
    return f"""# Reality CPU Physics Audit

`REALITY_PHYSICS_STATUS={report["status"]}`

- Generated: `{report["generated_at"]}`
- Python: `{report["python"]}`
- Platform: `{report["platform"]}`
- Backend: `{report["backend"]["name"]}`
- MuJoCo available/version: `{report["backend"]["available"]}` / `{report["backend"]["version"]}`
- Physics-test return code: `{report["tests"]["returncode"]}`
- Benchmark return code: `{report["benchmark"]["returncode"]}`

## Evidence

{evidence}

The exact test and benchmark command outputs are saved in
`PHYSICS_RESULTS.json`; this report does not invent backend or timing results.

## Assumptions

{assumptions}

## Known limitations

{limitations}
"""


def main() -> None:
    report = audit()
    (ROOT / "PHYSICS_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "PHYSICS_AUDIT.md").write_text(markdown(report), encoding="utf-8")
    print(f"REALITY_PHYSICS_STATUS={report['status']}")


if __name__ == "__main__":
    main()
