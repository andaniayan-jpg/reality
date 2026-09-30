from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

import reality


def _model(path: Path) -> reality.RealityModel:
    block = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    path.write_bytes(trimesh.Scene({"block": block}).export(file_type="glb"))
    return reality.open(path)


def test_agent_plans_measures_previews_and_executes_source_backed_edit(tmp_path: Path) -> None:
    model = _model(tmp_path / "block.glb")
    agent = reality.RealityAgent(model)
    measure = agent.plan("measure block")
    measured = agent.execute(measure)
    assert measured.executed and measured.results[0].value["surface_area"] == pytest.approx(24.0)

    plan = agent.plan("move block x=200 cm")
    assert plan.valid
    assert plan.actions[0].evidence["numeric_source"] == "user_request"
    preview = agent.preview(plan)
    assert not preview.executed
    assert preview.model is not None
    assert preview.model.part("block").bounds.center[0] == pytest.approx(2.0)
    assert model.part("block").bounds.center[0] == pytest.approx(0.0)

    committed = agent.execute(plan)
    assert committed.executed and committed.model is not None
    assert committed.model.part("block").bounds.center[0] == pytest.approx(2.0)
    assert model.part("block").bounds.center[0] == pytest.approx(0.0)


def test_agent_rejects_invalid_part_ambiguity_and_rolls_back(tmp_path: Path) -> None:
    model = _model(tmp_path / "block.glb")
    agent = reality.RealityAgent(model)
    unknown = agent.plan("measure nowhere")
    assert not unknown.valid and "unknown part" in unknown.diagnostics[0]
    invalid = agent.plan("move block x=1 parsec")
    assert not invalid.valid
    result = agent.execute(invalid)
    assert not result.executed and result.model is None
    assert model.part("block").bounds.center[0] == pytest.approx(0.0)


def test_agent_create_tool_makes_real_mesh_geometry(tmp_path: Path) -> None:
    model = reality.RealityAgent(_model(tmp_path / "source.glb")).create_box(
        "fixture", width=2.0, height=3.0, depth=4.0, units="mm"
    )
    assert model.parts[0].mesh is not None
    assert model.measure("fixture").value["surface_area"] == pytest.approx(52.0)
