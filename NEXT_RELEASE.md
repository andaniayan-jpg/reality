# Next release: verified cloud AI preview

Candidate package version: `0.3.0`. Do not change the current `0.2.1` version
or publish until every release gate below passes. This is a narrow, testable
release, **not** a declaration that the complete v3/v4 vision is finished.

## Finish line

A user can install the published wheel with `pip install reality`, configure a
Reality API key and deployed endpoint, and call both:

```python
import reality

print(reality.copilot("Explain how to inspect a joint clearance").text)
print(reality.perceive.from_image("part.png").text)
```

The response is clearly generated guidance, never a measured geometry or
simulation result. Existing `reality.open()`, `load()`, editing, physics,
futures, and integrations remain compatible.

## Release gates

1. **Real inference:** Configure server-side provider secrets and verify one
   live text response and one live image response through the authenticated
   Reality API. Record provider, model ID, date, latency, and redacted evidence
   in an internal audit; do not expose credentials or user content.
2. **Authentication and isolation:** `ai:use` is required for both routes;
   revoked keys and other tenants are denied. Provider secrets never reach
   Python-client responses, browser code, logs, or package artifacts.
3. **Fallback:** Test deterministic injected 429/5xx/timeout cases and a real
   provider failure where safely reproducible. A secondary configured provider
   succeeds when eligible; exhausted capacity returns a generic structured
   error. Invalid authentication remains visible to operators, not silently
   treated as success. No zero-rate-limit guarantee is claimed.
4. **Image safety:** Enforce the 8 MiB cloud limit, accepted types, mismatched
   MIME rejection, malformed encoding rejection, service/proxy body limits,
   and no image persistence by the gateway. Validate a genuine image with a
   live provider, not just a magic-byte test fixture.
5. **Operational controls:** Apply per-key rate limits and AI-specific cost or
   token quotas, timeouts, request IDs, redacted audit logs, and usage metrics.
   Load-test the synchronous gateway or move inference to bounded workers.
6. **Compatibility:** Run full tests, Ruff, mypy, wheel build, Twine, API
   integration tests, and Python 3.11–3.13 CI. Preserve deterministic
   geometry results and document any optional dependencies.
7. **Clean installation:** Build in isolation and install the final wheel in
   a clean venv with dependencies. After publication, run `pip install
   --no-cache-dir reality==0.3.0` outside the source checkout and confirm
   `reality.__file__` is from `site-packages`. Verify both text and image API
   calls against the deployed service.
8. **Truthful audit:** Publish a release audit with exact commands, counts,
   live-provider proof, known limitations, and an explicit PASS/PARTIAL/FAIL.
   Do not publish if a critical gate is PARTIAL or FAIL.

## Current progress

- **Done in source:** typed client routing, local model discovery, text and
  image cloud transports, server-side provider adapters, scoped API routes,
  input bounds, fail-closed behavior, and deterministic adapter/API tests.
- **Blocked on credentials/deployment:** live cloud inference and its latency,
  model-access, fallback, and billing evidence.
- **Verified locally:** a database-backed daily account request allowance,
  early AI JSON body limit, provider output-token caps, a real client-to-API
  loopback HTTP test with a stub model, production opt-in/account allowlisting,
  PostgreSQL 16 migration 004, and an
  isolated build/clean wheel install on Python 3.11 and 3.13. These bound use
  but do not establish exact provider-billed cost accounting.
- **Not done:** live token/currency reconciliation, public deployment, and
  PyPI publication. The Python 3.12 clean install relies on CI rather than a
  local interpreter.

## Work after this release

1. **Local-first milestone:** an explicit, consent-based setup flow; hardware
   and model compatibility checks; genuine offline text/image inference on
   several machine classes. Installation and download size/time are shown to
   users—never hidden or guaranteed to finish in three minutes.
2. **V3 integrations milestone:** native Blender, game-engine, simulator, and
   robotics adapters one at a time, each with capability boundaries and tests
   in its actual runtime. No claim of physical-AI hardware safety from a
   simulated rollout.
3. **Physical reasoning milestone:** tool-backed planning over real Reality
   measurements and simulations, with provenance and rollback. Model text may
   propose actions; deterministic tools validate every numerical claim.
4. **V4 platform milestone:** durable multi-tenant workflows, versioned world
   state, collaborative edits, governed data retention, and live digital-twin
   ingestion. Each component needs security and deployment evidence before it
   is called production-ready.

The broader [V3 audit](V3_AUDIT.md) and [V4 audit](V4_AUDIT.md) remain
`PARTIAL` until those milestones are independently verified.
