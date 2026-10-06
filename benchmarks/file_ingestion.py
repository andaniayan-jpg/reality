"""Reproducible local ingest timings; synthetic scenes, not production SLAs.

Run from the repository: ``python benchmarks/file_ingestion.py``.
``--large`` also writes and reads a comment-heavy 51 MiB OBJ to exercise the
large-file progress path. It is intentionally *not* representative of a dense
51 MiB engineering model.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

import numpy as np
import trimesh

import reality


def _scene(path: Path, count: int) -> None:
    scene = trimesh.Scene()
    box = trimesh.creation.box()
    for index in range(count):
        transform = np.eye(4)
        transform[0, 3] = index * 2.0
        scene.add_geometry(
            box, node_name=f"box-{index}", geom_name=f"geometry-{index}", transform=transform
        )
    path.write_bytes(scene.export(file_type="glb"))


def _large_obj(path: Path) -> None:
    body = trimesh.creation.box().export(file_type="obj").encode("utf-8")
    padding = b"# synthetic padding; not dense geometry\n" * 4096
    with path.open("wb") as stream:
        stream.write(body)
        while stream.tell() <= 51 * 1024 * 1024:
            stream.write(padding)


def _measure(path: Path, *, fast: bool) -> dict[str, object]:
    events: list[tuple[int, str]] = []
    tracemalloc.start()
    start = time.perf_counter()
    result = reality.perceive.from_3d(
        path,
        units="m" if path.suffix == ".obj" else None,
        fast=fast,
        on_progress=lambda pct, message: events.append((pct, message)),
    )
    seconds = time.perf_counter() - start
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "bytes": path.stat().st_size,
        "seconds": round(seconds, 4),
        "tracemalloc_peak_bytes": peak,
        "parts": len(result.parts),
        "fast": fast,
        "progress_events": len(events),
        "final_progress": events[-1][0],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--large", action="store_true")
    parser.add_argument("--large-only", action="store_true")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        results: dict[str, object] = {}
        if not arguments.large_only:
            for count in (1, 100, 1000):
                source = root / f"scene-{count}.glb"
                _scene(source, count)
                results[f"glb_{count}"] = _measure(source, fast=False)
        if arguments.large or arguments.large_only:
            source = root / "large.obj"
            _large_obj(source)
            results["obj_51mb_fast"] = _measure(source, fast=True)
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
