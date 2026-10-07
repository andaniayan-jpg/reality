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


_history: list[dict[str, str]] = []
_UNAVAILABLE = (
    "The local AI assistant is unavailable. Start your configured local AI service "
    "and install a supported model, then try again."
)


def copilot(
    prompt: str,
    obj: PhysicsObject | None = None,
    *,
    complexity: Literal["fast", "deep", "agent"] = "fast",
    realtime: bool = False,
    router: ModelRouter | None = None,
) -> AIResponse:
    """Ask a grounded advisory question without turning model text into evidence.

    Provider failures are deliberately converted into an actionable plain string.
    The legacy ``.text`` and ``.mode`` attributes remain available on the returned
    string-compatible :class:`AIResponse`.
    """
    if obj is not None:
        if not isinstance(obj, PhysicsObject):
            return AIResponse("Copilot context must be a PhysicsObject or PhysicsScene.", "local")
        prompt = (
            f"Question: {prompt}\nAuthoritative imported geometry: {obj.summary}\n"
            f"Evidence limits: {obj.limitations}\n"
            "Do not assert a physical failure, material grade or computed stress "
            "without sufficient data and validated analysis."
        )
    history = "\n".join(f"{item['role']}: {item['content']}" for item in _history[-8:])
    grounded_prompt = (
        "You are a physics-aware advisory assistant. Do not present estimates as "
        "measurements or make safety-critical conclusions without evidence.\n"
        f"Conversation so far:\n{history}\nUser: {prompt}"
        if history
        else "You are a physics-aware advisory assistant. Do not present estimates as "
        f"measurements or make safety-critical conclusions without evidence.\nUser: {prompt}"
    )
    try:
        task = AITask(prompt=grounded_prompt, complexity=complexity, realtime=realtime)
        selected = router or _default_router()
        response = (
            selected.route(task)
            if router is not None or detect_mode() == "online"
            else selected.route_feature("copilot", task)
        )
    except (AIUnavailableError, ValueError, OSError):
        # Preserve the established cloud-mode contract: an explicitly selected
        # undeployed cloud gateway fails closed instead of silently changing mode.
        if router is None and detect_mode() == "online":
            raise
        return AIResponse(_UNAVAILABLE, "local")
    _history.extend(
        ({"role": "user", "content": prompt}, {"role": "assistant", "content": response.text})
    )
    return response


def _reset() -> None:
    """Clear the in-memory session history for :func:`copilot`."""
    _history.clear()


# A method attribute keeps ``reality.copilot.reset()`` compact while the
# callable remains compatible with the original function-shaped API.
copilot.reset = _reset  # type: ignore[attr-defined]
