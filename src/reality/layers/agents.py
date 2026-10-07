"""Deterministic simulation agents; language models are optional advisers only."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import generate, simulate


@dataclass(slots=True)
class SimAgent:
    position: list[float]
    sensors: dict[str, float]
    memory: list[str] = field(default_factory=list)
    last_action: str = "idle"


class AgentTeam:
    def __init__(
        self, environment: simulate.SimWorld, count: int, role: str, sensors: list[str]
    ) -> None:
        if count < 1:
            raise ValueError("count must be positive")
        self.environment = environment
        self.role = role
        self.agents = tuple(
            SimAgent([0.0, 0.0, 0.0], {sensor: 0.0 for sensor in sensors}) for _ in range(count)
        )

    def run(self, episodes: int = 10) -> tuple[SimAgent, ...]:
        if episodes < 1:
            raise ValueError("episodes must be positive")
        for episode in range(episodes):
            for agent in self.agents:
                agent.last_action = "sense"
                agent.memory.append(f"episode {episode}: deterministic sensor sweep")
                agent.sensors["episode"] = float(episode)
        return self.agents

    def to_ros2(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "# Generated conservative ROS 2 scaffold\n"
            "# Agent decisions require deployment-specific validation.\n",
            encoding="utf-8",
        )
        return target

    @property
    def export(self) -> AgentTeam:
        return self


def environment(description: str) -> simulate.SimWorld:
    """Build a bounded primitive environment from a description."""
    obj = generate.object(description)
    sim = simulate.world()
    sim.add(obj=obj, mass=obj.estimated_mass or 1.0)
    sim.add_surface()
    return sim


def spawn(
    count: int = 1,
    role: str = "inspection",
    sensors: list[str] | None = None,
    *,
    environment: simulate.SimWorld | None = None,
) -> AgentTeam:
    return AgentTeam(environment or simulate.world(), count, role, sensors or ["proximity"])
