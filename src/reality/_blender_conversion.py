"""Opt-in instructions for converting a native Blender file to mesh geometry."""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from ._file_model import ModelFileError


class BlenderConversionRequired(ModelFileError):
    """A .blend file needs an explicit, user-run Blender export."""

    def __init__(self, source: Path, script: Path, output: Path, command: str) -> None:
        self.source = source
        self.script = script
        self.output = output
        self.command = command
        super().__init__(
            "Native Blender files are not parsed directly. Review the generated export "
            f"script at {script}; run it in Blender with: {command}; then call "
            f"from_3d({str(output)!r}). Only open trusted .blend files."
        )


def gltf_export_script(source: Path) -> str:
    """Return a reviewable Blender script; never execute Blender on import."""
    if not source.is_file():
        raise FileNotFoundError(source)
    target = source.with_name(f"{source.stem}-reality.gltf")
    return (
        "# Review this script and run it only with a trusted .blend file.\n"
        "import bpy\n"
        "from pathlib import Path\n"
        f"source = Path({str(source)!r})\n"
        f"target = Path({str(target)!r})\n"
        "if target.exists():\n"
        "    raise FileExistsError(target)\n"
        "bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)\n"
        "bpy.ops.export_scene.gltf(filepath=str(target), export_format='GLTF_EMBEDDED')\n"
    )


def conversion_instructions(source: Path) -> BlenderConversionRequired:
    if not source.is_file():
        raise FileNotFoundError(source)
    target = source.with_name(f"{source.stem}-reality.obj")
    if target.exists():
        raise ModelFileError(
            f"{target} already exists; move or rename it before requesting a new export"
        )
    script_text = (
        "# Review before running. Run only on a trusted Blender file.\n"
        "import bpy\n"
        "from pathlib import Path\n"
        f"target = Path({str(target)!r})\n"
        "if target.exists():\n"
        "    raise FileExistsError(target)\n"
        "if hasattr(bpy.ops.wm, 'obj_export'):\n"
        "    bpy.ops.wm.obj_export(filepath=str(target))\n"
        "elif hasattr(bpy.ops.export_scene, 'obj'):\n"
        "    bpy.ops.export_scene.obj(filepath=str(target))\n"
        "else:\n"
        "    raise RuntimeError('This Blender version has no OBJ exporter')\n"
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="reality-blend-export-", encoding="utf-8", delete=False
    ) as stream:
        stream.write(script_text)
        script = Path(stream.name)
    arguments = [
        "blender",
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        str(source),
        "--python",
        str(script),
    ]
    command = subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments)
    return BlenderConversionRequired(source, script, target, command)
