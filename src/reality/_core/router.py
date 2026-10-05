"""Deterministic task routing with retryable-only model fallback."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from reality._providers.base import (
    AIResponse,
    AITask,
    AIUnavailableError,
    Provider,
    RetryableProviderError,
)

from .auth import detect_mode

Mode = Literal["local", "online"]

# Internal policy only. Model identifiers are deliberately absent from public
# responses, but provider/data-transfer behavior is documented for users.
Feature = Literal[
    "copilot",
    "reason.predict",
    "reason.forces",
    "reason.cascade",
    "simulate.world",
    "simulate.stream",
    "generate.object",
    "generate.scene",
    "twin.predict",
    "twin.anomalies",
    "twin.from_video",
    "agents.spawn",
    "agents.train",
    "perceive.from_image",
    "capture.from_image",
]

_VISION_FEATURES: frozenset[Feature] = frozenset(
    {"perceive.from_image", "capture.from_image", "twin.from_video"}
)
_FAST_FEATURES: frozenset[Feature] = frozenset({"simulate.stream"})
_CODER_FEATURES: frozenset[Feature] = frozenset({"generate.object"})
_TEXT_FEATURES: frozenset[Feature] = frozenset(
    {
        "copilot",
        "reason.predict",
        "reason.forces",
        "reason.cascade",
        "simulate.world",
        "simulate.stream",
        "generate.object",
        "generate.scene",
        "twin.predict",
        "twin.anomalies",
        "agents.spawn",
        "agents.train",
    }
)


def _local_feature_model(feature: Feature, *, realtime: bool) -> str:
    if realtime or feature in _FAST_FEATURES:
        return "phi4:mini"
    if feature in _CODER_FEATURES:
        return "deepseek-coder-v2"
    return "qwen3:14b"


def _installed_model(wanted: str, installed: tuple[str, ...]) -> str | None:
    return next((model for model in installed if model in {wanted, f"{wanted}:latest"}), None)


def select_local_model(task: AITask, installed: tuple[str, ...]) -> str:
    """Only select a model the user has already installed."""
    variable = "REALITY_LOCAL_VISION_MODEL" if task.kind == "vision" else "REALITY_LOCAL_MODEL"
    requested = os.getenv(variable)
    preferred = ("qwen2-vl:7b",) if task.kind == "vision" else ("qwen3:14b", "phi4:mini")
    for wanted in ((requested,) if requested else ()) + preferred:
        for model in installed:
            if model == wanted or model.startswith(f"{wanted}:"):
                return model
    raise AIUnavailableError("No compatible local AI model is installed; see docs/ai-runtime.md")


class ModelRouter:
    """Injectable router. Hosted deployment supplies server-side adapters."""

    def __init__(
        self,
        providers: Mapping[str, Provider],
        *,
        local_models: tuple[str, ...] = (),
    ) -> None:
        self.providers = dict(providers)
        self.local_models = local_models

    def route_feature(self, feature: Feature, task: AITask) -> AIResponse:
        """Apply the explicit local-first feature map without implicit downloads.

        Vision alone may use the configured cloud vision provider. Missing or
        failing cloud vision falls back to an *installed* local vision model.
        If neither path works, fail honestly rather than fabricate a scene.
        """
        if feature not in _VISION_FEATURES | _TEXT_FEATURES:
            raise ValueError("unsupported AI feature")
        if task.kind == "vision":
            cloud = self.providers.get("gemini")
            if cloud is not None:
                try:
                    answer = cloud.complete(task, model="gemini-2.5-flash")
                    if answer.strip():
                        return AIResponse(text=answer, mode="online")
                except (AIUnavailableError, RetryableProviderError):
                    pass
            local = self.providers.get("local")
            for wanted in ("qwen2-vl:7b", "llava:7b"):
                model = _installed_model(wanted, self.local_models)
                if local is None or model is None:
                    continue
                try:
                    answer = local.complete(task, model=model)
                    if answer.strip():
                        return AIResponse(text=answer, mode="local")
                except (AIUnavailableError, RetryableProviderError):
                    continue
            raise AIUnavailableError(
                "Image analysis is unavailable; configure vision or install a local vision engine"
            )

        if feature in _VISION_FEATURES:
            raise ValueError("this feature requires an image")
        local = self.providers.get("local")
        model = _installed_model(
            _local_feature_model(feature, realtime=task.realtime), self.local_models
        )
        if local is None or model is None:
            raise AIUnavailableError(
                "The required local AI engine is not ready; see docs/ai-runtime.md"
            )
        try:
            answer = local.complete(task, model=model)
        except (AIUnavailableError, RetryableProviderError) as error:
            raise AIUnavailableError("Local AI is temporarily unavailable") from error
        if not answer.strip():
            raise AIUnavailableError("Local AI returned no answer")
        return AIResponse(text=answer, mode="local")

    def route(self, task: AITask, *, mode: Mode | None = None) -> AIResponse:
        actual: Mode = mode or ("online" if detect_mode() == "online" else "local")
        if actual == "local":
            provider = self.providers.get("local")
            if provider is None:
                raise AIUnavailableError("local AI engine is not configured")
            model = select_local_model(task, self.local_models)
            try:
                text = provider.complete(task, model=model)
            except RetryableProviderError as error:
                raise AIUnavailableError("local AI is temporarily unavailable") from error
            if not text.strip():
                raise AIUnavailableError("local AI returned no text")
            return AIResponse(text=text, mode="local")

        scout = os.getenv("REALITY_GROQ_FAST_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        maverick = os.getenv(
            "REALITY_GROQ_DEEP_MODEL", "meta-llama/llama-4-maverick-17b-128e-instruct"
        )
        free = os.getenv("REALITY_OPENROUTER_FALLBACK_MODEL", "openrouter/free")
        choices: tuple[tuple[str, str], ...]
        if "cloud" in self.providers:
            choices = (("cloud", ""),)
        elif task.kind == "vision":
            choices = (("gemini", "gemini-2.5-flash"), ("groq", scout), ("openrouter", free))
        elif task.realtime:
            choices = (("groq", scout), ("gemini", "gemini-2.5-flash"), ("openrouter", free))
        elif task.complexity == "agent":
            nim_model = os.getenv("REALITY_NIM_AGENT_MODEL")
            choices = ((("nim", nim_model),) if nim_model else ()) + (
                ("groq", maverick),
                ("gemini", "gemini-2.5-flash"),
                ("openrouter", free),
            )
        elif task.complexity == "deep":
            choices = (
                ("groq", maverick),
                ("gemini", "gemini-2.5-flash"),
                ("openrouter", free),
            )
        else:
            choices = (("groq", scout), ("gemini", "gemini-2.5-flash"), ("openrouter", free))
        for name, model in choices:
            provider = self.providers.get(name)
            if provider is None:
                continue
            try:
                text = provider.complete(task, model=model)
                if text.strip():
                    return AIResponse(text=text, mode="online")
            except RetryableProviderError:
                continue
        raise AIUnavailableError("AI service is unavailable; try again later")
