from __future__ import annotations

from pathlib import Path

import reality


def test_declared_joint_has_evidence_gated_risk(tmp_path: Path) -> None:
    path = tmp_path / "arm.sdf"
    path.write_text(
        '<sdf version="1.9"><model name="arm"><link name="base">'
        '<collision name="box"><geometry><box><size>1 1 1</size></box>'
        '</geometry></collision></link><link name="tool"><collision name="box">'
        "<geometry><box><size>0.2 0.2 0.2</size></box></geometry>"
        '</collision></link><joint name="hinge" type="revolute">'
        "<parent>base</parent><child>tool</child></joint></model></sdf>"
    )
    obj = reality.perceive.from_3d(path, density_kg_m3=1000)
    unknown = reality.reason.predict("500 N load", obj)
    assert unknown.joint_risks["hinge"] == "insufficient_evidence"
    measured = reality.reason.predict(
        "500 N load",
        obj,
        joint_areas_m2={"hinge": 1e-4},
        joint_allowable_stress_pa=10e6,
        joint_forces_newtons={"hinge": 900},
    )
    assert measured.joint_risks["hinge"] == "high"
    assert measured.weakest_joint == "hinge"
