from __future__ import annotations

from pathlib import Path

import pytest

import reality


def test_sdf_declared_inertia_and_limits_override_estimates(tmp_path: Path) -> None:
    path = tmp_path / "arm.sdf"
    path.write_text(
        """<sdf version="1.9"><model name="arm">
        <link name="base"><inertial><mass>2</mass><inertia>
          <ixx>1</ixx><ixy>0</ixy><ixz>0</ixz><iyy>1</iyy><iyz>0</iyz><izz>1</izz>
        </inertia></inertial><collision name="shape"><geometry>
          <box><size>1 1 1</size></box></geometry></collision></link>
        <link name="tool"><pose>2 0 0 0 0 0</pose><inertial><mass>3</mass>
          <inertia><ixx>1</ixx><ixy>0</ixy><ixz>0</ixz><iyy>1</iyy><iyz>0</iyz><izz>1</izz>
          </inertia></inertial><collision name="shape"><geometry>
          <box><size>1 1 1</size></box></geometry></collision></link>
        <joint name="arm_joint" type="revolute"><parent>base</parent><child>tool</child>
          <axis><xyz>0 0 1</xyz><limit><lower>-1</lower><upper>1</upper>
          <effort>20</effort><velocity>2</velocity></limit></axis></joint>
        </model></sdf>""",
        encoding="utf-8",
    )
    scene = reality.perceive.from_3d(path)
    assert isinstance(scene, reality.PhysicsScene)
    assert scene.mass_source == "declared"
    assert scene.estimated_mass == pytest.approx(5)
    assert scene.total_mass == pytest.approx(5)
    assert scene.centre_of_mass == pytest.approx((1.2, 0, 0))
    assert scene.moment_of_inertia is not None
    assert scene.moment_of_inertia[1][1] == pytest.approx(6.8)
    assert [obj.estimated_mass for obj in scene.objects] == [2, 3]
    assert scene.joints[0].lower_limit == -1
    assert scene.joints[0].upper_limit == 1
    assert scene.joints[0].effort_limit == 20
    assert scene.joints[0].velocity_limit == 2
    assert scene.hierarchy[0].children[0].children[0].name == "tool"
