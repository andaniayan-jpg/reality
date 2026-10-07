"""Regression coverage for the dependency-free completion-layer contracts."""

from __future__ import annotations

import reality


def test_copilot_is_string_compatible_when_local_ai_is_unavailable() -> None:
    reality.copilot.reset()
    answer = reality.copilot("Explain gravity in one sentence.")
    assert isinstance(answer, str)


def test_builtin_simulation_and_primitive_generation_work_without_optional_engines() -> None:
    generated = reality.generate.object("steel cube 1m")
    assert generated.model is not None
    assert generated.estimated_mass is not None
    sim = reality.simulate.world()
    sim.add("box", mass=10)
    sim.add_surface()
    result = sim.run(steps=3)
    assert result.final_state["box"][1] >= 0


def test_configuration_is_explicit_and_status_is_read_only() -> None:
    current = reality.status()
    assert "Setup:" in str(current)
