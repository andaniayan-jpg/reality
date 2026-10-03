# Reality AI runtime audit — 2026-10-03

`REALITY_AI_RUNTIME_STATUS=PARTIAL`

This work is a provider-neutral **foundation**, not a claim that Reality v3/v4
or the requested zero-setup AI experience is complete.

## Verified locally

- Existing geometry, CAD, editing, agent, MCP, API, and v3/v4 foundation tests:
  **152 passed, 5 CUDA skips, 0 failed**. CUDA hardware was unavailable here.
- Ruff lint passed; strict mypy passed for 47 Reality source files and the
  three new API support modules checked separately.
- Thirteen package AI runtime tests passed as part of the full suite, including
  an actual loopback HTTP transport test and wire-format tests with fake
  provider responses, transient HTTP fallback, and non-retryable auth failure.
  Eight API gateway tests covered authentication, revocation, scope, production
  opt-in/account entitlements, image checks, persistent daily quotas,
  oversized and chunked bodies, and package client → real loopback FastAPI
  HTTP transport. The model in that network
  test was a controlled stub; no live provider model was invoked.
- `python -m build --wheel` built in isolation and produced
  `reality-0.2.1-py3-none-any.whl`; Twine metadata check passed. Fresh
  Python 3.11 and 3.13 virtual environments installed the wheel and its
  dependencies without host site packages, imported Reality from their own
  `site-packages`, and inspected a generated OBJ. Python 3.12 remains covered
  by the configured CI matrix rather than this local machine.
- PostgreSQL 16 applied migrations 001–004 in order in a disposable,
  network-isolated container; `ai_daily_usage` had the expected six columns.
  The container was stopped and auto-removed after the check.
- Eleven website physics tests passed by direct Node execution. The `npm test`
  wrapper could not spawn the Node test subprocess in this sandbox (`EPERM`).

## Current machine

The local inference service was not running, no compatible model was installed,
and no GPU was detected. `local_setup_plan()` recommended a small text model
based on detected RAM, but did not install it. This machine therefore cannot
currently produce a live `reality.copilot()` answer.

## What remains

- The source API has scoped `/v1/ai/copilot` and `/v1/ai/perceive` gateways,
  but neither is deployed;
  no provider credentials have been supplied, and no live
  Gemini/Groq/NIM/OpenRouter response was tested.
- The gateway now has a database-atomic per-account UTC-day request allowance,
  coarse usage counts, an early 12 MiB JSON body limit, an 8 MiB image limit,
  a 1,024-token provider output cap, and production AI disabled by default
  with an account-ID allowlist. These bound calls but are not exact
  provider-billed token or currency accounting; live usage/pricing
  reconciliation remains for the credentialed deployment.
- No automatic installer/model pull, browser login, camera path, streaming,
  rate-limit guarantee, or three-minute first-run guarantee exists.
- Provider-side budgets, live cost reconciliation, public deployment, and
  inference-worker scale testing remain unverified.
- Proposed `reason`, `simulate`, `generate`, `twin`, and embodied `agents` AI
  layers are not implemented. Existing deterministic Reality physics and
  `RealityAgent` are separate and remain available.
- Existing [V3_AUDIT.md](V3_AUDIT.md) and [V4_AUDIT.md](V4_AUDIT.md) both report
  `PARTIAL`; a complete v3/v4 release must not be inferred from passing tests.

These AI additions are not published to PyPI. Installing the current public
`reality` package will not include them yet.
