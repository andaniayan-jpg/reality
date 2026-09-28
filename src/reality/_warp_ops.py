# mypy: ignore-errors

"""Optional custom NVIDIA Warp kernels with NumPy reference implementations.

The kernels in this module are deliberately small numerical primitives.  Graph,
relationship, explanation, and backend-selection logic remains on the CPU.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ._accelerators import AccelerationUnavailableError, require_cuda

try:
    import warp as wp  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - exercised on minimal CPU installs
    wp = None  # type: ignore[assignment]


FloatArray = NDArray[np.float32]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class WarpOperationTiming:
    """Measured transfer and synchronized kernel timings for one operation."""

    cold_seconds: float
    warm_kernel_seconds: float
    warm_end_to_end_seconds: float
    upload_seconds: float
    download_seconds: float
    repetitions: int


if wp is not None:

    @wp.kernel
    def _apply_branch_transforms_kernel(
        base_positions: wp.array(dtype=wp.vec3),
        deltas: wp.array(dtype=wp.vec3),
        output: wp.array(dtype=wp.vec3),
        object_count: int,
    ):
        thread = wp.tid()
        branch = thread // object_count
        object_index = thread % object_count
        output[thread] = base_positions[object_index] + deltas[branch * object_count + object_index]

    @wp.kernel
    def _aabb_intersections_kernel(
        centers: wp.array(dtype=wp.vec3),
        half_extents: wp.array(dtype=wp.vec3),
        first: wp.array(dtype=wp.int32),
        second: wp.array(dtype=wp.int32),
        output: wp.array(dtype=wp.int32),
        object_count: int,
        pair_count: int,
    ):
        thread = wp.tid()
        branch = thread // pair_count
        pair_index = thread % pair_count
        first_index = first[pair_index]
        second_index = second[pair_index]
        first_center = centers[branch * object_count + first_index]
        second_center = centers[branch * object_count + second_index]
        first_extent = half_extents[first_index]
        second_extent = half_extents[second_index]
        separation = wp.abs(first_center - second_center)
        limit = first_extent + second_extent
        overlap = 1
        if separation[0] > limit[0] or separation[1] > limit[1] or separation[2] > limit[2]:
            overlap = 0
        output[thread] = overlap

    @wp.kernel
    def _aabb_distances_kernel(
        minimum: wp.array(dtype=wp.vec3),
        maximum: wp.array(dtype=wp.vec3),
        deltas: wp.array(dtype=wp.vec3),
        first: int,
        second: int,
        output: wp.array(dtype=float),
        object_count: int,
    ):
        """Compute one AABB separation distance per branch."""
        branch = wp.tid()
        first_bounds = minimum[first] + deltas[branch * object_count + first]
        first_upper = maximum[first] + deltas[branch * object_count + first]
        second_bounds = minimum[second] + deltas[branch * object_count + second]
        second_upper = maximum[second] + deltas[branch * object_count + second]
        gap_x = wp.max(
            wp.max(second_bounds[0] - first_upper[0], first_bounds[0] - second_upper[0]), 0.0
        )
        gap_y = wp.max(
            wp.max(second_bounds[1] - first_upper[1], first_bounds[1] - second_upper[1]), 0.0
        )
        gap_z = wp.max(
            wp.max(second_bounds[2] - first_upper[2], first_bounds[2] - second_upper[2]), 0.0
        )
        output[branch] = wp.sqrt(gap_x * gap_x + gap_y * gap_y + gap_z * gap_z)

    @wp.kernel
    def _aabb_visibility_kernel(
        minimum: wp.array(dtype=wp.vec3),
        maximum: wp.array(dtype=wp.vec3),
        deltas: wp.array(dtype=wp.vec3),
        target: int,
        viewer: int,
        output: wp.array(dtype=wp.int32),
        object_count: int,
    ):
        """Determine centre-to-centre AABB line-of-sight for one branch."""
        branch = wp.tid()
        viewer_offset = deltas[branch * object_count + viewer]
        target_offset = deltas[branch * object_count + target]
        origin = (minimum[viewer] + maximum[viewer]) * 0.5 + viewer_offset
        destination = (minimum[target] + maximum[target]) * 0.5 + target_offset
        direction = destination - origin
        visible = 1
        for object_index in range(object_count):
            if object_index != target and object_index != viewer:
                offset = deltas[branch * object_count + object_index]
                lower = minimum[object_index] + offset
                upper = maximum[object_index] + offset
                low = 0.0
                high = 1.0
                valid = 1
                if wp.abs(direction[0]) <= 1.0e-12:
                    if origin[0] < lower[0] or origin[0] > upper[0]:
                        valid = 0
                else:
                    first = (lower[0] - origin[0]) / direction[0]
                    second = (upper[0] - origin[0]) / direction[0]
                    low = wp.max(low, wp.min(first, second))
                    high = wp.min(high, wp.max(first, second))
                if wp.abs(direction[1]) <= 1.0e-12:
                    if origin[1] < lower[1] or origin[1] > upper[1]:
                        valid = 0
                else:
                    first = (lower[1] - origin[1]) / direction[1]
                    second = (upper[1] - origin[1]) / direction[1]
                    low = wp.max(low, wp.min(first, second))
                    high = wp.min(high, wp.max(first, second))
                if wp.abs(direction[2]) <= 1.0e-12:
                    if origin[2] < lower[2] or origin[2] > upper[2]:
                        valid = 0
                else:
                    first = (lower[2] - origin[2]) / direction[2]
                    second = (upper[2] - origin[2]) / direction[2]
                    low = wp.max(low, wp.min(first, second))
                    high = wp.min(high, wp.max(first, second))
                if valid == 1 and high >= low and high >= 0.0 and low <= 1.0:
                    visible = 0
        output[branch] = visible


def evaluate_branch_transforms_cpu(
    base_positions: NDArray[np.floating[Any]],
    deltas: NDArray[np.floating[Any]],
) -> NDArray[np.float32]:
    """CPU oracle for applying one translation vector per branch/object."""
    base = np.asarray(base_positions, dtype=np.float32)
    offsets = np.asarray(deltas, dtype=np.float32)
    if base.ndim != 2 or base.shape[1] != 3:
        raise ValueError("base_positions must have shape (objects, 3)")
    if offsets.ndim != 3 or offsets.shape[1:] != base.shape:
        raise ValueError("deltas must have shape (branches, objects, 3)")
    return base[None, :, :] + offsets


def evaluate_aabb_intersections_cpu(
    centers: NDArray[np.floating[Any]],
    half_extents: NDArray[np.floating[Any]],
    pairs: NDArray[np.integer[Any]],
) -> BoolArray:
    """CPU oracle for batched AABB pair overlap."""
    branch_centers = np.asarray(centers, dtype=np.float32)
    extents = np.asarray(half_extents, dtype=np.float32)
    pair_indices = np.asarray(pairs, dtype=np.int32)
    if branch_centers.ndim != 3 or branch_centers.shape[2] != 3:
        raise ValueError("centers must have shape (branches, objects, 3)")
    if extents.shape != branch_centers.shape[1:]:
        raise ValueError("half_extents must have shape (objects, 3)")
    if pair_indices.ndim != 2 or pair_indices.shape[1] != 2:
        raise ValueError("pairs must have shape (pairs, 2)")
    first = branch_centers[:, pair_indices[:, 0], :]
    second = branch_centers[:, pair_indices[:, 1], :]
    limits = extents[pair_indices[:, 0], :] + extents[pair_indices[:, 1], :]
    return np.all(np.abs(first - second) <= limits[None, :, :], axis=2)


def evaluate_aabb_distances_cpu(
    minimum: NDArray[np.floating[Any]],
    maximum: NDArray[np.floating[Any]],
    deltas: NDArray[np.floating[Any]],
    pair: NDArray[np.integer[Any]],
) -> NDArray[np.float32]:
    """CPU oracle for one AABB separation distance per branch."""
    lower = np.asarray(minimum, dtype=np.float32)
    upper = np.asarray(maximum, dtype=np.float32)
    offsets = np.asarray(deltas, dtype=np.float32)
    pair_indices = np.asarray(pair, dtype=np.int32)
    if lower.ndim != 2 or lower.shape[1] != 3 or upper.shape != lower.shape:
        raise ValueError("minimum and maximum must have shape (objects, 3)")
    if offsets.ndim != 3 or offsets.shape[1:] != lower.shape:
        raise ValueError("deltas must have shape (branches, objects, 3)")
    if pair_indices.shape != (2,):
        raise ValueError("pair must have shape (2,)")
    first, second = (int(pair_indices[0]), int(pair_indices[1]))
    first_lower = lower[first][None, :] + offsets[:, first, :]
    first_upper = upper[first][None, :] + offsets[:, first, :]
    second_lower = lower[second][None, :] + offsets[:, second, :]
    second_upper = upper[second][None, :] + offsets[:, second, :]
    gaps = np.maximum.reduce(
        [
            np.zeros_like(first_lower),
            second_lower - first_upper,
            first_lower - second_upper,
        ]
    )
    return np.linalg.norm(gaps, axis=1).astype(np.float32, copy=False)


def evaluate_aabb_visibility_cpu(
    minimum: NDArray[np.floating[Any]],
    maximum: NDArray[np.floating[Any]],
    deltas: NDArray[np.floating[Any]],
    target: int,
    viewer: int,
) -> BoolArray:
    """CPU oracle for deterministic centre-ray AABB visibility per branch."""
    lower = np.asarray(minimum, dtype=np.float32)
    upper = np.asarray(maximum, dtype=np.float32)
    offsets = np.asarray(deltas, dtype=np.float32)
    if lower.ndim != 2 or lower.shape[1] != 3 or upper.shape != lower.shape:
        raise ValueError("minimum and maximum must have shape (objects, 3)")
    if offsets.ndim != 3 or offsets.shape[1:] != lower.shape:
        raise ValueError("deltas must have shape (branches, objects, 3)")
    if not 0 <= target < lower.shape[0] or not 0 <= viewer < lower.shape[0]:
        raise ValueError("target and viewer must be valid object indices")
    origin = (lower[viewer] + upper[viewer])[None, :] / 2.0 + offsets[:, viewer, :]
    destination = (lower[target] + upper[target])[None, :] / 2.0 + offsets[:, target, :]
    direction = destination - origin
    visible = np.ones(offsets.shape[0], dtype=np.bool_)
    for object_index in range(lower.shape[0]):
        if object_index in {target, viewer}:
            continue
        candidate_lower = lower[object_index][None, :] + offsets[:, object_index, :]
        candidate_upper = upper[object_index][None, :] + offsets[:, object_index, :]
        low = np.zeros(offsets.shape[0], dtype=np.float32)
        high = np.ones(offsets.shape[0], dtype=np.float32)
        valid = np.ones(offsets.shape[0], dtype=np.bool_)
        for axis in range(3):
            parallel = np.abs(direction[:, axis]) <= 1.0e-12
            valid &= ~parallel | (
                (origin[:, axis] >= candidate_lower[:, axis])
                & (origin[:, axis] <= candidate_upper[:, axis])
            )
            safe_direction = np.where(parallel, 1.0, direction[:, axis])
            first = (candidate_lower[:, axis] - origin[:, axis]) / safe_direction
            second = (candidate_upper[:, axis] - origin[:, axis]) / safe_direction
            low = np.maximum(low, np.minimum(first, second))
            high = np.minimum(high, np.maximum(first, second))
        visible &= ~(valid & (high >= low) & (high >= 0.0) & (low <= 1.0))
    return visible


def _ensure_warp(device: str) -> Any:
    if device.startswith("cuda"):
        require_cuda()
    if wp is None:  # defensive: require_cuda may race an uninstall
        raise AccelerationUnavailableError("warp-lang is not importable")
    os.environ.setdefault(
        "WARP_CACHE_PATH",
        os.path.join(tempfile.gettempdir(), "reality-warp-cache"),
    )
    wp.init()  # type: ignore[no-untyped-call]
    return wp


def evaluate_branch_transforms_warp(
    base_positions: NDArray[np.floating[Any]],
    deltas: NDArray[np.floating[Any]],
    *,
    device: str = "cuda:0",
) -> NDArray[np.float32]:
    """Launch Reality's branch-transform kernel and return synchronized results."""
    warp = _ensure_warp(device)
    base = np.asarray(base_positions, dtype=np.float32)
    offsets = np.asarray(deltas, dtype=np.float32)
    if base.ndim != 2 or base.shape[1] != 3:
        raise ValueError("base_positions must have shape (objects, 3)")
    if offsets.ndim != 3 or offsets.shape[1:] != base.shape:
        raise ValueError("deltas must have shape (branches, objects, 3)")
    count = base.shape[0]
    base_device = warp.array(base, dtype=warp.vec3, device=device)
    offsets_device = warp.array(offsets.reshape(-1, 3), dtype=warp.vec3, device=device)
    output_device = warp.zeros(offsets.shape[0] * count, dtype=warp.vec3, device=device)
    warp.launch(
        _apply_branch_transforms_kernel,
        dim=offsets.shape[0] * count,
        inputs=[base_device, offsets_device, output_device, count],
        device=device,
    )
    warp.synchronize_device(device)
    return np.asarray(output_device.numpy(), dtype=np.float32).reshape(offsets.shape)


