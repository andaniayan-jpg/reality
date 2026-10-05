"""Text copilot; model output is not a physics or geometry measurement."""

from __future__ import annotations

import os
from typing import Literal

from reality._core.auth import detect_mode
from reality._core.router import ModelRouter
from reality._physics_object import PhysicsObject
from reality._providers.base import AIResponse, AITask, AIUnavailableError, Provider
from reality._providers.cloud import CloudProvider
from reality._providers.gemini import GeminiProvider
from reality._providers.ollama import OllamaProvider


def _default_router() -> ModelRouter:
    if detect_mode() == "online":
        base = os.getenv("REALITY_API_BASE")
        if not base:
            raise AIUnavailableError(
                "Reality Cloud AI is not deployed for this package; set REALITY_API_BASE "
                "when a compatible service is available"
            )
        return ModelRouter({"cloud": CloudProvider(base)})
    local = OllamaProvider()
    try:
        models = local.available_models()
    except AIUnavailableError:
        models = ()
    providers: dict[str, Provider] = {"local": local}
    vision_key = os.getenv("REALITY_GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if vision_key:
        providers["gemini"] = GeminiProvider(vision_key)
    return ModelRouter(providers, local_models=models)


def copilot(
    prompt: str,
    obj: PhysicsObject | None = None,
    *,
    complexity: Literal["fast", "deep", "agent"] = "fast",
    realtime: bool = False,
    router: ModelRouter | None = None,
) -> AIResponse:
    """Ask a model for guidance; never treat its text as measured physics."""
    if obj is not None:
        if not isinstance(obj, PhysicsObject):
            raise TypeError("copilot context must be a PhysicsObject")
        prompt = (
            f"Question: {prompt}\nAuthoritative imported geometry: {obj.summary}\n"
            f"Evidence limits: {obj.limitations}\n"
            "Do not assert a physical failure, material grade or computed stress "
            "without sufficient data and validated analysis."
        )
    task = AITask(prompt=prompt, complexity=complexity, realtime=realtime)
    selected = router or _default_router()
    if router is not None or detect_mode() == "online":
        return selected.route(task)
    return selected.route_feature("copilot", task)
