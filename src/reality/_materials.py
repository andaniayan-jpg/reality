"""Material labels and explicitly supplied engineering properties.

Names and render materials do not identify a grade or certify yield strength.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

_NOMINAL_DENSITY = {"steel": 7850.0, "aluminum": 2700.0, "aluminium": 2700.0}


@dataclass(frozen=True, slots=True)
class MaterialProperties:
    name: str
    density_kg_m3: float | None
    yield_strength_pa: float | None
    yield_source: str | None
    density_source: str | None


def material(
    name: str | None,
    *,
    yield_strength_pa: float | None = None,
    density_kg_m3: float | None = None,
    source: str | None = None,
) -> MaterialProperties:
    """Return a material label with only defensible numeric properties.

    Generic material names provide a nominal density estimate, never an assumed
    yield strength. A caller must supply grade-specific strength and its source.
    """
    label = (name or "unknown").strip() or "unknown"
    for value, field in (
        (yield_strength_pa, "yield_strength_pa"),
        (density_kg_m3, "density_kg_m3"),
    ):
        if value is not None and (not isfinite(value) or value <= 0):
            raise ValueError(f"{field} must be a positive finite number")
    if yield_strength_pa is not None and not source:
        raise ValueError("a source is required for an explicit yield strength")
    nominal = _NOMINAL_DENSITY.get(label.lower())
    return MaterialProperties(
        name=label,
        density_kg_m3=density_kg_m3 if density_kg_m3 is not None else nominal,
        yield_strength_pa=yield_strength_pa,
        yield_source=source if yield_strength_pa is not None else None,
        density_source=(
            source
            if density_kg_m3 is not None
            else "nominal generic-material estimate"
            if nominal is not None
            else None
        ),
    )
