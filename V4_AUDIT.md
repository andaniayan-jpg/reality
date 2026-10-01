# Reality v4 foundation audit

`V4_STATUS=PARTIAL`

## Implemented and verified

- `WorldLedger.capture(world)` creates an immutable provenance record from the
  current `WorldSnapshot`.
- `append_snapshot()` accepts only a snapshot from the same lineage and returns
  a new ledger; it does not mutate the original ledger, base world, or branch.
- The state fingerprint is a deterministic SHA-256 digest of backend-neutral
  world state: IDs, names, local bounds, transforms, explicit physical inputs,
  agents, articulations, units, and navigation configuration.
- Caller-supplied coordinate frames and source digests are recorded. Missing
  coordinate-frame data stays `null`; it is never inferred.
- Ledger entries are JSON serializable and have timezone-aware timestamps.
- `JsonlLedgerStore` persists local ledger entries in a SHA-256-linked JSONL
  chain, verifies the chain before append, rejects unsafe lineage IDs, and
  detects edited entry data in tests.
- The existing Reality Cloud API now has a local browser-verified dashboard
  with one-time-reveal developer keys, real model analysis/measurement, and
  a real-provider SMS verification path. See [WEB_AUDIT.md](WEB_AUDIT.md).
  Live SMS and public deployment remain unverified.
- The API's PostgreSQL schema migrations 001–003 and real OBJ analysis were
  validated against a disposable local PostgreSQL 16 container. This is not a
  hosted multi-replica or object-storage deployment test.

## Deliberate exclusions

- Opaque mesh and CAD backend references are not included in the state digest.
  A caller needing source-asset integrity must provide an independently
  calculated source digest.
- This is a local value-object ledger, not a hosted append-only database,
  collaborative merge service, identity provider, distributed clock, or digital
  twin service.
- The JSONL store intentionally has no cross-process writer lock, signature,
  tenant authorization, replication, or external integrity anchor. An attacker
  able to rewrite the complete file can recalculate its unsigned hash chain.
- The ledger itself has no live sensor ingestion, tenant authorization,
  cross-device conflict resolution, or hardware actuation. The separate API
  does support tenant-scoped model storage, but its production deployment is
  not verified here.
- A fresh local `0.2.1` wheel and sdist were built and passed Twine checks.
  A clean Python 3.11 environment installed the wheel and performed a real OBJ
  inspection. No v4 release or public deployment is claimed.

The runnable demonstration is `python examples/world_ledger.py`. V4 remains a
foundation effort; its broader platform work is defined in [V4.md](V4.md).
