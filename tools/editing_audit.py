"""Generate evidence-backed audit artefacts for Reality's editing layer."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def run() -> dict[str, Any]:
    environment = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'};{ROOT / 'apps' / 'api'}"}
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_editing.py",
        "apps/api/tests",
        "-q",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    # Passing programmatic tests demonstrate the semantics, but not a complete
    # interactive browser workflow or every OpenCascade edge case.
    status = "PARTIAL" if completed.returncode == 0 else "FAIL"
    return {
        "status": status,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cad_backend_available": importlib.util.find_spec("cadquery") is not None,
        "tests": {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12_000:],
            "stderr": completed.stderr[-12_000:],
        },
        "evidence": [
            "Mesh edits use Trimesh and preserve the original imported model.",
            "STEP hole and native OpenCascade offset edits retain B-rep output and are reopened "
            "from STEP.",
            "HTTP editing creates a separate tenant-scoped model record through the Reality "
            "package.",
            "Transactions record ordered before/after measurement evidence and support undo/redo.",
        ],
        "limitations": [
            "OpenCascade can reject offsets, blends, shells, and other features for invalid or "
            "difficult input geometry.",
            "Validation reports backend validity and mesh consistency; it is not a universal "
            "self-intersection proof.",
            "The dashboard before/after preview is implemented, but this local audit does not "
            "exercise it in a real browser.",
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    tests = report["tests"]
    evidence = "\n".join(f"- {item}" for item in report["evidence"])
    limitations = "\n".join(f"- {item}" for item in report["limitations"])
    rationale = (
        "The executable editing and API evidence passed, but this remains PARTIAL because browser "
        "interaction was not exercised and CAD kernel feature success is input dependent."
        if report["status"] == "PARTIAL"
        else "The executable evidence failed; see `EDITING_RESULTS.json`."
    )
    return f"""# Reality editing audit

`REALITY_EDITING_STATUS={report["status"]}`

- Python: `{report["python"]}`
- Platform: `{report["platform"]}`
- CadQuery/OCP available: `{report["cad_backend_available"]}`
- Editing/API test return code: `{tests["returncode"]}`

## Evidence

{evidence}

The exact command output is saved in `EDITING_RESULTS.json`; hardware, kernel,
and geometry results are not manually invented in this audit.

## Status rationale

{rationale}

## Known limitations

{limitations}
"""


def main() -> None:
    report = run()
    (ROOT / "EDITING_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "EDITING_AUDIT.md").write_text(markdown(report), encoding="utf-8")
    print(f"REALITY_EDITING_STATUS={report['status']}")


if __name__ == "__main__":
    main()
