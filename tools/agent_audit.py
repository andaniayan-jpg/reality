"""Generate evidence for the provider-neutral Reality agent layer."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run() -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_agent.py", "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    status = "PASS" if completed.returncode == 0 else "FAIL"
    return {
        "status": status,
        "command": completed.args,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "evidence": [
            "Tests execute source-backed measurements, unit conversion, preview, and commit.",
            "Tests reject unknown names and invalid units before mutation.",
            "Tests assert the source model remains unchanged after preview/rejection.",
            "Numeric edit evidence is marked user_request; providers have no geometry authority.",
        ],
    }


def markdown(report: dict[str, object]) -> str:
    evidence = "\n".join(f"- {item}" for item in report["evidence"])
    return f"""# Reality agent audit

`REALITY_AGENT_STATUS={report["status"]}`

- Test return code: `{report["returncode"]}`
- Plan lifecycle: `plan → validate → preview → execute`

## Evidence

{evidence}

The complete test output is retained in `AGENT_RESULTS.json`.
"""


if __name__ == "__main__":
    report = run()
    (ROOT / "AGENT_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "AGENT_AUDIT.md").write_text(markdown(report), encoding="utf-8")
    print(f"REALITY_AGENT_STATUS={report['status']}")
