"""Explicit local configuration; importing Reality never writes user files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypedDict, cast


class RealityConfig(TypedDict):
    vision_quality: Literal["high", "fast"]
    simulation_backend: Literal["auto", "pybullet", "builtin"]
    language: str


_DEFAULT: RealityConfig = {
    "vision_quality": "high",
    "simulation_backend": "auto",
    "language": "en",
}


def configure(
    *,
    vision_quality: Literal["high", "fast"] = "high",
    simulation_backend: Literal["auto", "pybullet", "builtin"] = "auto",
    language: str = "en",
) -> RealityConfig:
    """Persist explicit preferences in ``~/.reality/config.json``."""
    if not language or len(language) > 16:
        raise ValueError("language must be a short non-empty language code")
    result: RealityConfig = {
        "vision_quality": vision_quality,
        "simulation_backend": simulation_backend,
        "language": language,
    }
    target = Path.home() / ".reality" / "config.json"
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def configuration() -> RealityConfig:
    """Return persisted settings or safe defaults without writing anything."""
    target = Path.home() / ".reality" / "config.json"
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _DEFAULT.copy()
    if not isinstance(raw, dict):
        return _DEFAULT.copy()
    vision = raw.get("vision_quality")
    backend = raw.get("simulation_backend")
    language = raw.get("language")
    clean_vision = vision if vision in {"high", "fast"} else "high"
    clean_backend = backend if backend in {"auto", "pybullet", "builtin"} else "auto"
    return {
        "vision_quality": cast(Literal["high", "fast"], clean_vision),
        "simulation_backend": cast(Literal["auto", "pybullet", "builtin"], clean_backend),
        "language": language if isinstance(language, str) else "en",
    }
