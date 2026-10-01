"""Verify that a fresh installed wheel can inspect a real generated mesh."""

from __future__ import annotations

import json
import tempfile
from importlib.metadata import version
from pathlib import Path

import trimesh

import reality


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="reality-wheel-smoke-") as directory:
        source = Path(directory) / "cube.obj"
        source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
        model = reality.open(source)
        assert model.format == "obj"
        assert model.parts
        assert model.measure(model.parts[0].name).backend
        assert reality.BlenderSceneIntegration().status().descriptor.name == "blender-active-scene"
        print(
            json.dumps(
                {
                    "version": version("reality"),
                    "import_path": str(Path(reality.__file__).resolve()),
                    "format": model.format,
                    "part_count": len(model.parts),
                    "measure_backend": model.measure(model.parts[0].name).backend,
                }
            )
        )


if __name__ == "__main__":
    main()
