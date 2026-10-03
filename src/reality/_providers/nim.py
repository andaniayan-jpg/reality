"""NVIDIA NIM adapter; deployment must configure an actually available model."""

from __future__ import annotations

from .openai_compatible import ChatCompletionsProvider


class NIMProvider(ChatCompletionsProvider):
    def __init__(self, api_key: str, *, timeout: float = 60.0) -> None:
        super().__init__(
            "https://integrate.api.nvidia.com/v1/chat/completions", api_key, timeout=timeout
        )
