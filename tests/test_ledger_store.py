from __future__ import annotations

from pathlib import Path

import pytest

from reality import Bounds, JsonlLedgerStore, LedgerIntegrityError, World, WorldLedger, WorldObject


def _world() -> World:
    return World(
        [WorldObject("Payload", Bounds((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1)), id="payload")]
    )


def test_jsonl_store_appends_and_verifies_a_branch_digest_chain(tmp_path: Path) -> None:
    world = _world()
    ledger = WorldLedger.capture(world, actor="test")
    store = JsonlLedgerStore(tmp_path / "ledgers")

    first = store.persist(ledger)
    branch = world.branch()
    branch.move("Payload", x=1.0)
    updated = ledger.append_snapshot(branch.snapshot(), event="payload-moved", actor="test")
    second = store.persist(updated)

    assert first.entry_count == 1
    assert second.entry_count == 2
    assert second.initial_state_digest == first.initial_state_digest
    assert second.current_state_digest == updated.provenance.state_digest
    assert store.verify(world.snapshot().lineage_id) == second
    assert world.object("Payload").position == (0.0, 0.0, 0.0)


def test_jsonl_store_detects_modified_entry_data(tmp_path: Path) -> None:
    world = _world()
    store = JsonlLedgerStore(tmp_path)
    ledger = WorldLedger.capture(world, actor="test", evidence={"source": "fixture"})
    store.persist(ledger)
    path = store.path_for(world.snapshot().lineage_id)
    path.write_text(
        path.read_text(encoding="utf-8").replace("fixture", "tampered"), encoding="utf-8"
    )

    with pytest.raises(LedgerIntegrityError, match="record hash"):
        store.verify(world.snapshot().lineage_id)


def test_jsonl_store_rejects_path_traversal_like_lineage_ids(tmp_path: Path) -> None:
    store = JsonlLedgerStore(tmp_path)

    with pytest.raises(ValueError, match="path characters"):
        store.path_for("../outside")
