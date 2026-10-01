"""Run a verified local MuJoCo rollout through the Reality v3 adapter.

Install the optional dependency first:
    python -m pip install "reality[physics]"
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import reality


def main() -> None:
    with TemporaryDirectory(prefix="reality-mujoco-") as directory:
        source = Path(directory) / "arm.xml"
        source.write_text(
            """<mujoco model="controlled-arm">
  <option gravity="0 0 0"/>
  <worldbody>
    <body name="arm">
      <joint name="shoulder" type="hinge" axis="0 0 1"/>
      <geom type="capsule" size="0.05 0.4"/>
    </body>
  </worldbody>
  <actuator>
    <motor name="shoulder-motor" joint="shoulder" ctrllimited="true" ctrlrange="-2 2"/>
  </actuator>
  <sensor><jointpos name="shoulder-position" joint="shoulder"/></sensor>
</mujoco>""",
            encoding="utf-8",
        )
        adapter = reality.MuJoCoSceneIntegration()
        scene = adapter.inspect_scene(source)
        result = adapter.rollout(
            source,
            controls={"shoulder-motor": 1.0},
            seconds=0.02,
            time_step=0.002,
        )
        print(
            json.dumps(
                {
                    "mujoco_version": scene.mujoco_version,
                    "joints": [joint.name for joint in scene.joints],
                    "actuators": [actuator.name for actuator in scene.actuators],
                    "sensor_readings": dict(result.sensor_readings),
                    "steps": result.steps,
                    "hardware_commanded": result.evidence["hardware_commanded"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
