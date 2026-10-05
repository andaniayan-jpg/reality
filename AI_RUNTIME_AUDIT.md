# Reality AI runtime audit — 2026-10-05

`REALITY_AI_RUNTIME_STATUS=PARTIAL`

This work is a provider-neutral **foundation**, not a claim that Reality v3/v4
or the requested zero-setup AI experience is complete.

## Verified locally

- Existing geometry, CAD, editing, agent, MCP, API, and AI route tests:
  **172 passed, 5 CUDA skips, 0 failed**. CUDA hardware was unavailable here.
- Ruff format/lint passed; strict mypy passed for 49 Reality source files and the
  three new API support modules checked separately.
- Package AI runtime tests passed as part of the full suite, including
  an actual loopback HTTP transport test and wire-format tests with fake
  provider responses, transient HTTP fallback, and non-retryable auth failure.
  Eight API gateway tests covered authentication, revocation, scope, production
  opt-in/account entitlements, image checks, persistent daily quotas,
  oversized and chunked bodies, and package client → real loopback FastAPI
  HTTP transport. The model in that network
  test was a controlled stub.
- The exact feature-routing table is covered by parameterized tests. File-only
  image capture and a real synthetic MP4 decoded through `imageio-ffmpeg`
  returned sampled observations. No webcam or OpenCV path exists.
- A supplied provider credential successfully listed 61 Gemini API models,
  including the requested `gemini-2.5-flash`, but a live image generation
  request to that model returned HTTP 404. The key was never written to source,
  audit files, or a committed configuration. Live vision is **not** validated.
- The current `reality-0.2.1-py3-none-any.whl` built both with the installed
  backend and in an isolated build environment; Twine check passed on both.
  A completely fresh Python 3.11 virtual
  environment installed the wheel with its `video` extra and imported Reality
  from `site-packages`. Earlier foundation wheels passed fresh Python 3.11 and
  3.13 installs, but the current changes have not been retested on 3.13.
- PostgreSQL 16 applied migrations 001–004 in order in a disposable,
  network-isolated container; `ai_daily_usage` had the expected six columns.
  The container was stopped and auto-removed after the check.

## Current machine

The local inference service was not running, no compatible model was installed,
and no GPU was detected. `local_setup_plan()` recommended a small text model
based on detected RAM, but did not install it. This machine therefore cannot
currently produce a live `reality.copilot()` answer.

## What remains

- The source API has scoped `/v1/ai/copilot` and `/v1/ai/perceive` gateways,
  but neither is deployed. No successful live model response, provider-side
  fallback, or hosted end-to-end AI call has been observed.
- The gateway now has a database-atomic per-account UTC-day request allowance,
  coarse usage counts, an early 12 MiB JSON body limit, an 8 MiB image limit,
  a 1,024-token provider output cap, and production AI disabled by default
  with an account-ID allowlist. These bound calls but are not exact
  provider-billed token or currency accounting; live usage/pricing
  reconciliation remains for the credentialed deployment.
- No automatic installer/model pull, browser login, streaming,
  rate-limit guarantee, or three-minute first-run guarantee exists.
- Camera capture and live frame grabbing were intentionally excluded. The
  file-only `reality.reality.capture()` returns an `AIResponse`, not a measured
  `World`; `reality.twin.from_video()` returns bounded `VideoObservations`, not
  a reconstructed or predictive 3D twin. Video requires the optional extra.
- Provider-side budgets, live cost reconciliation, public deployment, and
  inference-worker scale testing remain unverified.
- Proposed `reason`, `simulate`, `generate`, predictive `twin`, and embodied
  `agents` AI layers are not implemented. Their feature routes are tested but
  are not a substitute for complete public APIs. Existing deterministic Reality physics and
  `RealityAgent` are separate and remain available.
- Existing [V3_AUDIT.md](V3_AUDIT.md) and [V4_AUDIT.md](V4_AUDIT.md) both report
  `PARTIAL`; a complete v3/v4 release must not be inferred from passing tests.

These AI additions are not published to PyPI. Installing the current public
`reality` package will not include them yet.
