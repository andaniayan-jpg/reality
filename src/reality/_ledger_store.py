"""Hash-chained local persistence for immutable v4 provenance ledgers.

The store is deliberately local and single-process. Its chain detects accidental
or unsophisticated record modification; it is not a substitute for signed,
externally anchored, multi-writer production audit infrastructure.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._provenance import WorldLedger

_SCHEMA = "reality-ledger-store/v1"
_LINEAGE = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class LedgerIntegrityError(ValueError):
    """Raised when a persisted ledger is malformed or fails hash-chain checks."""


@dataclass(frozen=True, slots=True)
class LedgerVerification:
    """Verified facts about one persisted ledger file."""

    path: Path
    lineage_id: str
    entry_count: int
    initial_state_digest: str
    current_state_digest: str
    last_record_hash: str | None


class JsonlLedgerStore:
    """Append-only JSON Lines store for one or more local world lineages.

    Callers must serialize concurrent writers themselves. Production v4 storage
    should provide database transactions, authorization, signing, and external
    integrity anchors in addition to this deterministic file format.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path_for(self, lineage_id: str) -> Path:
        """Return the safely constrained local JSONL path for one lineage."""
        if not _LINEAGE.fullmatch(lineage_id):
            raise ValueError("lineage_id contains unsupported path characters")
        return self.root / f"{lineage_id}.jsonl"

    def persist(self, ledger: WorldLedger) -> LedgerVerification:
        """Append new ledger entries after verifying all existing history."""
        if not ledger.entries:
            raise ValueError("cannot persist a ledger without an initial entry")
        _validate_ledger(ledger)
        destination = self.path_for(ledger.provenance.lineage_id)
        if destination.exists():
            existing = self._read(destination)
            _validate_header(existing.header, ledger)
            if len(existing.entries) > len(ledger.entries):
                raise LedgerIntegrityError("persisted ledger has more entries than supplied ledger")
            for index, record in enumerate(existing.entries):
                if record["entry"] != ledger.entries[index].to_dict():
                    raise LedgerIntegrityError(
                        f"supplied ledger diverges from persisted history at entry {index}"
                    )
            start = len(existing.entries)
            previous_hash = existing.verification.last_record_hash
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            header = _header(ledger)
            destination.write_text(_line(header) + "\n", encoding="utf-8")
            start = 0
            previous_hash = _digest(header)
        if start < len(ledger.entries):
            with destination.open("a", encoding="utf-8", newline="\n") as stream:
                for index, entry in enumerate(ledger.entries[start:], start=start):
                    core = {
                        "kind": "entry",
                        "sequence": index,
                        "previous_record_hash": previous_hash,
                        "entry": entry.to_dict(),
                    }
                    record_hash = _digest(core)
                    stream.write(_line({**core, "record_hash": record_hash}) + "\n")
                    previous_hash = record_hash
                stream.flush()
                os.fsync(stream.fileno())
        return self.verify(ledger.provenance.lineage_id)

    def verify(self, lineage_id: str) -> LedgerVerification:
        """Parse and fully verify the hash and state-digest chain for one file."""
        destination = self.path_for(lineage_id)
        parsed = self._read(destination)
        return parsed.verification

    def _read(self, path: Path) -> _ParsedLedger:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise LedgerIntegrityError(f"could not read ledger {path}") from error
        if not lines:
            raise LedgerIntegrityError("ledger file is empty")
        records = [_json_line(path, line, index) for index, line in enumerate(lines, start=1)]
        header = records[0]
        if header.get("kind") != "header" or header.get("schema") != _SCHEMA:
            raise LedgerIntegrityError("ledger header is missing or uses an unsupported schema")
        lineage_id = _string(header, "lineage_id")
        initial = _sha(header.get("initial_state_digest"), "initial_state_digest")
        previous_hash = _digest(header)
        last_state = initial
        entries: list[dict[str, Any]] = []
        for sequence, record in enumerate(records[1:]):
            if record.get("kind") != "entry" or record.get("sequence") != sequence:
                raise LedgerIntegrityError(f"ledger entry {sequence} has an invalid sequence")
            if record.get("previous_record_hash") != previous_hash:
                raise LedgerIntegrityError(f"ledger entry {sequence} breaks the hash chain")
            record_hash = _sha(record.get("record_hash"), "record_hash")
            core = {key: value for key, value in record.items() if key != "record_hash"}
            if _digest(core) != record_hash:
                raise LedgerIntegrityError(f"ledger entry {sequence} has an invalid record hash")
            entry = record.get("entry")
            if not isinstance(entry, dict):
                raise LedgerIntegrityError(
                    f"ledger entry {sequence} does not contain an entry object"
                )
            input_digest = entry.get("input_state_digest")
            output_digest = _sha(entry.get("output_state_digest"), "output_state_digest")
            if sequence == 0 and input_digest is not None:
                raise LedgerIntegrityError(
                    "initial ledger entry must not have an input state digest"
                )
            if sequence == 0 and output_digest != initial:
                raise LedgerIntegrityError(
                    "initial ledger entry does not match the header state digest"
                )
            if sequence and input_digest != last_state:
                raise LedgerIntegrityError(f"ledger entry {sequence} breaks the state-digest chain")
            entries.append(record)
            previous_hash = record_hash
            last_state = output_digest
        if not entries:
            raise LedgerIntegrityError("ledger file has no entries")
        return _ParsedLedger(
            header=header,
            entries=tuple(entries),
            verification=LedgerVerification(
                path=path,
                lineage_id=lineage_id,
                entry_count=len(entries),
                initial_state_digest=initial,
                current_state_digest=last_state,
                last_record_hash=previous_hash,
            ),
        )


