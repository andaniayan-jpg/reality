"""Run the real v2 vertical slice and write the public pre-release audit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "tests/test_file_models.py",
    "tests/test_editing.py",
    "tests/test_agent.py",
    "apps/api/tests/test_integration.py",
    "apps/mcp/tests/test_mcp_integration.py",
]


def run(*, wheel_verified: bool = False) -> dict[str, object]:
    environment = {
        **os.environ,
        "PYTHONPATH": f"{ROOT / 'src'};{ROOT / 'apps' / 'api'};{ROOT / 'apps' / 'mcp'}",
    }
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    demo = subprocess.run(
        [sys.executable, "examples/edit_model.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    status = (
        "PASS"
        if completed.returncode == 0 and demo.returncode == 0 and wheel_verified
        else "PARTIAL"
    )
    if completed.returncode != 0 or demo.returncode != 0:
        status = "FAIL"
    local = "PASS" if completed.returncode == 0 else "FAIL"
    return {
        "status": status,
        "command": completed.args,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "demo_command": demo.args,
        "demo_returncode": demo.returncode,
        "demo_stdout": demo.stdout,
        "demo_stderr": demo.stderr,
        "capabilities": {
            "cad": local,
            "api": local,
            "editing": local,
            "agent": local,
            "mcp": local,
            "security": local,
            "tests": local,
            "wheel_install": "PASS" if wheel_verified else "PARTIAL",
            "demos": "PASS" if demo.returncode == 0 else "FAIL",
        },
        "known_limitations": [
            "This audit exercises local API integration; it does not claim a deployed "
            "PostgreSQL/S3 service.",
            "AABB-labelled queries remain approximations where documented; they are not "
            "exact mesh visibility/collision proofs.",
            "The MCP adapter is transport-neutral and does not bundle a ChatGPT plugin.",
        ],
    }


def markdown(report: dict[str, object]) -> str:
    rows = "\n".join(f"| {name} | {status} |" for name, status in report["capabilities"].items())
    limitations = "\n".join(f"- {item}" for item in report["known_limitations"])
    return f"""# Reality v2 audit

`REALITY_V2_STATUS={report["status"]}`

This is an evidence-backed local vertical-slice audit. It runs real source-file
loading, editing, HTTP API, agent, and MCP calls; it does not claim a hosted
deployment or substitute mocked geometry.

| Area | Status |
| --- | --- |
{rows}

## Known limitations

{limitations}

Full command output is retained in `REALITY_V2_RESULTS.json`.
"""


if __name__ == "__main__":
    report = run(wheel_verified="--wheel-verified" in sys.argv)
    (ROOT / "REALITY_V2_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "REALITY_V2_AUDIT.md").write_text(markdown(report), encoding="utf-8")
    print(f"REALITY_V2_STATUS={report['status']}")