def evaluate_aabb_intersections_warp(
    centers: NDArray[np.floating[Any]],
    half_extents: NDArray[np.floating[Any]],
    pairs: NDArray[np.integer[Any]],
    *,
    device: str = "cuda:0",
) -> BoolArray:
    """Launch Reality's batched AABB broad-phase kernel and synchronize it."""
    warp = _ensure_warp(device)
    branch_centers = np.asarray(centers, dtype=np.float32)
    extents = np.asarray(half_extents, dtype=np.float32)
    pair_indices = np.asarray(pairs, dtype=np.int32)
    if branch_centers.ndim != 3 or branch_centers.shape[2] != 3:
        raise ValueError("centers must have shape (branches, objects, 3)")
    if pair_indices.ndim != 2 or pair_indices.shape[1] != 2:
        raise ValueError("pairs must have shape (pairs, 2)")
    branch_count, object_count, _ = branch_centers.shape
    pair_count = pair_indices.shape[0]
    center_device = warp.array(branch_centers.reshape(-1, 3), dtype=warp.vec3, device=device)
    extent_device = warp.array(extents, dtype=warp.vec3, device=device)
    first_device = warp.array(pair_indices[:, 0], dtype=warp.int32, device=device)
    second_device = warp.array(pair_indices[:, 1], dtype=warp.int32, device=device)
    output_device = warp.zeros(branch_count * pair_count, dtype=warp.int32, device=device)
    warp.launch(
        _aabb_intersections_kernel,
        dim=branch_count * pair_count,
        inputs=[
            center_device,
            extent_device,
            first_device,
            second_device,
            output_device,
            object_count,
            pair_count,
        ],
        device=device,
    )
    warp.synchronize_device(device)
    return (
        np.asarray(output_device.numpy(), dtype=np.int32)
        .reshape(branch_count, pair_count)
        .astype(np.bool_, copy=False)
    )


