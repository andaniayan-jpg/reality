"""Optional Assimp mesh import; source geometry is converted to OBJ in memory."""

from __future__ import annotations

import importlib
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

from ._file_model import (
    ModelAssembly,
    ModelFileError,
    ModelPart,
    RealityModel,
    _model_from_parts,
    _unique_name,
)
from ._models import Bounds, Transform


def _obj_mesh(mesh: Any) -> trimesh.Trimesh:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if (
        vertices.ndim != 2
        or vertices.shape[1] != 3
        or not np.all(np.isfinite(vertices))
        or faces.ndim != 2
        or faces.shape[1] != 3
        or len(faces) == 0
        or np.any(faces < 0)
        or np.any(faces >= len(vertices))
    ):
        raise ModelFileError("Assimp mesh contains invalid or non-triangular geometry")
    # Convert one source mesh at a time. This retains scene-node names and
    # transforms outside the OBJ payload; flattening the scene would lose both.
    lines = [f"v {x:.17g} {y:.17g} {z:.17g}" for x, y, z in vertices]
    lines.extend(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces)
    parsed = trimesh.load(BytesIO(("\n".join(lines) + "\n").encode()), file_type="obj")
    if not isinstance(parsed, trimesh.Trimesh) or parsed.is_empty:
        raise ModelFileError("Assimp mesh could not be converted to OBJ")
    return parsed


def open_assimp(source: Path, suffix: str) -> RealityModel:
    try:
        assimp = importlib.import_module("pyassimp")
    except BaseException as error:
        # PyAssimp itself raises AssimpError(BaseException) when its native
        # library is missing. Never mask process termination or cancellation.
        if isinstance(error, KeyboardInterrupt | SystemExit | GeneratorExit):
            raise
        raise ModelFileError(
            "FBX/DAE/3DS support requires reality[assimp] and a native libassimp installation"
        ) from error

    parts: list[ModelPart] = []
    assemblies: list[ModelAssembly] = []
    used_names: set[str] = set()
    try:
        with assimp.load(str(source)) as scene:

            def visit(node: Any, parent_matrix: NDArray[np.float64], parent_id: str | None) -> str:
                assembly_id = (
                    "assembly-root" if parent_id is None else f"assembly-{len(assemblies) + 1}"
                )
                local_matrix = np.asarray(node.transformation, dtype=np.float64)
                if local_matrix.shape != (4, 4):
                    raise ModelFileError("Assimp node has an invalid transform")
                world_matrix = parent_matrix @ local_matrix
                transform = Transform.from_matrix(world_matrix)
                part_ids: list[str] = []
                for mesh_index, source_mesh in enumerate(node.meshes, start=1):
                    parsed = _obj_mesh(source_mesh)
                    candidate = str(getattr(source_mesh, "name", "") or node.name or "part")
                    name = _unique_name(candidate, used_names)
                    part_id = f"part-{len(parts) + 1}"
                    parts.append(
                        ModelPart(
                            name=name,
                            id=part_id,
                            transform=transform,
                            bounds=Bounds.from_points(parsed.bounds).transformed(transform),
                            _mesh=parsed,
                            metadata={"source_node": str(node.name), "mesh_index": mesh_index},
                        )
                    )
                    part_ids.append(part_id)
                slot = len(assemblies)
                assemblies.append(ModelAssembly(name=str(node.name), id=assembly_id))
                child_ids = tuple(
                    visit(child, world_matrix, assembly_id) for child in node.children
                )
                assemblies[slot] = ModelAssembly(
                    name=str(node.name or source.stem),
                    id=assembly_id,
                    parent_id=parent_id,
                    part_ids=tuple(part_ids),
                    child_ids=child_ids,
                )
                return assembly_id

            visit(scene.rootnode, np.eye(4), None)
    except ModelFileError:
        raise
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt | SystemExit | GeneratorExit):
            raise
        raise ModelFileError(f"{source}: Assimp could not parse this file: {error}") from error
    if not parts:
        raise ModelFileError(f"{source}: contains no triangular mesh geometry")
    return _model_from_parts(
        source,
        suffix,
        "unknown",
        parts,
        assemblies,
        {
            "backend": "assimp-trimesh",
            "unit_source": f".{suffix} units not established by this adapter",
            "file_size": source.stat().st_size,
            "conversion": "individual meshes via in-memory OBJ",
        },
    )
