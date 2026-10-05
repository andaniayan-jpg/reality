"""Evidence-bounded axial-yield screening for parsed physical objects."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Literal

import numpy as np
from scipy.spatial import ConvexHull, QhullError

from reality._core.router import ModelRouter
from reality._materials import material
from reality._physics_object import PhysicsObject
from reality._providers.base import AITask, AIUnavailableError

from .copilot import _default_router

_METRES_PER_UNIT = {"m": 1.0, "mm": 0.001, "cm": 0.01, "um": 0.000001, "in": 0.0254, "ft": 0.3048}
_LOAD_PATTERN = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(kg|kilograms?|kn|newtons?|n)\b", re.IGNORECASE
)
_STANDARD_GRAVITY = 9.80665


@dataclass(frozen=True, slots=True)
class Prediction:
    """A scoped axial-yield screen, or an insufficient-evidence result."""

    question: str
    outcome: Literal["unknown", "pass", "yield"]
    reason: str
    objects: tuple[PhysicsObject, ...]
    will_fail: bool | None = None
    failure_regions: tuple[str, ...] = ()
    safety_factor: float | None = None
    explanation: str = ""
    confidence: Literal["estimated", "insufficient_evidence"] = "insufficient_evidence"
    evidence: Mapping[str, object] = field(default_factory=dict)
    advisory: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    def __str__(self) -> str:
        return f"{self.outcome}: {self.explanation or self.reason}"


def predict(
    question: str,
    obj: PhysicsObject,
    *,
    load_axis: Literal["x", "y", "z"] | None = None,
    load_case: Literal["axial_tension", "axial_compression"] | None = None,
    support: Literal["opposed_face"] | None = None,
    yield_strength_pa: float | None = None,
    yield_source: str | None = None,
    force_newtons: float | None = None,
    use_ai: bool = False,
    router: ModelRouter | None = None,
) -> Prediction:
    """Screen a single closed mesh for pure axial yielding when inputs suffice.

    Cross-sections are sampled, not solved by FEA. Bending, buckling,
    fatigue, fracture, contacts and stress concentrations are out of scope.
    ``will_fail`` means this *axial yield screen* crosses its supplied strength,
    not that a design is certified safe or guaranteed to fracture.
    """
    if not question.strip():
        raise ValueError("question must not be empty")
    if not isinstance(obj, PhysicsObject):
        raise TypeError("predict expects a PhysicsObject from perceive.from_3d()")
    if force_newtons is not None and (not isfinite(force_newtons) or force_newtons <= 0):
        raise ValueError("force_newtons must be a positive finite number")
    spec = material(obj.material, yield_strength_pa=yield_strength_pa, source=yield_source)
    force, load_evidence = _force_from_prompt(question, force_newtons)
    missing: list[str] = []
    if force is None:
        missing.append("an unambiguous force in newtons or mass under standard gravity")
    if obj.units not in _METRES_PER_UNIT:
        missing.append("declared length units")
    if spec.yield_strength_pa is None:
        missing.append("grade-specific yield strength with its source")
    if load_axis is None:
        missing.append("load axis")
    if load_case is None:
        missing.append("axial tension/compression load case")
    if support is None:
        missing.append("opposed-face support assumption")
    if len(obj.parts) != 1 or obj.parts[0]._mesh is None or obj.watertight is not True:
        missing.append("a single watertight mesh part")

    sections: tuple[tuple[float, float], ...] | None = None
    if not missing and load_axis is not None:
        sections = _sample_convex_sections(obj, load_axis)
        if not sections:
            missing.append("convex, closed cross-sections along the load axis")
    if missing:
        reason = "Insufficient evidence: " + ", ".join(missing) + "."
        advisory = _advisory(question, obj, reason, router) if use_ai or router else None
        return Prediction(
            question=question,
            outcome="unknown",
            reason=reason,
            objects=(obj,),
            explanation=reason,
            evidence={"missing": tuple(missing), **load_evidence},
            advisory=advisory,
        )

    assert sections is not None and force is not None and spec.yield_strength_pa is not None
    assert load_case is not None and load_axis is not None
    minimum_position, minimum_area = min(sections, key=lambda sample: sample[1])
    stress = force / minimum_area
    safety_factor = spec.yield_strength_pa / stress
    will_yield = safety_factor < 1.0
    region = f"{obj.parts[0].name} near {load_axis}={minimum_position:.6g} m"
    explanation = (
        f"Under the specified pure {load_case.replace('_', ' ')} assumption, the sampled "
        f"minimum cross-section is {minimum_area:.6g} m² and nominal axial stress is "
        f"{stress:.6g} Pa. The supplied yield strength gives a sampled safety "
        f"factor of {safety_factor:.6g}. This is not FEA or a general failure verdict."
    )
    evidence: dict[str, object] = {
        **load_evidence,
        "force_newtons": force,
        "load_axis": load_axis,
        "load_case": load_case,
        "support": support,
        "minimum_cross_section_m2": minimum_area,
        "minimum_position_m": minimum_position,
        "sample_count": len(sections),
        "stress_pa": stress,
        "yield_strength_pa": spec.yield_strength_pa,
        "yield_source": spec.yield_source,
        "method": "sampled convex mesh sections; nominal pure axial stress",
        "not_evaluated": ("bending", "buckling", "fatigue", "fracture", "contacts"),
    }
    advisory = _advisory(question, obj, explanation, router) if use_ai or router else None
    if advisory:
        explanation += " Model commentary (unverified): " + advisory
    return Prediction(
        question=question,
        outcome="yield" if will_yield else "pass",
        reason=explanation,
        objects=(obj,),
        will_fail=will_yield,
        failure_regions=(region,) if will_yield else (),
        safety_factor=safety_factor,
        explanation=explanation,
        confidence="estimated",
        evidence=evidence,
        advisory=advisory,
    )


def _force_from_prompt(
    question: str, explicit_newtons: float | None
) -> tuple[float | None, dict[str, object]]:
    if explicit_newtons is not None:
        return explicit_newtons, {"load_source": "explicit force_newtons"}
    matches = _LOAD_PATTERN.findall(question)
    if len(matches) != 1:
        return None, {}
    number, unit = matches[0]
    value = float(number)
    if not isfinite(value) or value <= 0:
        return None, {}
    normalized = unit.lower()
    if normalized in {"kg", "kilogram", "kilograms"}:
        return value * _STANDARD_GRAVITY, {
            "load_source": "question mass converted to weight",
            "gravity_m_s2": _STANDARD_GRAVITY,
        }
    return value * (1000 if normalized == "kn" else 1), {"load_source": "question force"}


def _sample_convex_sections(
    obj: PhysicsObject, axis: Literal["x", "y", "z"]
) -> tuple[tuple[float, float], ...] | None:
    part = obj.parts[0]
    mesh = part._mesh.copy()
    mesh.apply_transform(part.transform.matrix)
    mesh.apply_scale(_METRES_PER_UNIT[obj.units])
    index = {"x": 0, "y": 1, "z": 2}[axis]
    low, high = mesh.bounds[:, index]
    if not isfinite(low) or not isfinite(high) or high <= low:
        return None
    normal = np.zeros(3)
    normal[index] = 1.0
    found: list[tuple[float, float]] = []
    for fraction in np.linspace(0.05, 0.95, 19):
        position = float(low + fraction * (high - low))
        origin = np.zeros(3)
        origin[index] = position
        section = mesh.section(plane_origin=origin, plane_normal=normal)
        if section is None:
            return None
        planar = section.to_2D()[0] if hasattr(section, "to_2D") else section.to_planar()[0]
        loops = planar.discrete
        if len(loops) != 1:
            return None  # Holes/disconnected sections need a robust polygon backend.
        vertices = np.asarray(loops[0], dtype=np.float64)
        if (
            len(vertices) < 4
            or not np.all(np.isfinite(vertices))
            or not np.allclose(vertices[0], vertices[-1], atol=1e-9)
        ):
            return None
        signed = np.dot(vertices[:-1, 0], vertices[1:, 1]) - np.dot(
            vertices[1:, 0], vertices[:-1, 1]
        )
        area = abs(float(signed)) * 0.5
        try:
            convex_area = float(ConvexHull(vertices[:-1]).volume)
        except QhullError:
            return None
        if area <= 0 or not np.isclose(area, convex_area, rtol=1e-5, atol=1e-12):
            return None
        found.append((position, area))
    return tuple(found)


def _advisory(
    question: str, obj: PhysicsObject, computed: str, router: ModelRouter | None
) -> str | None:
    try:
        selected = router or _default_router()
        prompt = (
            f"Question: {question}\nMeasured geometry: {obj.summary}\n"
            f"Computed or missing evidence: {computed}\n"
            "Explain limitations only. Do not change the numeric result or claim FEA."
        )
        return selected.route_feature("reason.predict", AITask(prompt=prompt)).text
    except AIUnavailableError:
        return None
