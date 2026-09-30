"""Measure structural ingestion of generated GLB scenes (no binary fixtures)."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import trimesh

import reality


def scene(count: int, *, subdivisions: int = 0) -> trimesh.Scene:
    mesh = trimesh.creation.icosphere(subdivisions=subdivisions)
    result = trimesh.Scene()
    for index in range(count):
        result.add_geometry(
            mesh,
            node_name=f"part-{index}",
            transform=trimesh.transformations.translation_matrix((index * 3.0, 0.0, 0.0)),
        )
    return result


def measure(count: int, *, subdivisions: int = 0) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "scene.glb"
        scene(count, subdivisions=subdivisions).export(path)
        started = time.perf_counter()
        model = reality.open(path)
        elapsed = time.perf_counter() - started
        return {
            "parts": count,
            "faces_per_part": int(len(model.parts[0].mesh.faces)),
            "file_bytes": path.stat().st_size,
            "open_seconds": elapsed,
            # ``predicate_count`` is a theoretical pair capacity. Report actual
            # materialized edges so the lazy path is not mistaken for a full
            # all-pairs graph calculation.
            "materialized_relationships": model.graph.relationship_count,
        }


if __name__ == "__main__":
    results = [measure(size) for size in (1, 100, 1_000)]
    results.append(measure(1, subdivisions=5))
    print(json.dumps(results, indent=2))
