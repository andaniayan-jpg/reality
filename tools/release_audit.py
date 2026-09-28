"""Generate reproducible public-release evidence without claiming unavailable hardware."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from futures_audit import gpu_validation

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str, allow_index: bool = False) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if allow_index:
        # Some development environments intentionally set PIP_NO_INDEX. A clean-install
        # audit must instead exercise the configured package index and record its result.
        environment["PIP_NO_INDEX"] = "0"
    return subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False, env=environment
    )


def summary(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    output = f"{completed.stdout}\n{completed.stderr}"
    return {"returncode": completed.returncode, "output": output[-4_000:]}


def test_summary() -> dict[str, Any]:
    completed = run(sys.executable, "-m", "pytest", "-q")
    output = f"{completed.stdout}\n{completed.stderr}"
    return {
        **summary(completed),
        "passed": _count(output, "passed"),
        "failed": _count(output, "failed"),
        "skipped": _count(output, "skipped"),
    }


def _count(output: str, label: str) -> int:
    match = re.search(rf"(\d+) {label}", output)
    return int(match.group(1)) if match else 0


def demos() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in (
        "room_layout_optimization.py",
        "game_level_clearance.py",
        "mechanism_feasibility.py",
        "robot_planning.py",
    ):
        completed = run(sys.executable, str(Path("examples") / name))
        entry = summary(completed)
        try:
            decoder = json.JSONDecoder()
            _, end = decoder.raw_decode(completed.stdout.lstrip())
            # Native optional dependencies occasionally write a diagnostic after a
            # completed program. The first JSON document is the demo contract.
            entry["trailing_output"] = completed.stdout.lstrip()[end:].strip()
            entry["machine_readable"] = True
        except json.JSONDecodeError:
            entry["machine_readable"] = False
        result[name] = entry
    return result


def install_check() -> dict[str, Any]:
    build = run(sys.executable, "-m", "build", allow_index=True)
    if build.returncode != 0:
        return {"build": summary(build), "install": None}
    wheels = sorted(
        (ROOT / "dist").glob("reality-*.whl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    wheel = wheels[0] if wheels else None
    with tempfile.TemporaryDirectory(prefix="reality-release-") as directory:
        environment = Path(directory) / "venv"
        create = run(sys.executable, "-m", "venv", str(environment))
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = (
            subprocess.run(
                [str(python), "-m", "pip", "install", str(wheel)],
                capture_output=True,
                text=True,
                env={**os.environ, "PIP_NO_INDEX": "0"},
            )
            if create.returncode == 0 and wheel is not None
            else None
        )
        import_check = (
            subprocess.run(
                [str(python), "-c", "import reality; print(reality.__name__)"],
                capture_output=True,
                text=True,
            )
            if install is not None and install.returncode == 0
            else None
        )
    return {
        "build": summary(build),
        "venv": summary(create),
        "wheel": str(wheel) if wheel else None,
        "install": summary(install) if install is not None else None,
        "import": summary(import_check) if import_check is not None else None,
    }


def audit() -> dict[str, Any]:
    tests = test_summary()
    benchmark = run(sys.executable, "benchmarks/explore_scaling.py")
    try:
        benchmark_rows = json.loads(benchmark.stdout)
    except json.JSONDecodeError:
        benchmark_rows = []
    release_demos = demos()
    installation = install_check()
    gpu = gpu_validation()
    name_check = run(sys.executable, "-m", "pip", "index", "versions", "reality", allow_index=True)
    all_demos_pass = all(
        item["returncode"] == 0 and item["machine_readable"] for item in release_demos.values()
    )
    installed = bool(installation.get("import") and installation["import"]["returncode"] == 0)
    core_pass = tests["returncode"] == 0 and all_demos_pass and installed and bool(benchmark_rows)
    gpu_pass = gpu["cpu_gpu_parity"] == "PASS"
    # A release host without a real CUDA validation is useful CPU evidence, but it
    # cannot prove the optional GPU implementation. Keep the combined release audit
    # partial until the corresponding Futures audit runs successfully on NVIDIA CUDA.
    status = "PASS" if core_pass and gpu_pass else "PARTIAL"
    return {
        "release_status": status,
        "commit": run("git", "rev-parse", "HEAD").stdout.strip() or "unknown",
        "tests": tests,
        "supported_capabilities": [
            "GLB/glTF/OBJ loading",
            "deterministic AABB predicates and Reality Graph",
            "visibility evidence",
            "snapshots, branches, consequences, and compact Futures",
            "exact World.explore optimization",
            "navigation, articulation, metadata, and optional MuJoCo physics",
            "optional Warp collision, distance, and AABB visibility kernels",
        ],
        "gpu_validation": gpu,
        "optimization_benchmark": benchmark_rows,
        "demos": release_demos,
        "installation": installation,
        "pypi_name_check": summary(name_check),
        "known_limitations": [
            "All spatial predicates and batched visibility use AABBs, not exact triangle meshes.",
            "Batched rotation and scale storage exists but exact batched predicate evaluation "
            "is pending.",
            "The experimental predictor only prioritizes; every selected candidate requires "
            "exact validation.",
        ],
        "reproduction": [
            "python -m pip install -e '.[dev,physics,gpu]'",
            "python -m ruff format --check . && python -m ruff check .",
            "python -m mypy src && python -m pytest -q",
            "python benchmarks/explore_scaling.py",
            "python tools/futures_audit.py --full --output FUTURES_AUDIT.md",
            "python tools/release_audit.py --output RELEASE_AUDIT.md",
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    benchmark = report["optimization_benchmark"]
    rows = "\n".join(
        "| {possibilities} | {generation_seconds:.6f} | {kernel_seconds:.6f} | "
        "{filtering_ranking_seconds:.6f} | {end_to_end_seconds:.6f} | {peak_traced_bytes} |".format(
            **row
        )
        for row in benchmark
    )
    gpu = report["gpu_validation"]
    tests = report["tests"]
    demos_pass = all(
        item["machine_readable"] and item["returncode"] == 0 for item in report["demos"].values()
    )
    installed = bool(
        report["installation"].get("import") and report["installation"]["import"]["returncode"] == 0
    )
    return (
        f"""# Reality v0.1 release audit