def evaluate_aabb_distances_warp(
    minimum: NDArray[np.floating[Any]],
    maximum: NDArray[np.floating[Any]],
    deltas: NDArray[np.floating[Any]],
    pair: NDArray[np.integer[Any]],
    *,
    device: str = "cuda:0",
) -> NDArray[np.float32]:
    """Launch Reality's custom AABB distance kernel and synchronize it."""
    warp = _ensure_warp(device)
    lower = np.asarray(minimum, dtype=np.float32)
    upper = np.asarray(maximum, dtype=np.float32)
    offsets = np.asarray(deltas, dtype=np.float32)
    pair_indices = np.asarray(pair, dtype=np.int32)
    if lower.ndim != 2 or lower.shape[1] != 3 or upper.shape != lower.shape:
        raise ValueError("minimum and maximum must have shape (objects, 3)")
    if offsets.ndim != 3 or offsets.shape[1:] != lower.shape:
        raise ValueError("deltas must have shape (branches, objects, 3)")
    if pair_indices.shape != (2,):
        raise ValueError("pair must have shape (2,)")
    object_count = lower.shape[0]
    lower_device = warp.array(lower, dtype=warp.vec3, device=device)
    upper_device = warp.array(upper, dtype=warp.vec3, device=device)
    offsets_device = warp.array(offsets.reshape(-1, 3), dtype=warp.vec3, device=device)
    output_device = warp.zeros(offsets.shape[0], dtype=warp.float32, device=device)
    warp.launch(
        _aabb_distances_kernel,
        dim=offsets.shape[0],
        inputs=[
            lower_device,
            upper_device,
            offsets_device,
            int(pair_indices[0]),
            int(pair_indices[1]),
            output_device,
            object_count,
        ],
        device=device,
    )
    warp.synchronize_device(device)
    return np.asarray(output_device.numpy(), dtype=np.float32)


