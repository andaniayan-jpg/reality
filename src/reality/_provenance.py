"""Local, immutable provenance records for the v4 platform foundation.

This module intentionally records the backend-neutral ``WorldSnapshot`` state.
It does not claim to fingerprint opaque mesh/CAD references: applications that
need source-asset integrity must provide a separately calculated source digest.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from ._articulation import PrismaticJoint, RevoluteJoint
from ._state import WorldSnapshot

if TYPE_CHECKING:
    from ._world import World

_SCHEMA = "reality-provenance/v1"


@dataclass(frozen=True, slots=True)
class WorldProvenance:
    """Identity and fingerprint for one immutable, backend-neutral world state."""

    schema: str
    lineage_id: str
    revision: int
    units: str
    coordinate_frame: str | None
    state_digest: str
    source_digest: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "lineage_id": self.lineage_id,
            "revision": self.revision,
            "units": self.units,
            "coordinate_frame": self.coordinate_frame,
            "state_digest": self.state_digest,
            "source_digest": self.source_digest,
        }


@dataclass(frozen=True, slots=True)
class ProvenanceEntry:
    """An immutable transition between two fingerprinted world states."""

    event: str
    actor: str
    timestamp: datetime
    input_state_digest: str | None
    output_state_digest: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event.strip():
            raise ValueError("provenance event must not be empty")
        if not self.actor.strip():
            raise ValueError("provenance actor must not be empty")
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    def to_dict(self) -> dict[str, object]:
        return {
            "event": self.event,
            "actor": self.actor,
            "timestamp": self.timestamp.isoformat(),
            "input_state_digest": self.input_state_digest,
            "output_state_digest": self.output_state_digest,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class WorldLedger:
    """An append-only local ledger for snapshots from one world lineage.

    The ledger is a value object: appending returns a new ledger and never
    mutates a previous ledger, snapshot, or world. A hosted v4 service can
    store these records in an append-only database later.
    """

    provenance: WorldProvenance
    entries: tuple[ProvenanceEntry, ...]

    @classmethod
    def capture(
        cls,
        world: World,
        *,
        actor: str = "system",
        event: str = "world-captured",
        coordinate_frame: str | None = None,
        source_digest: str | None = None,
        evidence: Mapping[str, object] = MappingProxyType({}),
    ) -> WorldLedger:
        """Create the first ledger entry from an immutable current snapshot."""
        snapshot = world.snapshot()
        provenance = provenance_for(
            snapshot,
            coordinate_frame=coordinate_frame,
            source_digest=source_digest,
        )
        entry = ProvenanceEntry(
            event=event,
            actor=actor,
            timestamp=datetime.now(UTC),
            input_state_digest=None,
            output_state_digest=provenance.state_digest,
            evidence=evidence,
        )
        return cls(provenance=provenance, entries=(entry,))

    def append_snapshot(
        self,
        snapshot: WorldSnapshot,
        *,
        actor: str = "system",
        event: str,
        evidence: Mapping[str, object] = MappingProxyType({}),
    ) -> WorldLedger:
        """Append a later snapshot from the same lineage without mutation."""
        if snapshot.lineage_id != self.provenance.lineage_id:
            raise ValueError("a ledger can only append snapshots from its original world lineage")
        next_provenance = provenance_for(
            snapshot,
            coordinate_frame=self.provenance.coordinate_frame,
            source_digest=self.provenance.source_digest,
        )
        entry = ProvenanceEntry(
            event=event,
            actor=actor,
            timestamp=datetime.now(UTC),
            input_state_digest=self.provenance.state_digest,
            output_state_digest=next_provenance.state_digest,
            evidence=evidence,
        )
        return replace(self, provenance=next_provenance, entries=self.entries + (entry,))

    def to_dict(self) -> dict[str, object]:
        return {
            "provenance": self.provenance.to_dict(),
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent)


def provenance_for(
    snapshot: WorldSnapshot,
    *,
    coordinate_frame: str | None = None,
    source_digest: str | None = None,
) -> WorldProvenance:
    """Fingerprint source state without including cache or opaque mesh references."""
    if coordinate_frame is not None and not coordinate_frame.strip():
        raise ValueError("coordinate_frame must be non-empty when supplied")
    if source_digest is not None and not source_digest.strip():
        raise ValueError("source_digest must be non-empty when supplied")
    encoded = json.dumps(_canonical_state(snapshot), sort_keys=True, separators=(",", ":")).encode()
    return WorldProvenance(
        schema=_SCHEMA,
        lineage_id=snapshot.lineage_id,
        revision=snapshot.version,
        units=snapshot.units,
        coordinate_frame=coordinate_frame,
        state_digest=hashlib.sha256(encoded).hexdigest(),
        source_digest=source_digest,
    )


def _canonical_state(snapshot: WorldSnapshot) -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "lineage_id": snapshot.lineage_id,
        "revision": snapshot.version,
        "units": snapshot.units,
        "navigation": {
            "resolution": snapshot.navigation_resolution,
            "margin": snapshot.navigation_margin,
            "backend": snapshot.compute_backend,
        },
        "objects": [
            _object_state(object_) for object_ in sorted(snapshot.objects, key=lambda item: item.id)
        ],
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "position": list(agent.position),
                "height": agent.height,
                "radius": agent.radius,
                "step_height": agent.step_height,
                "max_slope": agent.max_slope,
            }
            for agent in sorted(snapshot.agents, key=lambda item: item.id)
        ],
        "articulations": [
            _articulation_state(articulation) for articulation in snapshot.articulations
        ],
    }


def _object_state(object_: Any) -> dict[str, object]:
    return {
        "id": object_.id,
        "name": object_.name,
        "local_bounds": {
            "minimum": list(object_.local_bounds.minimum),
            "maximum": list(object_.local_bounds.maximum),
        },
        "transform": {
            "position": list(object_.position),
            "rotation": list(object_.rotation),
            "scale": list(object_.scale),
        },
        "physical": {
            "mass": object_.mass,
            "dynamic": object_.dynamic,
            "collision_shape": object_.collision_shape,
            "friction": object_.friction,
            "restitution": object_.restitution,
            "center_of_mass": list(object_.center_of_mass),
        },
    }


def _articulation_state(articulation: Any) -> dict[str, object]:
    joint = articulation.joint
    state: dict[str, object] = {
        "object_id": articulation.object_id,
        "kind": joint.kind,
        "axis": list(joint.axis),
        "minimum": joint.minimum,
        "maximum": joint.maximum,
        "current": joint.current,
    }
    if isinstance(joint, RevoluteJoint):
        state["pivot"] = list(joint.pivot)
        state["angular_resolution"] = joint.angular_resolution
    elif isinstance(joint, PrismaticJoint):
        state["linear_resolution"] = joint.linear_resolution
    return state