REALITY_RELEASE_STATUS={report["release_status"]}

## Evidence

- Commit: `{report["commit"]}`
- Tests: `{tests["passed"]} passed`, `{tests["skipped"]} skipped`, `{tests["failed"]} failed`
- CUDA available: `{gpu["cuda_available"]}`
- CUDA device: `{gpu["device"] or "unavailable"}`
- Custom Warp kernels: `{", ".join(gpu["custom_warp_kernels_tested"]) or "none"}`
- GPU parity: `{gpu["cpu_gpu_parity"]}`
- GPU pytest: `{gpu["gpu_pass_count"]}/{gpu["gpu_test_count"]}`
- GPU execution used: `{gpu["gpu_execution_used"]}`

## Supported capabilities

"""
        + "\n".join(f"- {capability}" for capability in report["supported_capabilities"])
        + f"""

## Optimization benchmark

| futures | generation s | predicates s | filter/rank s | end-to-end s | peak bytes |
|---:|---:|---:|---:|---:|---:|
{rows}

The benchmark uses exact CPU AABB predicates and records `upload_seconds` as `null` because no
GPU transfer occurs on CPU. CUDA records are included only when a real CUDA validation succeeds.

## Demos

Each program completed with machine-readable JSON: `{demos_pass}`.

## Install verification

Clean wheel installation/import success: `{installed}`.

PyPI name probe is included in `RELEASE_RESULTS.json`; availability can change between probe and
upload, so the final publish workflow must reserve the name before release.

## Correctness and reproduction

The test suite, all JSON demos, the exact optimization benchmark, and a wheel installed
into a temporary clean virtual environment were executed for this report. Reproduce with:

"""
        + "\n".join(f"- `{command}`" for command in report["reproduction"])
        + """

## Known limitations

"""
        + "\n".join(f"- {item}" for item in report["known_limitations"])
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("RELEASE_AUDIT.md"))
    args = parser.parse_args()
    report = audit()
    args.output.write_text(markdown(report), encoding="utf-8")
    Path("RELEASE_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(markdown(report))


if __name__ == "__main__":
    main()
