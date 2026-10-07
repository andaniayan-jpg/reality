from __future__ import annotations

import ast
from pathlib import Path

import trimesh

import reality


def test_ros2_node_is_python_and_has_description_and_joint_state(tmp_path: Path) -> None:
    path = tmp_path / "cube.obj"
    path.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    obj = reality.perceive.from_3d(path, units="m", density_kg_m3=1000)
    node = obj.export.to_ros2(tmp_path / "robot_node.py")
    content = node.read_text(encoding="utf-8")
    ast.parse(content)
    assert "rclpy" in content
    assert "robot_description" in content
    assert "/joint_states" in content
    assert (tmp_path / "robot_node.urdf").is_file()
