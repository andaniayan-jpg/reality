"""OpenRouter fallback adapter; free routing has no availability guarantee."""

from __future__ import annotations

from .openai_compatible import ChatCompletionsProvider


class OpenRouterProvider(ChatCompletionsProvider):
    def __init__(self, api_key: str, *, timeout: float = 60.0) -> None:
        super().__init__("https://openrouter.ai/api/v1/chat/completions", api_key, timeout=timeout)
