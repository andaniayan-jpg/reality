"""Independent, evidence-gated engineering screens; not FEA or certification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import pi, sqrt
from typing import Literal, cast

import numpy as np
import trimesh

from reality._file_model import ModelPart
from reality._physics_object import PhysicsObject, PhysicsScene

Risk = Literal["low", "medium", "high"]
_METRES = {"m": 1.0, "mm": 0.001, "cm": 0.01, "um": 0.000001, "in": 0.0254, "ft": 0.3048}
_NOMINAL_E = {"steel": 200e9, "aluminum": 69e9, "aluminium": 69e9}


@dataclass(frozen=True, slots=True)
class Section:
    part_name: str
    axis: Literal["x", "y", "z"]
    length_m: float
    area_m2: float
    minimum_inertia_m4: float
    polar_inertia_m4: float
    radius_m: float
    extreme_fibre_m: float
    circularity: float
    center_m: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class ModeScreens:
    buckling_load: float | None = None
    buckling_risk: Risk | None = None
    slender_members: tuple[str, ...] = ()
    max_bending_stress: float | None = None
    bending_location: str | None = None
    bending_risk: Risk | None = None
    torsional_capacity: float | None = None
    applied_torque: float | None = None
    torsion_risk: Risk | None = None
    joint_risks: Mapping[str, str] = field(default_factory=dict)
    weakest_joint: str | None = None
    fatigue_life_days: float | None = None
    missing_by_mode: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    mode_evidence: Mapping[str, object] = field(default_factory=dict)


def _risk(fraction: float) -> Risk:
    if fraction >= 0.8:
        return "high"
    if fraction >= 0.5:
        return "medium"
    return "low"


def _section(part: ModelPart, scale: float) -> Section | None:
    """Measure one midspan polygon; holes and disconnected loops are unsupported."""
    if part._mesh is None or part.solid is not None:
        return None
    mesh = cast(trimesh.Trimesh, part._mesh).copy()
    mesh.apply_transform(part.transform.matrix)
    mesh.apply_scale(scale)
    if not mesh.is_volume:
        return None
    index = int(np.argmax(mesh.extents))
    length = float(mesh.extents[index])
    if length <= 0:
        return None
    center = np.asarray(mesh.bounds, dtype=float).mean(axis=0)
    normal = np.eye(3)[index]
    sliced = mesh.section(plane_origin=center, plane_normal=normal)
    if sliced is None:
        return None
    planar = sliced.to_2D()[0] if hasattr(sliced, "to_2D") else sliced.to_planar()[0]
    loops = planar.discrete
    if len(loops) != 1:
        return None
    vertices = np.asarray(loops[0], dtype=float)
    if len(vertices) < 4 or not np.allclose(vertices[0], vertices[-1], atol=1e-8):
        return None
    x, y = vertices[:-1, 0], vertices[:-1, 1]
    x_next, y_next = vertices[1:, 0], vertices[1:, 1]
    cross = x * y_next - x_next * y
    signed_area = float(np.sum(cross) / 2)
    if abs(signed_area) <= 1e-15:
        return None
    sign = 1 if signed_area > 0 else -1
    area = abs(signed_area)
    centroid_x = float(np.sum((x + x_next) * cross) / (6 * signed_area))
    centroid_y = float(np.sum((y + y_next) * cross) / (6 * signed_area))
    ixx = sign * float(np.sum((y * y + y * y_next + y_next * y_next) * cross) / 12)
    iyy = sign * float(np.sum((x * x + x * x_next + x_next * x_next) * cross) / 12)
    ixy = sign * float(
        np.sum((2 * x * y + x * y_next + x_next * y + 2 * x_next * y_next) * cross) / 24
    )
    ixx -= area * centroid_y**2
    iyy -= area * centroid_x**2
    ixy -= area * centroid_x * centroid_y
    principal = np.linalg.eigvalsh(np.asarray(((ixx, -ixy), (-ixy, iyy))))
    if principal[0] <= 0 or not np.all(np.isfinite(principal)):
        return None
    radii = np.hypot(x - centroid_x, y - centroid_y)
    radius = float(np.max(radii))
    if radius <= 0:
        return None
    circularity = max(
        float(np.std(radii) / np.mean(radii)),
        abs(1.0 - area / (pi * radius**2)),
    )
    return Section(
        part.name,
        cast(Literal["x", "y", "z"], "xyz"[index]),
        length,
        area,
        float(principal[0]),
        float(ixx + iyy),
        radius,
        radius,  # conservative extreme-fibre distance for any in-plane axis
        circularity,
        cast(tuple[float, float, float], tuple(float(value) for value in center)),
    )


def screen_modes(
    obj: PhysicsObject,
    *,
    force_newtons: float | None,
    load_axis: str | None,
    load_case: str | None,
    yield_strength_pa: float | None,
    youngs_modulus_pa: float | None,
    span_m: float | None,
    bending_support: str | None,
    torque_nm: float | None,
    joint_areas_m2: Mapping[str, float] | None,
    joint_allowable_stress_pa: float | None,
    joint_forces_newtons: Mapping[str, float] | None,
    cycles_per_day: float | None,
    tensile_strength_pa: float | None,
    axial_stress_pa: float | None,
    fatigue_reference_cycles: float | None,
) -> ModeScreens:
    """Run each screen independently and record missing inputs per mode."""
    missing: dict[str, tuple[str, ...]] = {}
    evidence: dict[str, object] = {}
    if obj.model is None or not obj.supported or obj.units not in _METRES:
        sections: list[Section] = []
    else:
        sections = [
            item for part in obj.parts if (item := _section(part, _METRES[obj.units])) is not None
        ]
    slender = [section for section in sections if section.length_m / section.radius_m > 10]
    buckling_load: float | None = None
    buckling_risk: Risk | None = None
    if slender:
        label = (obj.material or "").lower()
        modulus = youngs_modulus_pa or _NOMINAL_E.get(label, 200e9)
        capacities = {
            section.part_name: pi**2 * modulus * section.minimum_inertia_m4 / section.length_m**2
            for section in slender
        }
        buckling_load = min(capacities.values())
        evidence["buckling"] = {
            "effective_length": "pin-pin L (assumed; verify end restraints)",
            "modulus_pa": modulus,
            "modulus_source": "explicit" if youngs_modulus_pa is not None else "nominal assumption",
            "member_capacities_n": capacities,
            "method": "Euler ideal-column midspan-section screen; imperfections excluded",
        }
        if force_newtons is not None and load_case == "axial_compression":
            buckling_risk = _risk(force_newtons / buckling_load)
        else:
            missing["buckling"] = ("compressive force and axial_compression load case",)
    else:
        missing["buckling"] = ("slender closed member with known units and one section loop",)

    bending_stress: float | None = None
    bending_location: str | None = None
    bending_risk: Risk | None = None
    bending_inputs: list[str] = []
    if not sections:
        bending_inputs.append("closed spanning member with known units")
    if force_newtons is None:
        bending_inputs.append("force")
    if span_m is None or span_m <= 0:
        bending_inputs.append("positive span_m")
    if bending_support != "simply_supported":
        bending_inputs.append("simply_supported bending_support")
    if (
        not bending_inputs
        and span_m is not None
        and span_m > max(section.length_m for section in sections) * (1 + 1e-6)
    ):
        bending_inputs.append("span_m must not exceed measured member length")
    if not bending_inputs:
        section = max(sections, key=lambda value: value.length_m)
        assert force_newtons is not None and span_m is not None
        moment = force_newtons * span_m / 4  # central point load, explicit model assumption
        bending_stress = moment * section.extreme_fibre_m / section.minimum_inertia_m4
        bending_location = f"{section.part_name} at midspan"
        if yield_strength_pa is not None:
            bending_risk = _risk(bending_stress / yield_strength_pa)
        else:
            missing["bending"] = ("yield strength for risk classification",)
        evidence["bending"] = {
            "moment_nm": moment,
            "span_m": span_m,
            "section_inertia_m4": section.minimum_inertia_m4,
            "assumption": "simply supported central point load",
        }
    else:
        missing["bending"] = tuple(bending_inputs)

    shafts = [
        section
        for section in sections
        if section.circularity < 0.1 and section.length_m > 6 * section.radius_m
    ]
    torsional_capacity: float | None = None
    torsion_risk: Risk | None = None
    if not shafts:
        missing["torsion"] = ("closed shaft-like circular section with known units",)
    elif yield_strength_pa is None:
        missing["torsion"] = ("grade-specific yield strength for shear capacity",)
    else:
        capacities = {
            section.part_name: yield_strength_pa
            / sqrt(3)
            * section.polar_inertia_m4
            / section.radius_m
            for section in shafts
        }
        torsional_capacity = min(capacities.values())
        evidence["torsion"] = {
            "shaft_capacities_nm": capacities,
            "shear_yield": "von Mises yield / sqrt(3) assumption",
            "method": "solid midspan polygon polar moment; warping ignored",
        }
        if torque_nm is not None:
            torsion_risk = _risk(torque_nm / torsional_capacity)
        else:
            missing["torsion"] = ("applied torque for risk classification",)

    joint_risks: dict[str, str] = {}
    weakest_joint: str | None = None
    joint_fractions: dict[str, float] = {}
    if isinstance(obj, PhysicsScene) and obj.model is not None:
        for joint in obj.joints:
            area = joint_areas_m2.get(joint.name) if joint_areas_m2 else None
            joint_force = joint_forces_newtons.get(joint.name) if joint_forces_newtons else None
            if (
                joint_force is None
                and force_newtons is not None
                and load_case == "axial_compression"
                and load_axis == "z"
            ):
                child = next(
                    (
                        component
                        for component in obj.objects
                        if any(
                            part.metadata.get("source_link") == joint.child
                            for part in component.parts
                        )
                    ),
                    None,
                )
                if child is not None and child.estimated_mass is not None:
                    joint_force = force_newtons + child.estimated_mass * 9.80665
                    evidence[f"joint_load_{joint.name}"] = (
                        "external force plus direct child weight; vertical worst-case screen"
                    )
            if (
                area is None
                or area <= 0
                or joint_allowable_stress_pa is None
                or joint_force is None
            ):
                joint_risks[joint.name] = "insufficient_evidence"
                continue
            fraction = joint_force / (area * joint_allowable_stress_pa)
            joint_fractions[joint.name] = fraction
            joint_risks[joint.name] = _risk(fraction)
        if joint_fractions:
            weakest_joint = max(joint_fractions, key=joint_fractions.__getitem__)
            evidence["joint_fractions"] = dict(joint_fractions)
        if any(value == "insufficient_evidence" for value in joint_risks.values()):
            missing["joint"] = ("joint area, allowable stress and transferred load per joint",)
    else:
        missing["joint"] = ("PhysicsScene with declared joints",)

    fatigue_life_days: float | None = None
    fatigue_missing: list[str] = []
    if cycles_per_day is None:
        fatigue_missing.append("cycles_per_day")
    if tensile_strength_pa is None:
        fatigue_missing.append("tensile_strength_pa")
    if fatigue_reference_cycles is None:
        fatigue_missing.append("fatigue_reference_cycles")
    if axial_stress_pa is None:
        fatigue_missing.append("applied nominal stress")
    if not fatigue_missing:
        assert cycles_per_day is not None and tensile_strength_pa is not None
        assert axial_stress_pa is not None and fatigue_reference_cycles is not None
        fatigue_life_days = (
            (0.5 * tensile_strength_pa / axial_stress_pa) ** 0.1
            * fatigue_reference_cycles
            / cycles_per_day
        )
        evidence["fatigue"] = {
            "reference_cycles": fatigue_reference_cycles,
            "method": "illustrative supplied S-N approximation, not measured fatigue life",
        }
    else:
        missing["fatigue"] = tuple(fatigue_missing)
    return ModeScreens(
        buckling_load=buckling_load,
        buckling_risk=buckling_risk,
        slender_members=tuple(section.part_name for section in slender),
        max_bending_stress=bending_stress,
        bending_location=bending_location,
        bending_risk=bending_risk,
        torsional_capacity=torsional_capacity,
        applied_torque=torque_nm,
        torsion_risk=torsion_risk,
        joint_risks=joint_risks,
        weakest_joint=weakest_joint,
        fatigue_life_days=fatigue_life_days,
        missing_by_mode=missing,
        mode_evidence=evidence,
    )
