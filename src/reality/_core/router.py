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
