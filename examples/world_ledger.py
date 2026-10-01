"""Create a reproducible local provenance ledger for a branchable Reality world."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import reality


def main() -> None:
    world = reality.World(
        [
            reality.WorldObject("Table", reality.Bounds((-1, -1, 0), (1, 1, 1)), id="table"),
            reality.WorldObject(
                "Chair",
                reality.Bounds((-0.3, -0.3, 0), (0.3, 0.3, 0.8)),
                id="chair",
            ),
        ],
        units="m",
    )
    ledger = reality.WorldLedger.capture(
        world,
        actor="layout-demo",
        coordinate_frame="right-handed-z-up",
        evidence={"source": "programmatic demo"},
    )
    future = world.branch()
    future.move("Chair", x=1.0)
    ledger = ledger.append_snapshot(
        future.snapshot(),
        actor="layout-demo",
        event="chair-moved",
        evidence={"candidate": "chair x +1m"},
    )
    with TemporaryDirectory(prefix="reality-ledger-") as directory:
        store = reality.JsonlLedgerStore(Path(directory) / "ledgers")
        verification = store.persist(ledger)
        print(
            ledger.to_json()
            + "\n"
            + str(
                {
                    "persisted_entries": verification.entry_count,
                    "current_state_digest": verification.current_state_digest,
                }
            )
        )


if __name__ == "__main__":
    main()
