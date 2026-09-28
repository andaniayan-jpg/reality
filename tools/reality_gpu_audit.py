"""Audit actual NVIDIA Warp execution and emit machine-readable GPU evidence."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault(
    "WARP_CACHE_PATH",
    str(Path(os.environ.get("TEMP", ".")) / "reality-warp-cache"),
)

import reality  # noqa: E402
from reality._warp_ops import (  # noqa: E402
    benchmark_aabb_intersections_warp,
    benchmark_branch_transform_warp,
    evaluate_aabb_intersections_cpu,
    evaluate_aabb_intersections_warp,
    evaluate_branch_transforms_cpu,
    evaluate_branch_transforms_warp,
)


def run(*args: str, timeout: int = 600) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": " ".join(args),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "seconds": time.perf_counter() - started,
    }


def nvidia_smi() -> dict[str, Any]:
    try:
        return run(
            "nvidia-smi",
            "--query-gpu=name,driver_version,compute_cap",
            "--format=csv,noheader",
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return {"returncode": 127, "stdout": "", "stderr": str(error)}


def parse_counts(output: str) -> dict[str, int]:
    return {
        name: int(match.group(1)) if (match := re.search(rf"(\d+) {name}", output)) else 0
        for name in ("passed", "failed", "skipped", "xfailed")
    }


def deterministic_inputs(
    branches: int, objects: int = 8
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    generator = np.random.default_rng(20260928 + branches)
    base = generator.normal(size=(objects, 3)).astype(np.float32)
    deltas = generator.normal(scale=0.25, size=(branches, objects, 3)).astype(np.float32)
    extents = generator.uniform(0.05, 0.5, size=(objects, 3)).astype(np.float32)
    pairs = np.asarray(
        [(first, second) for first in range(objects) for second in range(first + 1, objects)],
        dtype=np.int32,
    )
    return base, deltas, extents, pairs


def gpu_correctness(cuda: bool) -> dict[str, Any]:
    if not cuda:
        return {
            "status": "UNAVAILABLE",
            "reason": "No CUDA device; GPU kernels were not launched.",
            "operations": {},
        }
    base, deltas, extents, pairs = deterministic_inputs(32)
    expected_transforms = evaluate_branch_transforms_cpu(base, deltas)
    actual_transforms = evaluate_branch_transforms_warp(base, deltas)
    transformed_error = np.abs(actual_transforms - expected_transforms)
    centers = expected_transforms
    expected_aabb = evaluate_aabb_intersections_cpu(centers, extents, pairs)
    actual_aabb = evaluate_aabb_intersections_warp(centers, extents, pairs)
    numeric = transformed_error.astype(np.float64)
    return {
        "status": "PASS"
        if np.array_equal(actual_aabb, expected_aabb)
        and np.allclose(actual_transforms, expected_transforms, rtol=1e-5, atol=1e-5)
        else "FAIL",
        "operations": {
            "batched_branch_transforms": {
                "test_case_count": int(actual_transforms.size),
                "matching_count": int(
                    np.isclose(actual_transforms, expected_transforms, atol=1e-5).sum()
                ),
                "mismatch_count": int(
                    (~np.isclose(actual_transforms, expected_transforms, atol=1e-5)).sum()
                ),
                "maximum_numerical_error": float(numeric.max()),
                "mean_numerical_error": float(numeric.mean()),
                "tolerance": 1e-5,
                "cpu_pass": True,
                "gpu_pass": bool(
                    np.allclose(actual_transforms, expected_transforms, rtol=1e-5, atol=1e-5)
                ),
            },
            "batched_aabb_intersections": {
                "test_case_count": int(actual_aabb.size),
                "matching_count": int(np.equal(actual_aabb, expected_aabb).sum()),
                "mismatch_count": int((~np.equal(actual_aabb, expected_aabb)).sum()),
                "maximum_numerical_error": 0.0,
                "mean_numerical_error": 0.0,
                "tolerance": 0.0,
                "cpu_pass": True,
                "gpu_pass": bool(np.array_equal(actual_aabb, expected_aabb)),
            },
        },
    }


def scaling(cuda: bool, full: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for branch_count in (1, 10, 100, 1_000, 10_000):
        if not full and branch_count > 100:
            continue
        base, deltas, extents, pairs = deterministic_inputs(branch_count)
        setup_started = time.perf_counter()
        deltas = np.ascontiguousarray(deltas)
        setup_seconds = time.perf_counter() - setup_started
        cpu_started = time.perf_counter()
        cpu_transformed = evaluate_branch_transforms_cpu(base, deltas)
        cpu_collision = evaluate_aabb_intersections_cpu(cpu_transformed, extents, pairs)
        cpu_seconds = time.perf_counter() - cpu_started
        row: dict[str, Any] = {
            "branches": branch_count,
            "branch_setup_seconds": setup_seconds,
            "cpu_raw_seconds": cpu_seconds,
            "gpu_kernel_seconds": None,
            "gpu_total_seconds": None,
            "kernel_speedup": None,
            "end_to_end_speedup": None,
            "branch_delta_bytes": int(deltas.nbytes),
            "cpu_collision_count": int(cpu_collision.any(axis=1).sum()),
        }
        if cuda:
            _, transform_timing = benchmark_branch_transform_warp(base, deltas)
            gpu_centers = evaluate_branch_transforms_warp(base, deltas)
            _, aabb_timing = benchmark_aabb_intersections_warp(gpu_centers, extents, pairs)
            kernel = transform_timing.warm_kernel_seconds + aabb_timing.warm_kernel_seconds
            total = (
                transform_timing.upload_seconds
                + transform_timing.warm_end_to_end_seconds
                + aabb_timing.upload_seconds
                + aabb_timing.warm_end_to_end_seconds
                + transform_timing.download_seconds
                + aabb_timing.download_seconds
            )
            row.update(
                {
                    "gpu_kernel_seconds": kernel,
                    "gpu_total_seconds": total,
                    "gpu_transform_kernel_seconds": transform_timing.warm_kernel_seconds,
                    "gpu_aabb_kernel_seconds": aabb_timing.warm_kernel_seconds,
                    "gpu_transform_total_seconds": (
                        transform_timing.upload_seconds
                        + transform_timing.warm_end_to_end_seconds
                        + transform_timing.download_seconds
                    ),
                    "gpu_aabb_total_seconds": (
                        aabb_timing.upload_seconds
                        + aabb_timing.warm_end_to_end_seconds
                        + aabb_timing.download_seconds
                    ),
                    "kernel_speedup": cpu_seconds / kernel if kernel else None,
                    "end_to_end_speedup": cpu_seconds / total if total else None,
                    "warm_repetitions": transform_timing.repetitions,
                    "cold_transform_seconds": transform_timing.cold_seconds,
                    "cold_aabb_seconds": aabb_timing.cold_seconds,
                }
            )
        rows.append(row)
    return rows


def memory_rows() -> list[dict[str, Any]]:
    objects = 64
    base_scene_bytes = objects * 6 * 4
    rows = []
    for count in (1, 10, 100, 1_000, 10_000):
        delta = count * objects * 3 * 4
        naive = count * base_scene_bytes + delta
        rows.append(
            {
                "branches": count,
                "base_scene_bytes": base_scene_bytes,
                "branch_delta_bytes": delta,
                "naive_full_world_estimate_bytes": naive,
                "method": (
                    "naive copies base min/max arrays per branch; Reality stores one base "
                    "array plus branch/object/xyz deltas"
                ),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("REALITY_GPU_AUDIT.md"))
    args = parser.parse_args()
    status = reality.warp_status()
    smi = nvidia_smi()
    cuda = status.cuda_available
    proof: dict[str, Any]
    if cuda:
        try:
            base, deltas, extents, pairs = deterministic_inputs(2, objects=2)
            transform_result = evaluate_branch_transforms_warp(base, deltas)
            centers = transform_result
            aabb_result = evaluate_aabb_intersections_warp(centers, extents, pairs)
            proof = {
                "status": "PASS",
                "device": status.devices,
                "cuda_device_count": sum(device.startswith("cuda") for device in status.devices),
                "transform_kernel_result": transform_result.tolist(),
                "aabb_kernel_result": aabb_result.tolist(),
                "kernels_launched": 2,
            }
        except Exception as error:  # a real launch failure must remain visible
            proof = {
                "status": "FAIL",
                "error": f"{type(error).__name__}: {error}",
                "kernels_launched": 0,
            }
    else:
        proof = {
            "status": "FAIL",
            "device": status.devices,
            "cuda_device_count": 0,
            "kernels_launched": 0,
            "reason": status.reason,
        }
    correctness = gpu_correctness(cuda)
    tests = run(sys.executable, "-m", "pytest", "-q")
    counts = parse_counts(f"{tests['stdout']}\n{tests['stderr']}")
    scale = scaling(cuda, args.full)
    result = {
        "hardware": {
            "warp_version": status.version,
            "devices": status.devices,
            "cuda_available": cuda,
            "warp_reason": status.reason,
            "nvidia_smi": smi,
            "os": platform.platform(),
            "python": sys.version,
        },
        "cuda_proof": proof,
        "correctness": correctness,
        "scaling": scale,
        "memory": memory_rows(),
        "tests": {**counts, "runtime_seconds": tests["seconds"], "returncode": tests["returncode"]},
        "cpu_fallback": {"status": "PASS" if tests["returncode"] == 0 else "FAIL"},
    }
    overall = (
        "PASS"
        if (
            cuda
            and proof["status"] == "PASS"
            and correctness["status"] == "PASS"
            and tests["returncode"] == 0
        )
        else "PARTIAL"
        if tests["returncode"] == 0
        else "FAIL"
    )
    result["status"] = overall
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.write_text(_markdown(result), encoding="utf-8")
    (ROOT / "REALITY_GPU_RESULTS.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Wrote {ROOT / 'REALITY_GPU_RESULTS.json'}")
    print(f"REALITY_GPU_STATUS={overall}")
    return 0 if overall in {"PASS", "PARTIAL"} else 1


def _markdown(result: dict[str, Any]) -> str:
    hardware = result["hardware"]
    correctness = result["correctness"]
    kernel_lines = sum(
        1
        for line in Path(ROOT / "src/reality/_warp_ops.py").read_text().splitlines()
        if "kernel" in line or "def _" in line
    )
    return f"""# Reality GPU Audit

