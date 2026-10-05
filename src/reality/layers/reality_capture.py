"""File-based image capture; no webcam or live frame access."""

from __future__ import annotations

from pathlib import Path

from reality._core.router import ModelRouter
from reality._providers.base import AIResponse

from .perceive import from_image


def capture(
    *,
    source: str | Path,
    prompt: str = "Describe visible scene objects and uncertainty; do not infer exact physics.",
    router: ModelRouter | None = None,
) -> AIResponse:
    """Analyze a user-supplied image file; this does not construct measured geometry."""
    return from_image(source, prompt=prompt, router=router)
