# Reality GPU Audit

## 1. Hardware

```json
{
  "warp_version": "1.17.0",
  "devices": [
    "cpu"
  ],
  "cuda_available": false,
  "warp_reason": "CUDA driver/device is unavailable.",
  "nvidia_smi": {
    "returncode": 127,
    "stdout": "",
    "stderr": "[WinError 2] The system cannot find the file specified"
  },
  "os": "Windows-10-10.0.26200-SP0",
  "python": "3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]"
}
```

## 2. CUDA Proof

```json
{
  "status": "FAIL",
  "device": [
    "cpu"
  ],
  "cuda_device_count": 0,
  "kernels_launched": 0,
  "reason": "CUDA driver/device is unavailable."
}
```

CUDA proof is PASS only when two custom Reality kernels have actually launched on CUDA.

## 3. Custom Reality GPU Kernels

| Kernel | Source | Purpose | Input/output layout |
|---|---|---|---|
| transform kernel | `_warp_ops.py` | branch/object XYZ deltas | arrays → arrays |
| AABB kernel | `_warp_ops.py` | broad-phase overlap | centers/extents/pairs → mask |

These kernels and wrappers are Reality-owned; `wp.launch`, device memory, compilation,
and synchronization are NVIDIA Warp functionality. Approximate Reality-owned kernel source
lines: 24.

## 4. CPU vs GPU Correctness

```json
{
  "status": "UNAVAILABLE",
  "reason": "No CUDA device; GPU kernels were not launched.",
  "operations": {}
}
```

## 5. Branch Scaling

```json
[
  {
    "branches": 1,
    "branch_setup_seconds": 1.8000009731622413e-06,
    "cpu_raw_seconds": 0.0003051999992749188,
    "gpu_kernel_seconds": null,
    "gpu_total_seconds": null,
    "kernel_speedup": null,
    "end_to_end_speedup": null,
    "branch_delta_bytes": 96,
    "cpu_collision_count": 0
  },
  {
    "branches": 10,
    "branch_setup_seconds": 1.5000005078036338e-06,
    "cpu_raw_seconds": 0.0001733999997668434,
    "gpu_kernel_seconds": null,
    "gpu_total_seconds": null,
    "kernel_speedup": null,
    "end_to_end_speedup": null,
    "branch_delta_bytes": 960,
    "cpu_collision_count": 3
  },
  {
    "branches": 100,
    "branch_setup_seconds": 1.0999992809956893e-06,
    "cpu_raw_seconds": 0.00038580000000365544,
    "gpu_kernel_seconds": null,
    "gpu_total_seconds": null,
    "kernel_speedup": null,
    "end_to_end_speedup": null,
    "branch_delta_bytes": 9600,
    "cpu_collision_count": 35
  },
  {
    "branches": 1000,
    "branch_setup_seconds": 1.0000003385357559e-06,
    "cpu_raw_seconds": 0.0030029999998077983,
    "gpu_kernel_seconds": null,
    "gpu_total_seconds": null,
    "kernel_speedup": null,
    "end_to_end_speedup": null,
    "branch_delta_bytes": 96000,
    "cpu_collision_count": 870
  },
  {
    "branches": 10000,
    "branch_setup_seconds": 1.6999983927235007e-06,
    "cpu_raw_seconds": 0.17477669999971113,
    "gpu_kernel_seconds": null,
    "gpu_total_seconds": null,
    "kernel_speedup": null,
    "end_to_end_speedup": null,
    "branch_delta_bytes": 960000,
    "cpu_collision_count": 4006
  }
]
```

Timings synchronize before completion. GPU rows are null when CUDA is unavailable;
no speedup is fabricated. Warmed measurements exclude first-launch JIT from kernel timing.

## 6. GPU Memory

```json
[
  {
    "branches": 1,
    "base_scene_bytes": 1536,
    "branch_delta_bytes": 768,
    "naive_full_world_estimate_bytes": 2304,
    "method": "naive copies base min/max arrays per branch; Reality stores one base array plus branch/object/xyz deltas"
  },
  {
    "branches": 10,
    "base_scene_bytes": 1536,
    "branch_delta_bytes": 7680,
    "naive_full_world_estimate_bytes": 23040,
    "method": "naive copies base min/max arrays per branch; Reality stores one base array plus branch/object/xyz deltas"
  },
  {
    "branches": 100,
    "base_scene_bytes": 1536,
    "branch_delta_bytes": 76800,
    "naive_full_world_estimate_bytes": 230400,
    "method": "naive copies base min/max arrays per branch; Reality stores one base array plus branch/object/xyz deltas"
  },
  {
    "branches": 1000,
    "base_scene_bytes": 1536,
    "branch_delta_bytes": 768000,
    "naive_full_world_estimate_bytes": 2304000,
    "method": "naive copies base min/max arrays per branch; Reality stores one base array plus branch/object/xyz deltas"
  },
  {
    "branches": 10000,
    "base_scene_bytes": 1536,
    "branch_delta_bytes": 7680000,
    "naive_full_world_estimate_bytes": 23040000,
    "method": "naive copies base min/max arrays per branch; Reality stores one base array plus branch/object/xyz deltas"
  }
]
```

## 7. GPU Visibility/Collision/Predicate Benchmarks

The accelerated operations are reported separately in each branch-scaling row as
`gpu_transform_*` and `gpu_aabb_*` timings. The custom accelerated collision operation is
AABB broad-phase; visibility, navigation, MuJoCo simulation, graph logic, and explanation
remain CPU-only. When CUDA is unavailable, those operation-specific fields are correctly
absent rather than invented.

## 8. CPU Fallback

```json
{
  "status": "PASS"
}
```

The ordinary Reality suite imports and runs without CUDA. CUDA-specific tests skip with an
explicit reason on non-NVIDIA hosts; skipped tests are not GPU validation passes.

## 9. Full Tests

```json
{
  "passed": 61,
  "failed": 0,
  "skipped": 3,
  "xfailed": 0,
  "runtime_seconds": 3.2697484999989683,
  "returncode": 0
}
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

REALITY_GPU_STATUS=PARTIAL

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
