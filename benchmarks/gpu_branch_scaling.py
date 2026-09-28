"""Measure CPU references and custom Warp branch kernels on an NVIDIA device."""

from __future__ import annotations

import argparse
import json
import platform
import time

import numpy as np

import reality
from reality._warp_ops import (
    benchmark_aabb_intersections_warp,
    benchmark_branch_transform_warp,
    evaluate_aabb_intersections_cpu,
    evaluate_branch_transforms_cpu,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    status = reality.warp_status()
    print(
        json.dumps(
            {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "warp": status.version,
                "devices": status.devices,
                "cuda_available": status.cuda_available,
                "reason": status.reason,
            },
            indent=2,
        )
    )
    if not status.cuda_available:
        print("GPU benchmark not run: no CUDA device is available; no result is fabricated.")
        return 0
    rng = np.random.default_rng(20260928)
    objects = 64
    base = rng.normal(size=(objects, 3)).astype(np.float32)
    extents = rng.uniform(0.05, 0.5, size=(objects, 3)).astype(np.float32)
    pairs = np.asarray(
        [(first, second) for first in range(objects) for second in range(first + 1, objects)],
        dtype=np.int32,
    )
    counts = (1, 10, 100, 1_000, 10_000) if args.full else (1, 10, 100)
    rows = []
    for count in counts:
        setup_started = time.perf_counter()
        deltas = rng.normal(scale=0.25, size=(count, objects, 3)).astype(np.float32)
        setup_seconds = time.perf_counter() - setup_started
        cpu_started = time.perf_counter()
        transformed = evaluate_branch_transforms_cpu(base, deltas)
        evaluate_aabb_intersections_cpu(transformed, extents, pairs)
        cpu_seconds = time.perf_counter() - cpu_started
        transformed_gpu, transform_timing = benchmark_branch_transform_warp(base, deltas)
        _, aabb_timing = benchmark_aabb_intersections_warp(transformed_gpu, extents, pairs)
        kernel_seconds = transform_timing.warm_kernel_seconds + aabb_timing.warm_kernel_seconds
        total_seconds = (
            transform_timing.upload_seconds
            + transform_timing.warm_end_to_end_seconds
            + aabb_timing.upload_seconds
            + aabb_timing.warm_end_to_end_seconds
            + transform_timing.download_seconds
            + aabb_timing.download_seconds
        )
        rows.append(
            {
                "branches": count,
                "setup_seconds": setup_seconds,
                "cpu_seconds": cpu_seconds,
                "gpu_kernel_seconds": kernel_seconds,
                "gpu_total_seconds": total_seconds,
                "gpu_transform_kernel_seconds": transform_timing.warm_kernel_seconds,
                "gpu_aabb_kernel_seconds": aabb_timing.warm_kernel_seconds,
                "kernel_speedup": cpu_seconds / kernel_seconds if kernel_seconds else None,
                "end_to_end_speedup": cpu_seconds / total_seconds if total_seconds else None,
                "gpu_upload_seconds": transform_timing.upload_seconds + aabb_timing.upload_seconds,
                "gpu_download_seconds": (
                    transform_timing.download_seconds + aabb_timing.download_seconds
                ),
                "warm_repetitions": transform_timing.repetitions,
                "cold_transform_seconds": transform_timing.cold_seconds,
                "cold_aabb_seconds": aabb_timing.cold_seconds,
                "branch_delta_bytes": int(deltas.nbytes),
            }
        )
    print(json.dumps({"rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
