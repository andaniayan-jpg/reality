"""Evidence-bounded failure-mode screens for parsed physical objects."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

import numpy as np
from scipy.spatial import ConvexHull, QhullError

from reality._core.router import ModelRouter
from reality._materials import material
from reality._physics_object import PhysicsObject
from reality._providers.base import AITask, AIUnavailableError, RetryableProviderError

from .copilot import _default_router

_METRES_PER_UNIT = {"m": 1.0, "mm": 0.001, "cm": 0.01, "um": 0.000001, "in": 0.0254, "ft": 0.3048}
_LOAD_PATTERN = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(kg|kilograms?|kn|newtons?|n)\b", re.IGNORECASE
)
_STANDARD_GRAVITY = 9.80665


@dataclass(frozen=True, slots=True)
class Prediction:
    """Independent geometry screens; no field is a general safety certificate."""

    question: str
    outcome: Literal["unknown", "partial", "pass", "yield"]
    reason: str
    objects: tuple[PhysicsObject, ...]
    will_fail: bool | None = None
    failure_regions: tuple[str, ...] = ()
    safety_factor: float | None = None
    explanation: str = ""
    confidence: Literal["estimated", "insufficient_evidence"] = "insufficient_evidence"
    evidence: Mapping[str, object] = field(default_factory=dict)
    advisory: str | None = None
    buckling_load: float | None = None
    buckling_risk: Literal["low", "medium", "high"] | None = None
    slender_members: tuple[str, ...] = ()
    max_bending_stress: float | None = None
    bending_location: str | None = None
    bending_risk: Literal["low", "medium", "high"] | None = None
    torsional_capacity: float | None = None
    applied_torque: float | None = None
    torsion_risk: Literal["low", "medium", "high"] | None = None
    joint_risks: Mapping[str, str] = field(default_factory=dict)
    weakest_joint: str | None = None
    fatigue_life_days: float | None = None
    missing_by_mode: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    mode_evidence: Mapping[str, object] = field(default_factory=dict)
    _stress_regions: tuple[tuple[tuple[float, float, float], float], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))
        object.__setattr__(self, "joint_risks", MappingProxyType(dict(self.joint_risks)))
        object.__setattr__(self, "missing_by_mode", MappingProxyType(dict(self.missing_by_mode)))
        object.__setattr__(self, "mode_evidence", MappingProxyType(dict(self.mode_evidence)))

    def __str__(self) -> str:
        return f"{self.outcome}: {self.explanation or self.reason}"

    @property
    def missing(self) -> tuple[str, ...]:
        """Distinct missing evidence across independent mode screens."""
        raw = self.evidence.get("missing", ())
        values = list(raw) if isinstance(raw, tuple | list) else []
        for mode_values in self.missing_by_mode.values():
            values.extend(mode_values)
        return tuple(dict.fromkeys(str(value) for value in values))

    def export_stress_map(self, path: str | Path) -> Path:
        """Export nominal axial screening colours; grey means unmeasured."""
        from ._stress_map import export_stress_map

        return export_stress_map(self, Path(path))


def _predict_axial(
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
    if not obj.supported:
        missing.append("supported parsed geometry")
    elif len(obj.parts) != 1 or obj.parts[0]._mesh is None or obj.watertight is not True:
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
    youngs_modulus_pa: float | None = None,
    span_m: float | None = None,
    bending_support: Literal["simply_supported"] | None = None,
    torque_nm: float | None = None,
    joint_areas_m2: Mapping[str, float] | None = None,
    joint_allowable_stress_pa: float | None = None,
    joint_forces_newtons: Mapping[str, float] | None = None,
    cycles_per_day: float | None = None,
    tensile_strength_pa: float | None = None,
    fatigue_reference_cycles: float | None = None,
) -> Prediction:
    """Run independent screens; legacy ``outcome`` retains its axial meaning."""
    if not isinstance(obj, PhysicsObject):
        raise TypeError("predict expects a PhysicsObject from perceive.from_3d()")
    effective_cycles = cycles_per_day if cycles_per_day is not None else obj.cycles_per_day
    for name, value in (
        ("youngs_modulus_pa", youngs_modulus_pa),
        ("span_m", span_m),
        ("torque_nm", torque_nm),
        ("joint_allowable_stress_pa", joint_allowable_stress_pa),
        ("cycles_per_day", effective_cycles),
        ("tensile_strength_pa", tensile_strength_pa),
        ("fatigue_reference_cycles", fatigue_reference_cycles),
    ):
        if value is not None and (not isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be positive and finite")
    for mapping_name, values in (
        ("joint_areas_m2", joint_areas_m2),
        ("joint_forces_newtons", joint_forces_newtons),
    ):
        if values is not None and any(
            not isfinite(value) or value <= 0 for value in values.values()
        ):
            raise ValueError(f"{mapping_name} must contain positive finite values")
    axial = _predict_axial(
        question,
        obj,
        load_axis=load_axis,
        load_case=load_case,
        support=support,
        yield_strength_pa=yield_strength_pa,
        yield_source=yield_source,
        force_newtons=force_newtons,
        use_ai=use_ai,
        router=router,
    )
    from ._failure_modes import screen_modes

    force, _ = _force_from_prompt(question, force_newtons)
    stress = axial.evidence.get("stress_pa")
    modes = screen_modes(
        obj,
        force_newtons=force,
        load_axis=load_axis,
        load_case=load_case,
        yield_strength_pa=yield_strength_pa,
        youngs_modulus_pa=youngs_modulus_pa,
        span_m=span_m,
        bending_support=bending_support,
        torque_nm=torque_nm,
        joint_areas_m2=joint_areas_m2,
        joint_allowable_stress_pa=joint_allowable_stress_pa,
        joint_forces_newtons=joint_forces_newtons,
        cycles_per_day=effective_cycles,
        tensile_strength_pa=tensile_strength_pa,
        axial_stress_pa=float(stress) if isinstance(stress, int | float) else None,
        fatigue_reference_cycles=fatigue_reference_cycles,
    )
    regions: list[tuple[tuple[float, float, float], float]] = []
    if axial.outcome != "unknown" and load_axis is not None and force is not None:
        sections = _sample_convex_sections(obj, load_axis)
        if sections and yield_strength_pa is not None:
            scale = _METRES_PER_UNIT[obj.units]
            center = np.asarray(obj.bounds.center) * scale
            index = "xyz".index(load_axis)
            for position, area in sections:
                location = center.copy()
                location[index] = position
                point = tuple(float(value) for value in location)
                regions.append(
                    (cast(tuple[float, float, float], point), force / area / yield_strength_pa)
                )
    available = any(
        value is not None
        for value in (
            modes.buckling_load,
            modes.max_bending_stress,
            modes.torsional_capacity,
            modes.fatigue_life_days,
        )
    ) or any(value != "insufficient_evidence" for value in modes.joint_risks.values())
    partial = axial.outcome == "unknown" and available
    partial_reason = (
        "Independent mode results are available; axial yield remains unassessed. " + axial.reason
        if partial
        else axial.reason
    )
    return replace(
        axial,
        outcome="partial" if partial else axial.outcome,
        reason=partial_reason,
        explanation=partial_reason if partial else axial.explanation,
        confidence="estimated" if partial else axial.confidence,
        buckling_load=modes.buckling_load,
        buckling_risk=modes.buckling_risk,
        slender_members=modes.slender_members,
        max_bending_stress=modes.max_bending_stress,
        bending_location=modes.bending_location,
        bending_risk=modes.bending_risk,
        torsional_capacity=modes.torsional_capacity,
        applied_torque=modes.applied_torque,
        torsion_risk=modes.torsion_risk,
        joint_risks=modes.joint_risks,
        weakest_joint=modes.weakest_joint,
        fatigue_life_days=modes.fatigue_life_days,
        missing_by_mode=modes.missing_by_mode,
        mode_evidence=modes.mode_evidence,
        _stress_regions=tuple(regions),
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
    except (AIUnavailableError, RetryableProviderError):
        return None


@dataclass(frozen=True, slots=True)
class WhatIfResult:
    """Two independently computed screens over copy-on-write alternatives."""

    original: Prediction
    modified: Prediction
    changes_applied: Mapping[str, object]
    safety_factor_delta: float | None
    recommendation: str
    better: bool | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "changes_applied", MappingProxyType(dict(self.changes_applied)))


@dataclass(frozen=True, slots=True)
class CapacityResult:
    max_load: float | None
    limiting_mode: Literal["yield", "buckling", "bending", "joint"] | None
    explanation: str
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WeakestResult:
    weakest_component: str | None
    failure_mode: str | None
    safety_factor: float | None
    explanation: str


@dataclass(frozen=True, slots=True)
class ReasonAnswer:
    route: Literal["predict", "what_if", "capacity", "weakest", "facts"]
    structured: Prediction | WhatIfResult | CapacityResult | WeakestResult | None
    explanation: str


def _optional_ollama(prompt: str, router: ModelRouter | None) -> str | None:
    """Try an installed local model briefly; never let it change numeric results."""
    try:
        if router is None:
            from reality._providers.ollama import OllamaProvider

            local = OllamaProvider(timeout=1.0)
            models = local.available_models()
            if not models:
                return None
            local.timeout = 20.0
            router = ModelRouter({"local": local}, local_models=models)
        return router.route_feature(
            "reason.predict",
            AITask(
                prompt=prompt + "\nExplain evidence and uncertainty. Never alter computed numbers."
            ),
        ).text
    except (AIUnavailableError, RetryableProviderError):
        return None


def what_if(
    obj: PhysicsObject,
    changes: Mapping[str, object],
    question: str,
    *,
    router: ModelRouter | None = None,
    **predict_inputs: object,
) -> WhatIfResult:
    """Evaluate a copy-on-write alternative; numeric loads are newtons."""
    if not isinstance(obj, PhysicsObject):
        raise TypeError("what_if expects a PhysicsObject")
    if not question.strip():
        raise ValueError("question must not be empty")
    unsupported = set(changes) - {"material", "wall_thickness", "load"}
    if unsupported:
        raise ValueError(f"unsupported what-if changes: {', '.join(sorted(unsupported))}")
    kwargs = dict(predict_inputs)
    original = predict(question, obj, **kwargs)  # type: ignore[arg-type]
    draft = obj.modify
    applied: dict[str, object] = {}
    if "material" in changes:
        name = changes["material"]
        if not isinstance(name, str):
            raise TypeError("material override must be a name")
        if name != obj.material:
            draft.material(name)
            applied["material"] = name
    if "wall_thickness" in changes:
        wall = changes["wall_thickness"]
        if not isinstance(wall, int | float):
            raise TypeError("wall_thickness must be numeric in source units")
        draft.hollow(wall_thickness=float(wall))
        if draft.result.model is not None and draft.result.model.metadata.get("geometry_changed"):
            applied["wall_thickness"] = float(wall)
    alternate = draft.result if draft.change_log else obj
    if "load" in changes:
        load = changes["load"]
        if not isinstance(load, int | float) or not isfinite(load) or load <= 0:
            raise ValueError("load override must be positive newtons")
        kwargs["force_newtons"] = float(load)
        applied["load"] = float(load)
    if "material" in applied:
        # Strength/modulus supplied for the original material cannot be
        # transferred to a different grade by changing only a name.
        for property_name in (
            "yield_strength_pa",
            "yield_source",
            "youngs_modulus_pa",
            "tensile_strength_pa",
        ):
            kwargs.pop(property_name, None)
    modified = predict(question, alternate, **kwargs)  # type: ignore[arg-type]
    delta = (
        modified.safety_factor - original.safety_factor
        if modified.safety_factor is not None and original.safety_factor is not None
        else None
    )
    better = (delta > 0) if delta is not None else None
    original_text = (
        f"{original.safety_factor:.6g}" if original.safety_factor is not None else "unavailable"
    )
    modified_text = (
        f"{modified.safety_factor:.6g}" if modified.safety_factor is not None else "unavailable"
    )
    delta_text = f"{delta:+.6g}" if delta is not None else "unavailable"
    fallback = (
        f"Original safety factor: {original_text}. Modified safety factor: "
        f"{modified_text}. Delta: {delta_text}. No structural certification is implied."
    )
    advisory = _optional_ollama(
        f"Question: {question}\nOriginal screen: {original.reason}\n"
        f"Modified screen: {modified.reason}\nMeasured comparison: {fallback}",
        router,
    )
    return WhatIfResult(original, modified, applied, delta, advisory or fallback, better)


def capacity(
    obj: PhysicsObject,
    *,
    load_axis: Literal["x", "y", "z"] | None = None,
    load_case: Literal["axial_tension", "axial_compression"] | None = None,
    support: Literal["opposed_face"] | None = None,
    yield_strength_pa: float | None = None,
    yield_source: str | None = None,
    youngs_modulus_pa: float | None = None,
    span_m: float | None = None,
    bending_support: Literal["simply_supported"] | None = None,
    joint_areas_m2: Mapping[str, float] | None = None,
    joint_allowable_stress_pa: float | None = None,
) -> CapacityResult:
    """Minimum nominal load among modes with enough evidence; never a safe working load."""
    material(obj.material, yield_strength_pa=yield_strength_pa, source=yield_source)
    for name, value in (
        ("youngs_modulus_pa", youngs_modulus_pa),
        ("span_m", span_m),
        ("joint_allowable_stress_pa", joint_allowable_stress_pa),
    ):
        if value is not None and (not isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be positive and finite")
    if joint_areas_m2 is not None and any(
        not isfinite(value) or value <= 0 for value in joint_areas_m2.values()
    ):
        raise ValueError("joint_areas_m2 must contain positive finite areas")
    candidates: dict[Literal["yield", "buckling", "bending", "joint"], float] = {}
    if (
        yield_strength_pa is not None
        and yield_source
        and load_axis is not None
        and load_case is not None
        and support == "opposed_face"
        and obj.model is not None
        and len(obj.parts) == 1
        and obj.units in _METRES_PER_UNIT
    ):
        sections = _sample_convex_sections(obj, load_axis)
        if sections:
            candidates["yield"] = yield_strength_pa * min(area for _, area in sections)
    from ._failure_modes import _METRES, _section, screen_modes

    modes = screen_modes(
        obj,
        force_newtons=None,
        load_axis=load_axis,
        load_case=load_case,
        yield_strength_pa=yield_strength_pa,
        youngs_modulus_pa=youngs_modulus_pa,
        span_m=span_m,
        bending_support=bending_support,
        torque_nm=None,
        joint_areas_m2=None,
        joint_allowable_stress_pa=None,
        joint_forces_newtons=None,
        cycles_per_day=None,
        tensile_strength_pa=None,
        axial_stress_pa=None,
        fatigue_reference_cycles=None,
    )
    if (
        load_case == "axial_compression"
        and youngs_modulus_pa is not None
        and modes.buckling_load is not None
    ):
        candidates["buckling"] = modes.buckling_load
    if (
        yield_strength_pa is not None
        and yield_source
        and span_m is not None
        and span_m > 0
        and bending_support == "simply_supported"
        and obj.model is not None
        and obj.units in _METRES
    ):
        beam_sections = [
            section
            for part in obj.parts
            if (section := _section(part, _METRES[obj.units])) is not None
            and span_m <= section.length_m * (1 + 1e-6)
        ]
        if beam_sections:
            candidates["bending"] = min(
                4
                * yield_strength_pa
                * section.minimum_inertia_m4
                / (span_m * section.extreme_fibre_m)
                for section in beam_sections
            )
    from reality._physics_object import PhysicsScene

    if isinstance(obj, PhysicsScene) and joint_areas_m2 and joint_allowable_stress_pa is not None:
        areas = [joint_areas_m2[joint.name] for joint in obj.joints if joint.name in joint_areas_m2]
        if areas:
            candidates["joint"] = min(areas) * joint_allowable_stress_pa
    if not candidates:
        return CapacityResult(
            None,
            None,
            "Insufficient evidence for a load capacity: provide a load axis/case, "
            "supports and source-backed material strength as applicable.",
        )
    mode = min(candidates, key=candidates.__getitem__)
    return CapacityResult(
        candidates[mode],
        mode,
        f"Nominal {mode} screening threshold is {candidates[mode]:.6g} N under stated "
        "assumptions; this is not a rated or safe working load.",
        evidence={str(name): value for name, value in candidates.items()},
    )


def weakest(
    obj: PhysicsObject,
    *,
    load_axis: Literal["x", "y", "z"] | None = None,
    load_case: Literal["axial_tension", "axial_compression"] | None = None,
    support: Literal["opposed_face"] | None = None,
    yield_strength_pa: float | None = None,
    yield_source: str | None = None,
    force_newtons: float | None = None,
    youngs_modulus_pa: float | None = None,
    span_m: float | None = None,
    bending_support: Literal["simply_supported"] | None = None,
    torque_nm: float | None = None,
    joint_areas_m2: Mapping[str, float] | None = None,
    joint_allowable_stress_pa: float | None = None,
    joint_forces_newtons: Mapping[str, float] | None = None,
) -> WeakestResult:
    """Rank comparable, evidenced safety factors across available modes."""
    from reality._physics_object import PhysicsScene

    for name, value in (("force_newtons", force_newtons), ("torque_nm", torque_nm)):
        if value is not None and (not isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be positive and finite")
    if obj.model is None:
        return WeakestResult(None, None, None, "Geometry is unavailable for component ranking.")
    components = obj.objects if isinstance(obj, PhysicsScene) else (obj,)
    candidates: list[tuple[float, str, str]] = []
    for component in components:
        report = predict(
            "component failure screen",
            component,
            load_axis=load_axis,
            load_case=load_case,
            support=support,
            yield_strength_pa=yield_strength_pa,
            yield_source=yield_source,
            force_newtons=force_newtons,
            youngs_modulus_pa=youngs_modulus_pa,
            span_m=span_m,
            bending_support=bending_support,
            torque_nm=torque_nm,
        )
        name = component.parts[0].name
        if report.safety_factor is not None:
            candidates.append((report.safety_factor, name, "yield"))
        if report.buckling_load is not None and force_newtons and youngs_modulus_pa:
            candidates.append((report.buckling_load / force_newtons, name, "buckling"))
        if report.max_bending_stress is not None and yield_strength_pa is not None:
            candidates.append((yield_strength_pa / report.max_bending_stress, name, "bending"))
        if report.torsional_capacity is not None and torque_nm is not None:
            candidates.append((report.torsional_capacity / torque_nm, name, "torsion"))
    if isinstance(obj, PhysicsScene) and joint_areas_m2 and joint_allowable_stress_pa:
        joint_report = predict(
            "joint failure screen",
            obj,
            force_newtons=force_newtons,
            load_axis=load_axis,
            load_case=load_case,
            joint_areas_m2=joint_areas_m2,
            joint_allowable_stress_pa=joint_allowable_stress_pa,
            joint_forces_newtons=joint_forces_newtons,
        )
        fractions = joint_report.mode_evidence.get("joint_fractions")
        if isinstance(fractions, Mapping):
            for joint in obj.joints:
                fraction = fractions.get(joint.name)
                if isinstance(fraction, int | float) and fraction > 0:
                    candidates.append((1.0 / fraction, joint.child, "joint"))
    if not candidates:
        return WeakestResult(
            None,
            None,
            None,
            "No comparable loaded failure screens are available; the weakest part "
            "cannot be determined from geometry alone.",
        )
    safety, name, mode = min(candidates)
    return WeakestResult(
        name,
        mode,
        safety,
        f"{name} has the lowest available nominal {mode} safety ratio ({safety:.6g}). "
        "Other failure modes may govern.",
    )


def ask(
    obj: PhysicsObject,
    question: str,
    *,
    router: ModelRouter | None = None,
    **predict_inputs: object,
) -> ReasonAnswer:
    """Route common physical questions to computations; otherwise return facts."""
    if not isinstance(obj, PhysicsObject):
        raise TypeError("ask expects a PhysicsObject")
    if not question.strip():
        raise ValueError("question must not be empty")
    lowered = question.lower()
    structured: Prediction | WhatIfResult | CapacityResult | WeakestResult | None
    route: Literal["predict", "what_if", "capacity", "weakest", "facts"]
    if "what if" in lowered:
        changes: dict[str, object] = {}
        for label in ("aluminium", "aluminum", "steel"):
            if re.search(rf"\b{label}\b", lowered):
                changes["material"] = label
                break
        load, _ = _force_from_prompt(question, None)
        if load is not None:
            changes["load"] = load
        structured = what_if(obj, changes, question, router=router, **predict_inputs)
        route = "what_if"
        fallback = structured.recommendation
    elif any(marker in lowered for marker in ("will it fail", "will this fail", "fail under")):
        structured = predict(question, obj, **predict_inputs)  # type: ignore[arg-type]
        route = "predict"
        fallback = structured.reason
    elif "how much load" in lowered or "capacity" in lowered:
        allowed = {
            key: value
            for key, value in predict_inputs.items()
            if key
            in {
                "load_axis",
                "load_case",
                "support",
                "yield_strength_pa",
                "yield_source",
                "youngs_modulus_pa",
                "span_m",
                "bending_support",
                "joint_areas_m2",
                "joint_allowable_stress_pa",
            }
        }
        structured = capacity(obj, **allowed)  # type: ignore[arg-type]
        route = "capacity"
        fallback = structured.explanation
    elif "which part" in lowered or "weakest" in lowered:
        allowed = {
            key: value
            for key, value in predict_inputs.items()
            if key
            in {
                "load_axis",
                "load_case",
                "support",
                "yield_strength_pa",
                "yield_source",
                "force_newtons",
                "youngs_modulus_pa",
                "span_m",
                "bending_support",
                "torque_nm",
                "joint_areas_m2",
                "joint_allowable_stress_pa",
                "joint_forces_newtons",
            }
        }
        structured = weakest(obj, **allowed)  # type: ignore[arg-type]
        route = "weakest"
        fallback = structured.explanation
    else:
        structured = None
        route = "facts"
        fallback = obj.summary + " Limits: " + "; ".join(obj.limitations)
    advisory = _optional_ollama(
        f"Question: {question}\nMeasured object facts: {obj.summary}\n"
        f"Computed result or factual fallback: {fallback}",
        router,
    )
    return ReasonAnswer(
        route,
        structured,
        advisory
        or (f"AI unavailable. Computed result: {fallback}" if route != "facts" else fallback),
    )