def evaluate_aabb_visibility_warp(
    minimum: NDArray[np.floating[Any]],
    maximum: NDArray[np.floating[Any]],
    deltas: NDArray[np.floating[Any]],
    target: int,
    viewer: int,
    *,
    device: str = "cuda:0",
) -> BoolArray:
    """Launch Reality's deterministic AABB visibility kernel and synchronize it."""
    warp = _ensure_warp(device)
    lower = np.asarray(minimum, dtype=np.float32)
    upper = np.asarray(maximum, dtype=np.float32)
    offsets = np.asarray(deltas, dtype=np.float32)
    if lower.ndim != 2 or lower.shape[1] != 3 or upper.shape != lower.shape:
        raise ValueError("minimum and maximum must have shape (objects, 3)")
    if offsets.ndim != 3 or offsets.shape[1:] != lower.shape:
        raise ValueError("deltas must have shape (branches, objects, 3)")
    if not 0 <= target < lower.shape[0] or not 0 <= viewer < lower.shape[0]:
        raise ValueError("target and viewer must be valid object indices")
    object_count = lower.shape[0]
    lower_device = warp.array(lower, dtype=warp.vec3, device=device)
    upper_device = warp.array(upper, dtype=warp.vec3, device=device)
    offsets_device = warp.array(offsets.reshape(-1, 3), dtype=warp.vec3, device=device)
    output_device = warp.zeros(offsets.shape[0], dtype=warp.int32, device=device)
    warp.launch(
        _aabb_visibility_kernel,
        dim=offsets.shape[0],
        inputs=[
            lower_device,
            upper_device,
            offsets_device,
            target,
            viewer,
            output_device,
            object_count,
        ],
        device=device,
    )
    warp.synchronize_device(device)
    return np.asarray(output_device.numpy(), dtype=np.int32).astype(np.bool_, copy=False)


