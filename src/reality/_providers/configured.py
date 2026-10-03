"""Construct online routing only from trusted server-side environment variables."""

from __future__ import annotations

import os

from reality._core.router import ModelRouter

from .base import AIUnavailableError, Provider
from .gemini import GeminiProvider
from .groq import GroqProvider
from .nim import NIMProvider
from .openrouter import OpenRouterProvider


def online_router_from_env() -> ModelRouter:
    providers: dict[str, Provider] = {}
    if key := os.getenv("REALITY_GEMINI_API_KEY"):
        providers["gemini"] = GeminiProvider(key)
    if key := os.getenv("REALITY_GROQ_API_KEY"):
        providers["groq"] = GroqProvider(key)
    if key := os.getenv("REALITY_NIM_API_KEY"):
        providers["nim"] = NIMProvider(key)
    if key := os.getenv("REALITY_OPENROUTER_API_KEY"):
        providers["openrouter"] = OpenRouterProvider(key)
    if not providers:
        raise AIUnavailableError("AI service is not configured")
    return ModelRouter(providers)
