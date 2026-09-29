"""Optional NVIDIA Warp capability probing without import-time GPU requirements."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class AccelerationUnavailableError(RuntimeError):
    """Raised when a requested numerical accelerator cannot run."""


@dataclass(frozen=True, slots=True)
class WarpStatus:
    installed: bool
    version: str | None
    cuda_available: bool
    devices: tuple[str, ...]
    reason: str


def warp_status() -> WarpStatus:
    try:
        import warp as wp
    except ImportError:
        return WarpStatus(False, None, False, (), "warp-lang is not installed")
    try:
        cache = Path(tempfile.gettempdir()) / "reality-warp-cache"
        os.environ.setdefault("WARP_CACHE_PATH", str(cache))
        wp.init()
        devices = tuple(str(device) for device in wp.get_devices())
        available = bool(wp.is_cuda_available())
        return WarpStatus(
            True,
            str(wp.__version__),
            available,
            devices,
            "CUDA is available." if available else "CUDA driver/device is unavailable.",
        )
    except Exception as error:  # pragma: no cover - depends on host driver/runtime
        return WarpStatus(
            True,
            str(wp.__version__),
            False,
            (),
            f"Warp initialization failed: {error}",
        )


def require_cuda() -> None:
    status = warp_status()
    if not status.installed:
        raise AccelerationUnavailableError(
            "CUDA backend requires optional dependency 'warp-lang'; install reality[gpu]. "
            "Select backend='cpu'."
        )
    if not status.cuda_available:
        raise AccelerationUnavailableError(
            "NVIDIA Warp is installed but no usable CUDA driver/device is available. "
            "Select backend='cpu'."
        )
