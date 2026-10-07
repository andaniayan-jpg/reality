"""Read-only runtime status reporting."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from .detector import detect_hardware


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    local_ai: str
    vision_mode: str
    hardware: str
    setup_policy: str

    def __str__(self) -> str:
        return (
            f"Local AI engine: {self.local_ai}\nVision mode: {self.vision_mode}\n"
            f"Hardware: {self.hardware}\nSetup: {self.setup_policy}"
        )


def status() -> RuntimeStatus:
    """Return status without installing engines, downloading models, or calling cloud APIs."""
    profile = detect_hardware()
    # Detector intentionally observes hardware only. A live service check would
    # be a network side effect and is not necessary for import/status.
    ai = "not checked (use an AI feature to connect)"
    vision = (
        "cloud-enabled"
        if getenv("GEMINI_API_KEY") or getenv("REALITY_GEMINI_API_KEY")
        else "local fallback"
    )
    ram = f"{profile.ram_bytes / 1024**3:.1f} GiB" if profile.ram_bytes is not None else "unknown"
    hardware = f"RAM {ram}; GPU {profile.gpu_name or 'not detected'}"
    return RuntimeStatus(
        ai, vision, hardware, "explicit opt-in only; imports do not download software"
    )
