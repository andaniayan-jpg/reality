"""Image question answering over a supplied image, not inferred CAD topology."""

from __future__ import annotations

from pathlib import Path

from reality._core.router import ModelRouter
from reality._providers.base import AIResponse, AITask

from .copilot import _default_router

MAX_IMAGE_BYTES = 20 * 1024 * 1024


def from_image(
    path: str | Path,
    *,
    prompt: str = "Describe only what is visibly supported by this image.",
    router: ModelRouter | None = None,
) -> AIResponse:
    """Submit a JPEG/PNG/WebP image to an installed vision-capable model."""
    source = Path(path)
    if source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("supported image formats: JPG, PNG, WebP")
    if source.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds the 20 MiB limit")
    image = source.read_bytes()
    if not image:
        raise ValueError("image is empty")
    suffix = source.suffix.lower()
    matches = (
        image.startswith(b"\x89PNG\r\n\x1a\n")
        if suffix == ".png"
        else image.startswith(b"\xff\xd8\xff")
        if suffix in {".jpg", ".jpeg"}
        else image.startswith(b"RIFF") and image[8:12] == b"WEBP"
    )
    if not matches:
        raise ValueError("image content does not match its extension")
    return (router or _default_router()).route(AITask(prompt=prompt, kind="vision", image=image))