def benchmark_branch_transform_warp(
    base_positions: NDArray[np.floating[Any]],
    deltas: NDArray[np.floating[Any]],
    *,
    device: str = "cuda:0",
    repetitions: int = 5,
) -> tuple[NDArray[np.float32], WarpOperationTiming]:
    """Measure cold and warmed transform launches with explicit synchronization."""
    warp = _ensure_warp(device)
    base = np.asarray(base_positions, dtype=np.float32)
    offsets = np.asarray(deltas, dtype=np.float32)
    count = base.shape[0]
    upload_started = perf_counter()
    base_device = warp.array(base, dtype=warp.vec3, device=device)
    offsets_device = warp.array(offsets.reshape(-1, 3), dtype=warp.vec3, device=device)
    output_device = warp.zeros(offsets.shape[0] * count, dtype=warp.vec3, device=device)
    warp.synchronize_device(device)
    upload_seconds = perf_counter() - upload_started
    cold_started = perf_counter()
    warp.launch(
        _apply_branch_transforms_kernel,
        dim=offsets.shape[0] * count,
        inputs=[base_device, offsets_device, output_device, count],
        device=device,
    )
    warp.synchronize_device(device)
    cold_seconds = perf_counter() - cold_started
    warm_kernel = 0.0
    warm_end_to_end = 0.0
    for _ in range(repetitions):
        started = perf_counter()
        warp.launch(
            _apply_branch_transforms_kernel,
            dim=offsets.shape[0] * count,
            inputs=[base_device, offsets_device, output_device, count],
            device=device,
        )
        warp.synchronize_device(device)
        kernel_finished = perf_counter()
        output_device.numpy()
        warm_kernel += kernel_finished - started
        warm_end_to_end += perf_counter() - started
    download_started = perf_counter()
    result = np.asarray(output_device.numpy(), dtype=np.float32).reshape(offsets.shape)
    warp.synchronize_device(device)
    download_seconds = perf_counter() - download_started
    return result, WarpOperationTiming(
        cold_seconds,
        warm_kernel / repetitions,
        warm_end_to_end / repetitions,
        upload_seconds,
        download_seconds,
        repetitions,
    )


