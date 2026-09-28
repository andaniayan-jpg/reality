"""Trimesh adapter for supported scene formats."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import trimesh

from ._models import Bounds, Transform, WorldObject
from ._world import World

SUPPORTED_SUFFIXES = frozenset({".glb", ".gltf", ".obj"})


def load(path: str | Path, *, backend: Literal["cpu", "cuda"] = "cpu") -> World:
    """Load GLB, glTF, or OBJ geometry into a backend-neutral :class:`World`.

    Trimesh remains an implementation detail: each returned object retains a
    mesh reference while its public geometry is represented by ``Transform``
    and ``Bounds``.
    """
    source = Path(path)
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(
            f"unsupported scene format {source.suffix!r}; supported formats: {supported}"
        )
    if not source.is_file():
        raise FileNotFoundError(source)
    scene = trimesh.load(source, force="scene")
    if not isinstance(scene, trimesh.Scene):  # Defensive: force="scene" promises a Scene.
        scene = trimesh.Scene(scene)
    objects: list[WorldObject] = []
    used_names: set[str] = set()
    for node_name in scene.graph.nodes_geometry:
        transform_matrix, geometry_name = scene.graph[node_name]
        mesh = scene.geometry[geometry_name]
        base_name = str(node_name) if node_name else str(geometry_name)
        name = _unique_name(base_name, used_names)
        objects.append(
            WorldObject(
                name=name,
                id=name,
                local_bounds=Bounds.from_points(np.asarray(mesh.bounds)),
                transform=Transform.from_matrix(np.asarray(transform_matrix)),
                mesh=mesh,
            )
        )
    return World(objects, backend=backend)


def _unique_name(name: str, used_names: set[str]) -> str:
    candidate = name or "object"
    suffix = 2
    while candidate in used_names:
        candidate = f"{name}-{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate
