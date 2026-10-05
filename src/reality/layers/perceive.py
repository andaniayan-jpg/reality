"""File-based image perception and deterministic 3D physical interpretation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from reality._core.auth import detect_mode
from reality._core.router import ModelRouter
from reality._file_model import open_model
from reality._physics_object import PhysicsObject, physics_object_from_model
from reality._providers.base import AIResponse, AITask

from .copilot import _default_router

MAX_IMAGE_BYTES = 20 * 1024 * 1024


def from_3d(
    path: str | Path,
    *,
    units: str | None = None,
    density_kg_m3: float | None = None,
    max_bytes: int = 512 * 1024 * 1024,
    enrich: bool = False,
    router: ModelRouter | None = None,
) -> PhysicsObject:
    """Read a 3D/CAD file into a measured, uncertainty-aware physical object.

    Meshes use the existing Trimesh importer; STEP/STP keep their original B-reps
    through the optional CAD backend. No LLM is needed for geometry. ``enrich``
    adds advisory model text, never overwriting measured fields. OBJ/STL/PLY
    usually need an explicit ``units`` value for a meaningful mass estimate.
    """
    model = open_model(path, max_bytes=max_bytes)
    obj = physics_object_from_model(model, units=units, density_kg_m3=density_kg_m3)
    if not enrich:
        return obj
    selected = router or _default_router()
    prompt = (
        "Explain this 3D object's possible material and design concerns as hypotheses only. "
        "Do not invent loads, stress, joints, exact materials, or numerical measurements. "
        f"Authoritative geometry summary: {obj.summary} "
        f"Source part names: {[part.name for part in model.parts]}. "
        f"Known limitations: {obj.limitations}"
    )
    response = selected.route_feature("reason.predict", AITask(prompt=prompt))
    return replace(obj, ai_notes=response.text)


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
    selected = router or _default_router()
    task = AITask(prompt=prompt, kind="vision", image=image)
    if router is not None or detect_mode() == "online":
        return selected.route(task)
    return selected.route_feature("perceive.from_image", task)
