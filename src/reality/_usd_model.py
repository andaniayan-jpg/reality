"""Optional OpenUSD mesh importer that preserves names and transform hierarchy.

USD stages may contain references and native parser code. Hosted use must run
this adapter in a resource-limited worker, never directly in an API process.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

from ._file_model import ModelAssembly, ModelFileError, ModelPart, RealityModel, _model_from_parts
from ._models import Bounds, Transform


@dataclass(frozen=True, slots=True)
class _UsdMaterialLabel:
    name: str
    path: str


def _triangles(
    points: NDArray[np.float64], counts: list[int], indices: list[int]
) -> NDArray[np.int64]:
    triangles: list[tuple[int, int, int]] = []
    offset = 0
    for count in counts:
        face = indices[offset : offset + count]
        offset += count
        if len(face) != count or any(index < 0 or index >= len(points) for index in face):
            raise ModelFileError("USD mesh has invalid face indices")
        if count == 3:
            triangles.append((face[0], face[1], face[2]))
        elif count == 4:
            quad = points[face]
            normal = np.cross(quad[1] - quad[0], quad[2] - quad[1])
            turns = [
                float(
                    np.dot(
                        np.cross(
                            quad[(i + 1) % 4] - quad[i], quad[(i + 2) % 4] - quad[(i + 1) % 4]
                        ),
                        normal,
                    )
                )
                for i in range(4)
            ]
            if np.linalg.norm(normal) <= 1e-12 or any(turn <= 0 for turn in turns):
                raise ModelFileError("USD mesh has a non-convex or degenerate quad")
            triangles.extend(((face[0], face[1], face[2]), (face[0], face[2], face[3])))
        else:
            raise ModelFileError(
                "USD mesh polygons with more than four vertices need triangulation"
            )
    if offset != len(indices):
        raise ModelFileError("USD mesh face counts do not match face indices")
    result: NDArray[np.int64] = np.asarray(triangles, dtype=np.int64)
    return result


def open_usd(source: Path) -> RealityModel:
    try:
        from pxr import Usd, UsdGeom, UsdShade
    except ImportError as error:
        raise ModelFileError("USD support requires: pip install reality[usd]") from error
    with source.open("rb") as stream:
        is_ascii = stream.read(5) == b"#usda"
        if is_ascii:
            while chunk := stream.read(1024 * 1024):
                if b"@" in chunk:
                    raise ModelFileError(
                        "USD external asset references require an isolated import worker"
                    )
    try:
        stage = Usd.Stage.Open(str(source), load=Usd.Stage.LoadNone)
    except Exception as error:
        raise ModelFileError(f"{source}: USD stage could not be opened") from error
    if stage is None:
        raise ModelFileError(f"{source}: USD stage could not be opened")
    metres_per_unit = float(UsdGeom.GetStageMetersPerUnit(stage))
    if not np.isfinite(metres_per_unit) or metres_per_unit <= 0:
        raise ModelFileError("USD stage has invalid metres-per-unit metadata")
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    parts: list[ModelPart] = []
    source_paths: dict[str, str] = {}
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh_schema = UsdGeom.Mesh(prim)
        points_value: Any = mesh_schema.GetPointsAttr().Get()
        counts_value: Any = mesh_schema.GetFaceVertexCountsAttr().Get()
        indices_value: Any = mesh_schema.GetFaceVertexIndicesAttr().Get()
        if points_value is None or counts_value is None or indices_value is None:
            raise ModelFileError(f"USD mesh {prim.GetPath()} is missing topology")
        points = np.asarray(points_value, dtype=np.float64) * metres_per_unit
        if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
            raise ModelFileError("USD mesh has invalid points")
        triangles = _triangles(
            points, [int(value) for value in counts_value], [int(value) for value in indices_value]
        )
        if len(triangles) == 0:
            raise ModelFileError("USD mesh has no supported faces")
        mesh = trimesh.Trimesh(vertices=points, faces=triangles, process=False)
        matrix = np.asarray(cache.GetLocalToWorldTransform(prim), dtype=np.float64).T
        matrix[:3, 3] *= metres_per_unit
        try:
            transform = Transform.from_matrix(matrix)
        except ValueError as error:
            raise ModelFileError("USD shear transforms are not yet supported") from error
        path = prim.GetPath().pathString
        part_id = f"part-{len(parts) + 1}"
        source_paths[part_id] = path
        material, _binding = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        material_path = material.GetPath().pathString if material else None
        material_label = (
            _UsdMaterialLabel(material.GetPrim().GetName(), material_path)
            if material_path is not None
            else None
        )
        parts.append(
            ModelPart(
                name=prim.GetName(),
                id=part_id,
                transform=transform,
                bounds=Bounds.from_points(np.asarray(mesh.bounds)).transformed(transform),
                material=material_label,
                _mesh=mesh,
                metadata={"source_prim": path, "material_path": material_path},
            )
        )
    if not parts:
        raise ModelFileError("USD stage has no loaded triangle/convex-quad mesh geometry")

    all_paths: set[str] = set()
    direct_parts: dict[str, list[str]] = defaultdict(list)
    for part_id, path in source_paths.items():
        parent = path.rpartition("/")[0] or "/"
        direct_parts[parent].append(part_id)
        while parent != "/":
            all_paths.add(parent)
            parent = parent.rpartition("/")[0] or "/"
    child_paths: dict[str, list[str]] = defaultdict(list)
    for path in sorted(all_paths):
        child_paths[path.rpartition("/")[0] or "/"].append(path)
    assemblies = (
        ModelAssembly(
            name=source.stem,
            id="assembly-root",
            part_ids=tuple(direct_parts["/"]),
            child_ids=tuple(f"assembly:{path}" for path in child_paths["/"]),
        ),
        *(
            ModelAssembly(
                name=path.rpartition("/")[2],
                id=f"assembly:{path}",
                part_ids=tuple(direct_parts[path]),
                child_ids=tuple(f"assembly:{child}" for child in child_paths[path]),
                parent_id=(
                    f"assembly:{path.rpartition('/')[0]}"
                    if path.rpartition("/")[0]
                    else "assembly-root"
                ),
                metadata={"source_prim": path},
            )
            for path in sorted(all_paths)
        ),
    )
    return _model_from_parts(
        source,
        source.suffix.lower().lstrip("."),
        "m",
        parts,
        assemblies,
        {
            "backend": "openusd-pxr",
            "unit_source": "USD stage metresPerUnit, normalized to metres",
            "source_metres_per_unit": metres_per_unit,
            "source_units_authored": bool(stage.HasAuthoredMetadata("metersPerUnit")),
            "file_size": source.stat().st_size,
            "loaded_payloads": False,
        },
    )