@dataclass(frozen=True, slots=True)
class _ParsedLedger:
    header: Mapping[str, Any]
    entries: tuple[dict[str, Any], ...]
    verification: LedgerVerification


def _header(ledger: WorldLedger) -> dict[str, object]:
    initial = ledger.entries[0]
    return {
        "kind": "header",
        "schema": _SCHEMA,
        "lineage_id": ledger.provenance.lineage_id,
        "units": ledger.provenance.units,
        "coordinate_frame": ledger.provenance.coordinate_frame,
        "source_digest": ledger.provenance.source_digest,
        "initial_state_digest": initial.output_state_digest,
    }


def _validate_header(header: Mapping[str, Any], ledger: WorldLedger) -> None:
    expected = _header(ledger)
    for key in ("lineage_id", "units", "coordinate_frame", "source_digest", "initial_state_digest"):
        if header.get(key) != expected[key]:
            raise LedgerIntegrityError(f"persisted ledger header differs for {key!r}")


def _validate_ledger(ledger: WorldLedger) -> None:
    previous: str | None = None
    for index, entry in enumerate(ledger.entries):
        if index == 0:
            if entry.input_state_digest is not None:
                raise ValueError("initial ledger entry must not have an input state digest")
        elif entry.input_state_digest != previous:
            raise ValueError(f"ledger entry {index} does not continue the previous state digest")
        if not _DIGEST.fullmatch(entry.output_state_digest):
            raise ValueError(f"ledger entry {index} has an invalid output state digest")
        previous = entry.output_state_digest
    if ledger.provenance.state_digest != previous:
        raise ValueError("ledger provenance does not match its final entry state digest")


def _json_line(path: Path, line: str, number: int) -> dict[str, Any]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        raise LedgerIntegrityError(f"ledger {path} has invalid JSON on line {number}") from error
    if not isinstance(value, dict):
        raise LedgerIntegrityError(f"ledger {path} line {number} must be an object")
    return value


def _digest(value: Mapping[str, object]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _line(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _string(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise LedgerIntegrityError(f"ledger header field {key!r} must be a non-empty string")
    return result


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise LedgerIntegrityError(f"ledger field {field!r} must be a SHA-256 hexadecimal digest")
    return value
