"""Audit the parallel futures milestone and write reproducible evidence."""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

import reality
from reality._warp_ops import (
    evaluate_aabb_distances_cpu,
    evaluate_aabb_distances_warp,
    evaluate_aabb_intersections_cpu,
    evaluate_aabb_intersections_warp,
    evaluate_aabb_visibility_cpu,
    evaluate_aabb_visibility_warp,
    evaluate_branch_transforms_cpu,
    evaluate_branch_transforms_warp,
)
from reality.predicates import collision, distance, visibility


def make_scene(object_count: int = 1_000) -> reality.World:
    box = reality.Bounds((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))
    objects = [
        reality.WorldObject("Camera", box, reality.Transform(position=(-5.0, 0.0, 0.0))),
        reality.WorldObject("Target", box, reality.Transform(position=(5.0, 0.0, 0.0))),
        reality.WorldObject("Mover", box, reality.Transform(position=(0.0, 2.0, 0.0))),
    ]
    objects.extend(
        reality.WorldObject(
            f"Static-{index}", box, reality.Transform(position=(index % 50, index // 50, 0.0))
        )
        for index in range(object_count - len(objects))
    )
    return reality.World(objects)


def git_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def gpu_pytest_summary(cuda_available: bool) -> dict[str, Any]:
    """Collect pass/skip counts from the real GPU pytest module when runnable."""
    if not cuda_available:
        return {"status": "NOT_RUN", "count": 0, "passed": 0, "failed": 0, "skipped": 0}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_gpu.py", "-q"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    passed_match = re.search(r"(\d+) passed", output)
    failed_match = re.search(r"(\d+) failed", output)
    skipped_match = re.search(r"(\d+) skipped", output)
    if passed_match is None:
        return {
            "status": "ERROR",
            "count": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "error": output[-2_000:],
        }
    passed = int(passed_match.group(1))
    failed = int(failed_match.group(1)) if failed_match else 0
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    return {
        "status": "PASS" if completed.returncode == 0 and failed == 0 else "FAIL",
        "count": passed + failed + skipped,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }


def gpu_validation() -> dict[str, Any]:
    """Run real custom-kernel parity checks when a CUDA device is available."""
    cuda = reality.warp_status()
    device = next((item for item in cuda.devices if item.startswith("cuda")), None)
    kernels = (
        "branch_transforms",
        "aabb_intersections",
        "aabb_distances",
        "aabb_visibility",
    )
    result: dict[str, Any] = {
        "cuda_available": cuda.cuda_available,
        "device": device,
        "custom_warp_kernels_tested": list(kernels),
        "kernel_parity_count": len(kernels),
        "kernel_parity_pass_count": 0,
        "gpu_test_count": 0,
        "gpu_pass_count": 0,
        "cpu_gpu_parity": "NOT_RUN",
        "gpu_execution_used": False,
        "failures": [],
        "pytest": gpu_pytest_summary(cuda.cuda_available),
    }
    if not cuda.cuda_available or device is None:
        result["custom_warp_kernels_tested"] = []
        result["kernel_parity_count"] = 0
        result["gpu_test_count"] = 0
        result["cpu_gpu_parity"] = "NOT_RUN"
        return result

    generator = np.random.default_rng(20260929)
    base = generator.normal(size=(7, 3)).astype(np.float32)
    deltas = generator.normal(size=(13, 7, 3)).astype(np.float32)
    centers = generator.normal(size=(13, 7, 3)).astype(np.float32)
    extents = generator.uniform(0.05, 0.5, size=(7, 3)).astype(np.float32)
    pairs = np.asarray([(0, 1), (1, 2), (2, 6)], dtype=np.int32)
    minimum = centers[0] - extents
    maximum = centers[0] + extents
    pair = np.asarray((2, 6), dtype=np.int32)
    checks = (
        (
            "branch_transforms",
            lambda: np.allclose(
                evaluate_branch_transforms_warp(base, deltas, device=device),
                evaluate_branch_transforms_cpu(base, deltas),
                rtol=1e-5,
                atol=1e-5,
            ),
        ),
        (
            "aabb_intersections",
            lambda: np.array_equal(
                evaluate_aabb_intersections_warp(centers, extents, pairs, device=device),
                evaluate_aabb_intersections_cpu(centers, extents, pairs),
            ),
        ),
        (
            "aabb_distances",
            lambda: np.allclose(
                evaluate_aabb_distances_warp(minimum, maximum, deltas, pair, device=device),
                evaluate_aabb_distances_cpu(minimum, maximum, deltas, pair),
                rtol=1e-5,
                atol=1e-5,
            ),
        ),
        (
            "aabb_visibility",
            lambda: np.array_equal(
                evaluate_aabb_visibility_warp(
                    minimum, maximum, deltas, target=2, viewer=0, device=device
                ),
                evaluate_aabb_visibility_cpu(minimum, maximum, deltas, target=2, viewer=0),
            ),
        ),
    )
    for name, check in checks:
        try:
            passed = bool(check())
            result["gpu_execution_used"] = True
            if passed:
                result["kernel_parity_pass_count"] += 1
            else:
                result["failures"].append(f"{name}: CPU/GPU parity mismatch")
        except Exception as error:  # pragma: no cover - hardware/runtime dependent
            result["failures"].append(f"{name}: {error}")
    result["cpu_gpu_parity"] = (
        "PASS"
        if result["kernel_parity_pass_count"] == len(kernels)
        and not result["failures"]
        and result["pytest"]["status"] == "PASS"
        else "FAIL"
    )
    result["gpu_test_count"] = len(kernels) + result["pytest"]["count"]
    result["gpu_pass_count"] = result["kernel_parity_pass_count"] + result["pytest"]["passed"]
    if result["pytest"]["status"] == "ERROR":
        result["failures"].append("GPU pytest validation could not be parsed")
    return result


def audit(full: bool) -> dict[str, Any]:
    world = make_scene()
    futures = world.futures(10_000).randomize_position(
        "Mover", x=(-1.0, 1.0), y=(-1.0, 1.0), z=(0.0, 0.0), seed=20260928
    )
    started = time.perf_counter()
    evaluation = futures.evaluate(
        [
            collision("Mover", "Target"),
            distance("Mover", "Target"),
            visibility("Target", from_="Camera"),
        ]
    )
    evaluation_seconds = time.perf_counter() - started
    selected = evaluation.where(collision("Mover", "Target") == False)  # noqa: E712
    cuda = reality.warp_status()
    gpu = gpu_validation()
    validation_passed = gpu["cpu_gpu_parity"] == "PASS"
    if validation_passed:
        limitations = [
            "Visibility uses deterministic AABB ray tests, not exact triangle-mesh rays.",
            "Batched rotation and scale are stored but predicate evaluation is not "
            "implemented yet.",
        ]
    elif cuda.cuda_available:
        limitations = [
            "CUDA was available, but one or more custom-kernel parity checks failed.",
            "Visibility uses deterministic AABB ray tests, not exact triangle-mesh rays.",
            "Batched rotation and scale are stored but predicate evaluation is not "
            "implemented yet.",
        ]
    else:
        limitations = [
            f"CUDA validation could not be performed: {cuda.reason}",
            "Visibility uses deterministic AABB ray tests, not exact triangle-mesh rays.",
            "Batched rotation and scale are stored but predicate evaluation is not "
            "implemented yet.",
        ]
    report: dict[str, Any] = {
        "status": "PASS" if validation_passed else "PARTIAL",
        "revision": git_revision(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cuda": {
            "installed": cuda.installed,
            "version": cuda.version,
            "cuda_available": cuda.cuda_available,
            "devices": list(cuda.devices),
            "reason": cuda.reason,
        },
        "gpu_validation": gpu,
        "scene_objects": len(world.objects),
        "futures": len(futures),
        "delta_bytes": futures.delta_bytes,
        "logical_delta_bytes": len(futures) * 3 * 8,
        "evaluation_seconds": evaluation_seconds,
        "selected_without_collision": len(selected),
        "shared_snapshot": futures.shared_snapshot is world.snapshot(),
        "predicates": ["collision", "distance", "visibility"],
        "visibility_is_bounding_volume": True,
        "limitations": limitations,
        "gpu_acceleration_next": [
            "Keep AABB centers/extents resident on GPU across many candidate batches.",
            "Move visibility ray batches and broad-phase pair culling to Warp kernels.",
            "Add GPU reduction kernels for filtering and ranking to reduce host transfers.",
        ],
    }
    if full:
        report["scaling"] = []
        for count in (100, 1_000, 10_000, 50_000, 100_000):
            start = time.perf_counter()
            batch = world.futures(count).randomize_position(
                "Mover", x=(-1.0, 1.0), y=(-1.0, 1.0), z=(0.0, 0.0), seed=17
            )
            creation = time.perf_counter() - start
            start = time.perf_counter()
            batch.evaluate([distance("Mover", "Target")])
            elapsed = time.perf_counter() - start
            report["scaling"].append(
                {
                    "futures": count,
                    "creation_seconds": creation,
                    "distance_seconds": elapsed,
                    "delta_bytes": batch.delta_bytes,
                }
            )
        lower = [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]]
        upper = [[1.0, 1.0, 1.0], [3.0, 1.0, 1.0]]
        report["cpu_distance_oracle"] = evaluate_aabb_distances_cpu(
            lower, upper, [[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]], [0, 1]
        ).tolist()
    return report


def markdown(report: dict[str, Any]) -> str:
    rows = report.get("scaling", [])
    scaling = (
        "\n".join(
            f"| {row['futures']} | {row['creation_seconds']:.6f} | "
            f"{row['distance_seconds']:.6f} | {row['delta_bytes']} |"
            for row in rows
        )
        or "| — | — | — | — |"
    )
    gpu = report["gpu_validation"]
    tested_kernels = ", ".join(gpu["custom_warp_kernels_tested"]) or "none"
    if gpu["cpu_gpu_parity"] == "PASS":
        gpu_boundary = (
            f"CUDA validation PASSED on `{gpu['device']}`. The custom Warp kernels were "
            "validated against their CPU oracles with matching results."
        )
    elif report["cuda"]["cuda_available"]:
        gpu_boundary = (
            f"CUDA was available on `{gpu['device']}`, but custom-kernel validation did not "
            "pass. See the GPU Validation section for failures."
        )
    else:
        gpu_boundary = f"CUDA validation could not be performed: {report['cuda']['reason']}"
    return (
        f"""# Futures audit

Status: **{report["status"]}**

This report was generated by `python tools/futures_audit.py --full --output FUTURES_AUDIT.md`.

## Reproducibility

- Revision: `{report["revision"]}`
- Python: `{report["python"]}`
- Platform: `{report["platform"]}`
- Scene objects: `{report["scene_objects"]}`
- Futures: `{report["futures"]}`
- CUDA: `{report["cuda"]["reason"]}`

## GPU Validation

- CUDA available: `{gpu["cuda_available"]}`
- CUDA device: `{gpu["device"] or "unavailable"}`
- Custom Warp kernels tested: `{tested_kernels}`
- CPU/GPU parity status: **{gpu["cpu_gpu_parity"]}**
- GPU test count/pass count: `{gpu["gpu_test_count"]}` / `{gpu["gpu_pass_count"]}`
- GPU execution actually used: `{gpu["gpu_execution_used"]}`

{gpu_boundary}

## Compact state evidence

- Shared snapshot: `{report["shared_snapshot"]}`
- Measured NumPy delta bytes: `{report["delta_bytes"]}`
- Logical float64 delta payload: `{report["logical_delta_bytes"]}`
- 10k evaluation seconds: `{report["evaluation_seconds"]:.6f}`
- Candidates without collision: `{report["selected_without_collision"]}`

## Scaling

| futures | creation seconds | distance seconds | delta bytes |
|---:|---:|---:|---:|
{scaling}

## CPU/GPU boundary

Visibility is a deterministic AABB bounding-volume experiment, not exact mesh occlusion.

Future GPU work should keep immutable bounds resident, batch ray and broad-phase kernels, and
perform filtering/ranking reductions before transferring selected candidates to Python.

## Limitations

"""
        + "\n".join(f"- {item}" for item in report["limitations"])
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("FUTURES_AUDIT.md"))
    args = parser.parse_args()
    report = audit(args.full)
    args.output.write_text(markdown(report), encoding="utf-8")
    Path("FUTURES_RESULTS.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(markdown(report))


if __name__ == "__main__":
    main()
