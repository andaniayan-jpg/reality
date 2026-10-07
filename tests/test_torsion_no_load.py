from __future__ import annotations

from pathlib import Path

import trimesh

import reality


def test_shaft_capacity_does_not_invent_torque_or_risk(tmp_path: Path) -> None:
    path = tmp_path / "shaft.obj"
    path.write_text(trimesh.creation.cylinder(radius=0.1, height=2).export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    result = reality.reason.predict(
        "How much torque?", obj, yield_strength_pa=200e6, yield_source="test fixture"
    )
    assert result.torsional_capacity is not None and result.torsional_capacity > 0
    assert result.applied_torque is None
    assert result.torsion_risk is None
    assert result.missing_by_mode["torsion"] == ("applied torque for risk classification",)


def test_square_bar_is_not_misclassified_as_circular_shaft(tmp_path: Path) -> None:
    path = tmp_path / "square.obj"
    path.write_text(trimesh.creation.box(extents=(0.2, 0.2, 2)).export(file_type="obj"))
    obj = reality.perceive.from_3d(path, units="m")
    result = reality.reason.predict(
        "shaft?", obj, yield_strength_pa=200e6, yield_source="test fixture"
    )
    assert result.torsional_capacity is None
