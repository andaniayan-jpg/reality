"""Groq adapter; model identifiers remain router-configurable."""

from __future__ import annotations

from .openai_compatible import ChatCompletionsProvider


class GroqProvider(ChatCompletionsProvider):
    def __init__(self, api_key: str, *, timeout: float = 60.0) -> None:
        super().__init__(
            "https://api.groq.com/openai/v1/chat/completions", api_key, timeout=timeout
        )
