"""Trimesh adapter for supported scene formats."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import numpy as np
import trimesh

from ._metadata import SceneMetadata, SceneMetadataError, merge_scene_metadata, parse_scene_metadata
from ._models import Bounds, Transform, WorldObject
from ._world import World

SUPPORTED_SUFFIXES = frozenset({".glb", ".gltf", ".obj"})


def load(
    path: str | Path,
    *,
    backend: Literal["cpu", "cuda"] = "cpu",
    metadata: Mapping[str, object] | str | Path | None = None,
) -> World:
    """Load GLB, glTF, or OBJ geometry into a backend-neutral :class:`World`.

    Trimesh remains an implementation detail: each returned object retains a
    mesh reference while its public geometry is represented by ``Transform``
    and ``Bounds``.  Explicit articulation and rigid-body metadata can be read
    from ``extras.reality`` in glTF/GLB files, an optional sibling
    ``<scene>.reality.json`` file, or the ``metadata`` argument.  Later sources
    override earlier sources field-by-field; no physical information is inferred
    from mesh names or topology.
    """
    source = Path(path)
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(
            f"unsupported scene format {source.suffix!r}; supported formats: {supported}"
        )
    if not source.is_file():
        raise FileNotFoundError(source)
    scene_metadata = _metadata_for(source, metadata)
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
    world = World(objects, units=scene_metadata.units or "m", backend=backend)
    _apply_metadata(world, scene_metadata)
    return world


def _metadata_for(
    source: Path, metadata: Mapping[str, object] | str | Path | None
) -> SceneMetadata:
    documents: list[SceneMetadata] = []
    embedded = _embedded_gltf_metadata(source)
    if embedded is not None:
        documents.append(embedded)
    sidecar = source.with_suffix(".reality.json")
    if sidecar.is_file():
        documents.append(_metadata_file(sidecar))
    if metadata is not None:
        if isinstance(metadata, str | Path):
            documents.append(_metadata_file(Path(metadata)))
        else:
            documents.append(parse_scene_metadata(metadata, source="metadata argument"))
    return merge_scene_metadata(*documents)


def _metadata_file(path: Path) -> SceneMetadata:
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SceneMetadataError(f"{path}: invalid JSON: {error.msg}") from error
    return parse_scene_metadata(payload, source=str(path))


def _embedded_gltf_metadata(source: Path) -> SceneMetadata | None:
    if source.suffix.lower() not in {".gltf", ".glb"}:
        return None
    document = _gltf_document(source)
    payloads: list[object] = []
    extras = document.get("extras")
    if isinstance(extras, Mapping) and "reality" in extras:
        payloads.append(extras["reality"])
    scenes = document.get("scenes")
    scene_index = document.get("scene", 0)
    if isinstance(scenes, list) and isinstance(scene_index, int) and 0 <= scene_index < len(scenes):
        scene = scenes[scene_index]
        if isinstance(scene, Mapping):
            scene_extras = scene.get("extras")
            if isinstance(scene_extras, Mapping) and "reality" in scene_extras:
                payloads.append(scene_extras["reality"])
    nodes = document.get("nodes")
    if isinstance(nodes, list):
        node_objects: dict[str, object] = {}
        for index, node in enumerate(nodes):
            if not isinstance(node, Mapping):
                continue
            node_extras = node.get("extras")
            if not isinstance(node_extras, Mapping) or "reality" not in node_extras:
                continue
            name = node.get("name")
            if not isinstance(name, str) or not name.strip():
                raise SceneMetadataError(
                    f"{source}: nodes[{index}].extras.reality requires a non-empty node name"
                )
            node_objects[name] = node_extras["reality"]
        if node_objects:
            payloads.append({"objects": node_objects})
    if not payloads:
        return None
    return merge_scene_metadata(
        *(
            parse_scene_metadata(payload, source=f"{source} embedded metadata")
            for payload in payloads
        )
    )


def _gltf_document(source: Path) -> Mapping[str, object]:
    try:
        if source.suffix.lower() == ".gltf":
            document = json.loads(source.read_text(encoding="utf-8"))
        else:
            data = source.read_bytes()
            if len(data) < 20 or data[:4] != b"glTF":
                raise SceneMetadataError(f"{source}: invalid GLB header")
            offset = 12
            document = None
            while offset + 8 <= len(data):
                length = int.from_bytes(data[offset : offset + 4], "little")
                kind = data[offset + 4 : offset + 8]
                start, end = offset + 8, offset + 8 + length
                if end > len(data):
                    raise SceneMetadataError(f"{source}: invalid GLB chunk length")
                if kind == b"JSON":
                    document = json.loads(data[start:end].decode("utf-8").rstrip(" \t\r\n\0"))
                    break
                offset = end
            if document is None:
                raise SceneMetadataError(f"{source}: GLB does not contain a JSON chunk")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SceneMetadataError(f"{source}: invalid embedded glTF metadata JSON") from error
    if not isinstance(document, Mapping):
        raise SceneMetadataError(f"{source}: glTF JSON document must be an object")
    return document


def _apply_metadata(world: World, metadata: SceneMetadata) -> None:
    for item in metadata.objects:
        try:
            object_ = world.object(item.reference)
        except LookupError as error:
            raise SceneMetadataError(
                f"metadata references missing or ambiguous object {item.reference!r}"
            ) from error
        if item.physics is not None:
            world.set_physics(object_, **item.physics)  # type: ignore[arg-type]
        if item.articulation is not None:
            world.articulate(object_, **item.articulation)  # type: ignore[arg-type]


def _unique_name(name: str, used_names: set[str]) -> str:
    candidate = name or "object"
    suffix = 2
    while candidate in used_names:
        candidate = f"{name}-{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate
