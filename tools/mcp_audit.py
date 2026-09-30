"""Generate evidence for the API-backed Reality MCP adapter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run() -> dict[str, object]:
    environment = {
        **os.environ,
        "PYTHONPATH": f"{ROOT / 'src'};{ROOT / 'apps' / 'api'};{ROOT / 'apps' / 'mcp'}",
    }
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "apps/mcp/tests/test_mcp_integration.py", "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    status = "PASS" if completed.returncode == 0 else "FAIL"
    return {
        "status": status,
        "command": completed.args,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "evidence": [
            "MCP tests upload and inspect actual GLB/OBJ bytes through FastAPI.",
            "MCP measure, topology, preview, conversion, edit, versions, and undo call /v1.",
            "Destructive apply/undo require explicit confirmation.",
            "A second account receives a real API 404 for another tenant's model.",
        ],
        "limitations": [
            "The adapter is transport-neutral; a host chooses the MCP stdio/HTTP SDK integration.",
            "No hosted production endpoint is claimed by this local integration audit.",
        ],
    }


def markdown(report: dict[str, object]) -> str:
    evidence = "\n".join(f"- {item}" for item in report["evidence"])
    limitations = "\n".join(f"- {item}" for item in report["limitations"])
    return f"""# Reality MCP audit

`REALITY_MCP_STATUS={report["status"]}`

- Test return code: `{report["returncode"]}`

## Evidence

{evidence}

## Boundaries

{limitations}

The full local end-to-end evidence is retained in `MCP_RESULTS.json`.
"""


if __name__ == "__main__":
    report = run()
    (ROOT / "MCP_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "MCP_AUDIT.md").write_text(markdown(report), encoding="utf-8")
    print(f"REALITY_MCP_STATUS={report['status']}")
