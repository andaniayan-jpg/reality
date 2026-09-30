"""Generate evidence-backed audit files for the hosted Reality API."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run() -> dict[str, object]:
    environment = {**os.environ, "PYTHONPATH": f"{ROOT / 'apps' / 'api'};{ROOT / 'src'}"}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "apps/api/tests", "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    # Local evidence proves the API semantics. A production PASS additionally
    # requires exercising the supplied PostgreSQL/S3 and browser deployment
    # paths against real services, which this workstation has not done.
    status = "PARTIAL" if completed.returncode == 0 else "FAIL"
    return {
        "status": status,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "command": completed.args,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12_000:],
        "stderr": completed.stderr[-12_000:],
        "evidence": [
            "Integration tests create two accounts and assert cross-tenant file lookup "
            "returns 404.",
            "Tests upload OBJ, GLB, and optional installed-CAD STEP assets through FastAPI.",
            "Tests validate API-key revocation and database-backed per-key rate limiting.",
        ],
        "limitations": [
            "PostgreSQL and S3-compatible storage adapters are configured but were not "
            "integration-tested against live services in this local audit.",
            "The responsive WebGL dashboard was not exercised in a real browser in this audit.",
        ],
    }


def markdown(report: dict[str, object]) -> str:
    evidence = "\n".join(f"- {item}" for item in report["evidence"])
    limitations = "\n".join(f"- {item}" for item in report["limitations"])
    return f"""# Reality Cloud API audit

`REALITY_API_STATUS={report["status"]}`

- Python: `{report["python"]}`
- Platform: `{report["platform"]}`
- Integration-test return code: `{report["returncode"]}`

## Evidence

{evidence}

The exact executed command output is retained in `API_RESULTS.json`; this report
does not fabricate backend, security, or geometry results.

## Status rationale

{limitations}
"""


if __name__ == "__main__":
    report = run()
    (ROOT / "API_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "API_AUDIT.md").write_text(markdown(report), encoding="utf-8")
    print(f"REALITY_API_STATUS={report['status']}")
