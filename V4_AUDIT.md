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

## Deliberate exclusions

- Opaque mesh and CAD backend references are not included in the state digest.
  A caller needing source-asset integrity must provide an independently
  calculated source digest.
- This is a local value-object ledger, not a hosted append-only database,
  collaborative merge service, identity provider, distributed clock, or digital
  twin service.
- No live sensor ingestion, object storage, tenancy, cross-device conflict
  resolution, or hardware actuation is claimed.
- A fresh distributable-wheel build is not verified in this session because the
  isolated build environment could not download its Hatchling dependency. The
  source-level test, lint, typing, and example checks remain verified.

The runnable demonstration is `python examples/world_ledger.py`. V4 remains a
foundation effort; its broader platform work is defined in [V4.md](V4.md).
