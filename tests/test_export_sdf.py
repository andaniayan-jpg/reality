from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import reality


def test_sdf_writeback_preserves_structure_and_updates_inertia(tmp_path: Path) -> None:
    path = tmp_path / "arm.sdf"
    path.write_text(
        '<sdf version="1.9"><model name="arm"><link name="base"><inertial>'
        '<mass>2</mass></inertial><collision name="shape"><geometry><box>'
        '<size>1 1 1</size></box></geometry></collision></link><link name="tool">'
        '<collision name="shape"><geometry><box><size>0.2 0.2 1</size>'
        '</box></geometry></collision></link><joint name="hinge" type="revolute">'
        "<parent>base</parent><child>tool</child></joint></model></sdf>",
        encoding="utf-8",
    )
    obj = reality.perceive.from_3d(path, density_kg_m3=1000)
    original_root = ET.parse(obj.export(tmp_path / "same.sdf")).getroot()
    assert original_root.findtext("model/link/inertial/mass") == "2"
    output = obj.modify.scale(factor=2).export(tmp_path / "edited.sdf")
    root = ET.parse(output).getroot()
    assert root.find("model").get("name") == "arm"
    assert {node.get("name") for node in root.findall("model/link")} == {"base", "tool"}
    assert root.find("model/joint").get("name") == "hinge"
    assert float(root.findtext('model/link[@name="base"]/inertial/mass')) == pytest.approx(8000)
    assert reality.perceive.from_3d(output).model is not None


def test_sdf_recomputes_from_declared_mass_without_guessed_density(tmp_path: Path) -> None:
    path = tmp_path / "body.sdf"
    path.write_text(
        '<sdf version="1.9"><model name="body"><link name="body">'
        '<inertial><mass>2</mass></inertial><collision name="box">'
        "<geometry><box><size>1 1 1</size></box></geometry>"
        "</collision></link></model></sdf>",
        encoding="utf-8",
    )
    obj = reality.perceive.from_3d(path)
    output = obj.modify.scale(factor=2).export(tmp_path / "scaled.sdf")
    assert float(ET.parse(output).getroot().findtext("model/link/inertial/mass")) == pytest.approx(
        16
    )
