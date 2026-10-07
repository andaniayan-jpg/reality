"""OBJ colours for nominal measured stress ratios, never a simulated FEA field."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
import trimesh
from scipy.spatial import KDTree

if TYPE_CHECKING:
    from .reason import Prediction

_METRES = {"m": 1.0, "mm": 0.001, "cm": 0.01, "um": 0.000001, "in": 0.0254, "ft": 0.3048}


def _colour(ratio: float | None) -> tuple[float, float, float]:
    if ratio is None:
        return (0.5, 0.5, 0.5)
    if ratio > 0.9:
        return (1.0, 0.0, 0.0)
    if ratio >= 0.7:
        return (1.0, 0.5, 0.0)
    if ratio >= 0.5:
        return (1.0, 1.0, 0.0)
    return (0.0, 1.0, 0.0)


def export_stress_map(result: Prediction, target: Path) -> Path:
    if target.suffix.lower() != ".obj":
        raise ValueError("stress map export requires .obj")
    obj = result.objects[0]
    if obj.model is None or any(part._mesh is None or part.solid is not None for part in obj.parts):
        raise ValueError("stress map requires mesh geometry")
    scale = _METRES.get(obj.units)
    regions = result._stress_regions if scale is not None else ()
    tree = KDTree(np.asarray([item[0] for item in regions])) if regions else None
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Reality nominal axial stress screening; not FEA\n")
        if tree is None:
            stream.write("# Stress data insufficient for colouring\n")
            stream.write("# Provide material and load case\n")
        vertex_offset = 0
        for part in obj.parts:
            mesh = cast(trimesh.Trimesh, part._mesh).copy()
            mesh.apply_transform(part.transform.matrix)
            vertices = np.asarray(mesh.vertices, dtype=float)
            if tree is not None and scale is not None:
                _, indices = tree.query(vertices * scale)
                ratios: list[float | None] = [
                    regions[int(index)][1] for index in np.atleast_1d(indices)
                ]
            else:
                ratios = [None] * len(vertices)
            for vertex, ratio in zip(vertices, ratios, strict=True):
                colour = _colour(ratio)
                stream.write(
                    "v "
                    + " ".join(format(float(value), ".9g") for value in (*vertex, *colour))
                    + "\n"
                )
            for face in mesh.faces:
                stream.write("f " + " ".join(str(int(i) + 1 + vertex_offset) for i in face) + "\n")
            vertex_offset += len(vertices)
    return target
