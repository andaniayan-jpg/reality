"""A side-effect-free plan for local AI setup.

Installing executables or downloading multi-gigabyte models is deliberately
not an import-time or implicit ``copilot`` side effect.
"""

from __future__ import annotations

from dataclasses import dataclass

from reality._providers.base import AIUnavailableError
from reality._providers.ollama import OllamaProvider

from .detector import HardwareProfile, detect_hardware


@dataclass(frozen=True, slots=True)
class LocalSetupPlan:
    engine_running: bool
    installed_models: tuple[str, ...]
    suggested_model: str | None
    hardware: HardwareProfile
    ready: bool


def local_setup_plan(provider: OllamaProvider | None = None) -> LocalSetupPlan:
    """Inspect only; unknown memory means no automatic model recommendation."""
    engine = provider or OllamaProvider()
    profile = detect_hardware()
    try:
        installed = engine.available_models()
        running = True
    except AIUnavailableError:
        installed = ()
        running = False
    ram = profile.ram_bytes
    recommended = (
        "qwen3:14b"
        if ram is not None and ram >= 24 * 1024**3
        else "phi4:mini"
        if ram is not None and ram >= 8 * 1024**3
        else None
    )
    ready = running and any(
        name == candidate or name.startswith(f"{candidate}:")
        for name in installed
        for candidate in ("qwen3:14b", "phi4:mini")
    )
    return LocalSetupPlan(running, installed, recommended, profile, ready)