def benchmark_aabb_intersections_warp(
    centers: NDArray[np.floating[Any]],
    half_extents: NDArray[np.floating[Any]],
    pairs: NDArray[np.integer[Any]],
    *,
    device: str = "cuda:0",
    repetitions: int = 5,
) -> tuple[BoolArray, WarpOperationTiming]:
    """Measure cold and warmed synchronized AABB broad-phase launches."""
    warp = _ensure_warp(device)
    branch_centers = np.asarray(centers, dtype=np.float32)
    extents = np.asarray(half_extents, dtype=np.float32)
    pair_indices = np.asarray(pairs, dtype=np.int32)
    branch_count, object_count, _ = branch_centers.shape
    pair_count = pair_indices.shape[0]
    upload_started = perf_counter()
    center_device = warp.array(branch_centers.reshape(-1, 3), dtype=warp.vec3, device=device)
    extent_device = warp.array(extents, dtype=warp.vec3, device=device)
    first_device = warp.array(pair_indices[:, 0], dtype=warp.int32, device=device)
    second_device = warp.array(pair_indices[:, 1], dtype=warp.int32, device=device)
    output_device = warp.zeros(branch_count * pair_count, dtype=warp.int32, device=device)
    warp.synchronize_device(device)
    upload_seconds = perf_counter() - upload_started

    def launch() -> None:
        warp.launch(
            _aabb_intersections_kernel,
            dim=branch_count * pair_count,
            inputs=[
                center_device,
                extent_device,
                first_device,
                second_device,
                output_device,
                object_count,
                pair_count,
            ],
            device=device,
        )

    cold_started = perf_counter()
    launch()
    warp.synchronize_device(device)
    cold_seconds = perf_counter() - cold_started
    warm_kernel = 0.0
    warm_end_to_end = 0.0
    for _ in range(repetitions):
        started = perf_counter()
        launch()
        warp.synchronize_device(device)
        kernel_finished = perf_counter()
        output_device.numpy()
        warm_kernel += kernel_finished - started
        warm_end_to_end += perf_counter() - started
    download_started = perf_counter()
    result = (
        np.asarray(output_device.numpy(), dtype=np.int32)
        .reshape(branch_count, pair_count)
        .astype(np.bool_, copy=False)
    )
    warp.synchronize_device(device)
    download_seconds = perf_counter() - download_started
    return result, WarpOperationTiming(
        cold_seconds,
        warm_kernel / repetitions,
        warm_end_to_end / repetitions,
        upload_seconds,
        download_seconds,
        repetitions,
    )
