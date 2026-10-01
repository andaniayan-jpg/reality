from __future__ import annotations

import json

import pytest

from reality import Bounds, World, WorldLedger, WorldObject, provenance_for


def _world() -> World:
    return World(
        [
            WorldObject("Base", Bounds((-1.0, -1.0, 0.0), (1.0, 1.0, 0.5)), id="base"),
            WorldObject("Payload", Bounds((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1)), id="payload"),
        ],
        units="m",
    )


def test_ledger_records_immutable_branch_provenance_without_mutating_base() -> None:
    world = _world()
    ledger = WorldLedger.capture(
        world,
        actor="integration-test",
        coordinate_frame="right-handed-z-up",
        source_digest="source-sha256-placeholder",
        evidence={"importer": "test"},
    )
    future = world.branch()
    future.move("Payload", x=1.0)

    updated = ledger.append_snapshot(
        future.snapshot(),
        actor="integration-test",
        event="candidate-moved",
        evidence={"change": "Payload x +1m"},
    )

    assert world.object("Payload").position == (0.0, 0.0, 0.0)
    assert len(ledger.entries) == 1
    assert len(updated.entries) == 2
    assert updated.provenance.coordinate_frame == "right-handed-z-up"
    assert updated.entries[-1].input_state_digest == ledger.provenance.state_digest
    assert updated.provenance.state_digest != ledger.provenance.state_digest
    assert json.loads(updated.to_json())["entries"][-1]["event"] == "candidate-moved"


def test_provenance_fingerprint_is_deterministic_for_one_snapshot() -> None:
    snapshot = _world().snapshot()

    first = provenance_for(snapshot, coordinate_frame="right-handed-z-up")
    second = provenance_for(snapshot, coordinate_frame="right-handed-z-up")

    assert first.state_digest == second.state_digest
    assert first.to_dict()["source_digest"] is None


def test_ledger_rejects_unrelated_world_lineage_and_invalid_metadata() -> None:
    ledger = WorldLedger.capture(_world())
    other = _world()

    with pytest.raises(ValueError, match="original world lineage"):
        ledger.append_snapshot(other.snapshot(), event="wrong-world")
    with pytest.raises(ValueError, match="coordinate_frame"):
        provenance_for(_world().snapshot(), coordinate_frame="")
