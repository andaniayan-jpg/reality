"""Provider-neutral request and response contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

MAX_CLOUD_IMAGE_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_TOKENS = 1024

SYSTEM_GUIDANCE = (
    "Give general guidance only. Never claim to have measured geometry, run a "
    "physics simulation, or verified an edit unless the request includes "
    "authoritative Reality tool evidence. State uncertainty plainly."
)


class AIUnavailableError(RuntimeError):
    """No usable inference path is currently available."""


class RetryableProviderError(RuntimeError):
    """Capacity, timeout, or transient upstream failure eligible for fallback."""


@dataclass(frozen=True, slots=True)
class AITask:
    prompt: str
    kind: Literal["text", "vision"] = "text"
    complexity: Literal["fast", "deep", "agent"] = "fast"
    realtime: bool = False
    image: bytes | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt must not be empty")
        if self.kind == "vision" and not self.image:
            raise ValueError("vision tasks require an image")


@dataclass(frozen=True, slots=True)
class AIResponse:
    """Model text, not a measured or simulated physical-world result."""

    text: str
    mode: Literal["local", "online"]

    def __str__(self) -> str:
        return self.text


class Provider(Protocol):
    """Advanced users may register any implementation of this interface."""

    def complete(self, task: AITask, *, model: str) -> str: ...
