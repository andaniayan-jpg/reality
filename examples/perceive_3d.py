"""Inspect an input file, or generate a closed cube when no path is supplied.

Run from an installed package with: python examples/perceive_3d.py [file.obj]
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import trimesh

import reality


def inspect(path: Path) -> None:
    units = "mm" if path.suffix.lower() in {".obj", ".stl", ".ply"} else None
    obj = reality.perceive.from_3d(path, units=units, density_kg_m3=2700)
    print(obj.summary)
    print(f"Watertight: {obj.watertight}")
    print(f"Centre of mass: {obj.centre_of_mass} {obj.units}")
    print(f"Estimated mass: {obj.estimated_mass} kg")
    print(f"Joint declarations: {len(obj.joints)}")
    print(f"Thin-part screening candidates: {len(obj.weak_points)}")
    print(reality.reason.predict("Could this fail under a 500 kg load?", obj))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        inspect(Path(sys.argv[1]))
    else:
        with TemporaryDirectory() as directory:
            demo = Path(directory) / "cube.obj"
            trimesh.creation.box(extents=(2, 2, 2)).export(demo)
            inspect(demo)