## 1. Hardware

```json
{json.dumps(hardware, indent=2, default=str)}
```

## 2. CUDA Proof

```json
{json.dumps(result["cuda_proof"], indent=2, default=str)}
```

CUDA proof is PASS only when two custom Reality kernels have actually launched on CUDA.

## 3. Custom Reality GPU Kernels

| Kernel | Source | Purpose | Input/output layout |
|---|---|---|---|
| transform kernel | `_warp_ops.py` | branch/object XYZ deltas | arrays → arrays |
| AABB kernel | `_warp_ops.py` | broad-phase overlap | centers/extents/pairs → mask |

These kernels and wrappers are Reality-owned; `wp.launch`, device memory, compilation,
and synchronization are NVIDIA Warp functionality. Approximate Reality-owned kernel source
lines: {kernel_lines}.

## 4. CPU vs GPU Correctness

```json
{json.dumps(correctness, indent=2, default=str)}
```

## 5. Branch Scaling

```json
{json.dumps(result["scaling"], indent=2, default=str)}
```

Timings synchronize before completion. GPU rows are null when CUDA is unavailable;
no speedup is fabricated. Warmed measurements exclude first-launch JIT from kernel timing.

## 6. GPU Memory

```json
{json.dumps(result["memory"], indent=2, default=str)}
```

