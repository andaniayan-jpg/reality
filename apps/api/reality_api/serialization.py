"""Stable JSON views of Reality package values; no geometry is reimplemented here."""

from __future__ import annotations

from typing import Any

from reality import Bounds, ModelPart, ModelResult, RealityModel


def bounds(value: Bounds) -> dict[str, list[float]]:
    return {"minimum": list(value.minimum), "maximum": list(value.maximum)}


def part(value: ModelPart) -> dict[str, Any]:
    return {
        "id": value.id,
        "name": value.name,
        "transform": {
            "position": list(value.transform.position),
            "rotation": list(value.transform.rotation),
            "scale": list(value.transform.scale),
        },
        "bounds": bounds(value.bounds),
        "volume": value.volume,
        "surface_area": value.surface_area,
        "center_of_mass": list(value.center_of_mass) if value.center_of_mass else None,
        "material": str(value.material) if value.material is not None else None,
        "topology": dict(value.topology()) if value.topology() is not None else None,
        "has_mesh": value.mesh is not None,
        "has_solid": value.solid is not None,
    }


def model_summary(model: RealityModel) -> dict[str, Any]:
    return {
        "format": model.format,
        "units": model.units,
        "bounds": bounds(model.bounds),
        "metadata": dict(model.metadata),
        "statistics": _json_safe(dict(model.statistics())),
        "validation": {
            "valid": model.validate().valid,
            "warnings": list(model.validate().warnings),
        },
        "assemblies": [
            {
                "id": assembly.id,
                "name": assembly.name,
                "part_ids": list(assembly.part_ids),
                "child_ids": list(assembly.child_ids),
                "parent_id": assembly.parent_id,
                "metadata": dict(assembly.metadata),
            }
            for assembly in model.assemblies
        ],
    }


def result(value: ModelResult[Any]) -> dict[str, Any]:
    return {
        "value": _json_safe(value.value),
        "measurement": value.measurement,
        "units": value.units,
        "tolerance": value.tolerance,
        "backend": value.backend,
        "reason": value.reason,
        "objects": [part(item) for item in value.objects],
        "evidence": _json_safe(dict(value.evidence)),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Bounds):
        return bounds(value)
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value
