"""Deterministic primitive generation with optional advisory language input.

This module deliberately does not trust generated JSON as geometry code.  It
only accepts a small, validated primitive vocabulary and records constraints
that cannot be measured from the generated shape.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import trimesh

from reality._file_model import ModelAssembly, ModelPart, _model_from_parts
from reality._models import Bounds, Transform
from reality._physics_object import PhysicsObject, physics_object_from_model

_MATERIAL_DENSITY = {"steel": 7850.0, "aluminum": 2700.0, "aluminium": 2700.0, "wood": 700.0}


def _dimensions(prompt: str) -> tuple[float, float, float]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|met(?:re|er)s?)\b", prompt.lower())
    size = float(match.group(1)) if match else 1.0
    if not 0 < size <= 10_000:
        raise ValueError("primitive dimensions must be between 0 and 10,000 metres")
    return (size, size, size)


def object(prompt: str, constraints: Mapping[str, Any] | None = None) -> PhysicsObject:
    """Build a validated box, cylinder, or sphere from an explicit text request.

    Natural-language generation is intentionally bounded until an optional model
    can propose structured input that passes the exact same validation path.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    lowered = prompt.lower()
    dimensions = _dimensions(prompt)
    if "sphere" in lowered or "ball" in lowered:
        mesh = trimesh.creation.icosphere(radius=dimensions[0] / 2)
        geometry = "sphere"
    elif "cylinder" in lowered or "shaft" in lowered or "pipe" in lowered:
        mesh = trimesh.creation.cylinder(radius=dimensions[0] / 2, height=dimensions[2])
        geometry = "cylinder"
    else:
        mesh = trimesh.creation.box(extents=dimensions)
        geometry = "box"
    material = next((name for name in _MATERIAL_DENSITY if name in lowered), None)
    name = re.sub(r"\s+", " ", prompt.strip())[:80]
    part = ModelPart(
        name=name,
        id="generated-0",
        transform=Transform(),
        bounds=Bounds.from_points(mesh.bounds),
        _mesh=mesh,
        metadata={"generated": True, "primitive": geometry},
    )
    model = _model_from_parts(
        Path("<generated>"),
        "obj",
        "m",
        (part,),
        (ModelAssembly(name="generated", id="assembly-root", part_ids=(part.id,)),),
        {"generated": True, "generator": "validated-primitives"},
    )
    result = physics_object_from_model(
        model, units="m", density_kg_m3=_MATERIAL_DENSITY.get(material) if material else None
    )
    warnings: list[str] = []
    for key, value in (constraints or {}).items():
        if key == "max_mass_kg" and isinstance(value, int | float):
            if result.estimated_mass is None or result.estimated_mass > float(value):
                warnings.append(f"constraint max_mass_kg={value!r} is not satisfied")
        else:
            warnings.append(f"constraint {key!r} was not measurable for a {geometry}")
    return replace(
        result,
        material=material,
        material_source="name-heuristic" if material else "unknown",
        limitations=(
            *result.limitations,
            *warnings,
            "Generated geometry is a primitive approximation.",
        ),
        message="; ".join(warnings) if warnings else None,
    )
