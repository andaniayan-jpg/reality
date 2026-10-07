from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_stress_map_has_extended_obj_vertex_colours(tmp_path: Path) -> None:
    path = tmp_path / "cube.obj"
    path.write_text(trimesh.creation.box().export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    result = reality.reason.predict(
        "500 N load",
        obj,
        load_axis="z",
        load_case="axial_compression",
        support="opposed_face",
        yield_strength_pa=1000,
        yield_source="test fixture",
    )
    output = result.export_stress_map(tmp_path / "stress.obj")
    vertices = [line.split() for line in output.read_text().splitlines() if line.startswith("v ")]
    assert vertices
    assert all(len(vertex) == 7 for vertex in vertices)
    assert any(float(vertex[4]) == 1.0 for vertex in vertices)