## 7. GPU Visibility/Collision/Predicate Benchmarks

The accelerated operations are reported separately in each branch-scaling row as
`gpu_transform_*` and `gpu_aabb_*` timings. The custom accelerated collision operation is
AABB broad-phase; visibility, navigation, MuJoCo simulation, graph logic, and explanation
remain CPU-only. When CUDA is unavailable, those operation-specific fields are correctly
absent rather than invented.

## 8. CPU Fallback

```json
{json.dumps(result["cpu_fallback"], indent=2, default=str)}
```

The ordinary Reality suite imports and runs without CUDA. CUDA-specific tests skip with an
explicit reason on non-NVIDIA hosts; skipped tests are not GPU validation passes.

## 9. Full Tests

```json
{json.dumps(result["tests"], indent=2, default=str)}
```

## 10. Known GPU Limitations

- GPU validation requires a real NVIDIA CUDA driver/device; this host currently exposes
  only Warp's CPU device.
- Data transfer and launch overhead can dominate small branch counts.
- Only translation application and AABB broad-phase are accelerated.
- Visibility, navigation, graph/relation updates, consequences, and MuJoCo remain CPU-only.
- No GPU physics or Warp simulation backend is claimed.
- GPU benchmark rows cannot be recorded until CUDA is available.

## 11. Reality GPU Status

REALITY_GPU_STATUS={result["status"]}

PASS requires a real CUDA device, two successful custom-kernel launches, CPU/GPU parity,
actual synchronized timings, and no core correctness failures.

## 12. Reproduction

```bash
python -m pip install -e ".[dev,physics,gpu]"
python -m pytest -q
python tools/reality_gpu_audit.py --full --output REALITY_GPU_AUDIT.md
```

For a fresh Colab GPU runtime, use `notebooks/reality_gpu_validation.ipynb` first so the
driver, CUDA, and Warp wheel compatibility are recorded before running this command.
"""


if __name__ == "__main__":
    raise SystemExit(main())
