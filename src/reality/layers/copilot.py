"""Text copilot; model output is not a physics or geometry measurement."""

from __future__ import annotations

import os
from typing import Literal

from reality._core.auth import detect_mode
from reality._core.router import ModelRouter
from reality._providers.base import AIResponse, AITask, AIUnavailableError
from reality._providers.cloud import CloudProvider
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
    return ModelRouter({"local": local}, local_models=local.available_models())


def copilot(
    prompt: str,
    *,
    complexity: Literal["fast", "deep", "agent"] = "fast",
    realtime: bool = False,
    router: ModelRouter | None = None,
) -> AIResponse:
    """Ask a model for guidance; never treat its text as measured physics."""
    task = AITask(prompt=prompt, complexity=complexity, realtime=realtime)
    return (router or _default_router()).route(task)
