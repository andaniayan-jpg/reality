"""Conservative hardware discovery for local model selection."""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    """Unknown values are ``None``; they are never guessed from CPU count."""

    ram_bytes: int | None
    vram_bytes: int | None
    gpu_name: str | None
    cpu_cores: int | None


def _ram_bytes() -> int | None:
    if platform.system() == "Windows":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong),
                ("available_phys", ctypes.c_ulonglong),
                ("total_page", ctypes.c_ulonglong),
                ("available_page", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        success = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return int(status.total_phys) if success else None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    sysconf = getattr(os, "sysconf", None)
    if sysconf is None:
        return None
    try:
        return int(sysconf("SC_PHYS_PAGES") * sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError):
        return None


def detect_hardware() -> HardwareProfile:
    """Probe RAM and, when present, one NVIDIA GPU without importing CUDA."""
    gpu_name: str | None = None
    vram_bytes: int | None = None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            name, mib = result.stdout.splitlines()[0].rsplit(",", maxsplit=1)
            gpu_name = name.strip()
            vram_bytes = int(mib.strip()) * 1024**2
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return HardwareProfile(_ram_bytes(), vram_bytes, gpu_name, os.cpu_count())
