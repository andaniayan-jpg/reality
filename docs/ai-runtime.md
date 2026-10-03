# Reality AI runtime foundation

This is an opt-in text/vision *assistant* layer, not a geometry engine. The
authoritative `World`/`RealityModel` measurements, validation, CAD operations,
and physics remain deterministic package code. An AI response is typed as
`AIResponse(text, mode)` and cannot certify a distance, clearance, collision,
or simulation outcome.

## Current public API

```python
import reality

mode = reality.detect_mode()  # "local" or "online"
profile = reality.detect_hardware()
plan = reality.local_setup_plan()  # read-only; no installation or download

# Only after a compatible local model is already installed and running:
reply = reality.copilot("Explain what a clearance query measures")
print(reply.text)

# PNG, JPEG, or WebP (at most 20 MiB):
description = reality.perceive.from_image("frame.png")
```

`reality.login(api_key)` holds an existing Reality key in process memory for
this Python session; `reality.logout()` clears it. `REALITY_API_KEY` is another
way to select online mode. Zero-argument `login()` uses that environment
variable when present. There is no OAuth/device/browser login in the package
yet. Do not put keys in browser JavaScript, source files, notebooks you share,
or logs. Use the hosted API only after a real gateway is deployed.

## Local operation

The default local transport connects only to `127.0.0.1:11434`. It lists models
through `/api/tags` and sends inference to `/api/chat`. Model selection uses
only models actually installed. For text it prefers `qwen3:14b`, then
`phi4:mini`; for images it prefers `qwen2-vl:7b`. The hardware plan's RAM-based
recommendation is an estimate, not proof that a model fits or runs fast.
`REALITY_LOCAL_MODEL` and `REALITY_LOCAL_VISION_MODEL` allow choosing another
*already installed* compatible model. A custom `Provider` can also be passed
through `ModelRouter`.

`pip install reality` never downloads an executable, launches a background
service, pulls multi-gigabyte weights, or grants installer permissions.
`local_setup_plan()` explains the missing step. First-run under three minutes,
universal offline inference, and unbounded usage cannot be guaranteed on every
machine. Once the user installs the engine and weights, local inference does
not require an internet service.

## Online operation and server adapters

The Python client looks for `REALITY_API_KEY` or an in-process login. It also
requires `REALITY_API_BASE` pointing to a deployed Reality gateway. The API
implements `POST /v1/ai/copilot` and `POST /v1/ai/perceive` with the explicit
`ai:use` key scope. The cloud image route accepts PNG, JPEG, or WebP bytes up
to 8 MiB, transported as base64 JSON; local image inspection accepts up to
20 MiB. An ordinary model-inspection key does not automatically gain paid AI
access.
No such gateway has been deployed or configured with provider credentials in
this repository, so online inference is not yet live. The client fails with
an actionable error rather than manufacturing an answer.
Production gateway access is disabled by default and requires an approved
account ID as well as explicit server-side enablement; possessing a generic
Reality API key does not activate paid AI access.

Trusted server code configures `REALITY_GEMINI_API_KEY`,
`REALITY_GROQ_API_KEY`, `REALITY_NIM_API_KEY`, and/or
`REALITY_OPENROUTER_API_KEY`; the gateway creates the matching adapters for
each request. Their HTTPS wire shapes, access scope, fail-closed behavior, and
fallback are tested, but no live provider account was used. The existing API
applies persistent per-key request-rate limits and request logs; production
AI-specific token/cost quotas and load tests still need work before deployment.
Provider keys must remain server-side. NVIDIA NIM model selection requires an
explicit `REALITY_NIM_AGENT_MODEL` because access/model IDs vary. Fallback only
retries temporary failures; it does not hide invalid authentication or unsafe
input. No provider can promise zero rate-limit errors or uninterrupted service.

## Not implemented yet

- Automatic engine installation or model download.
- Public deployment of the AI gateway, signup/device login, provider
  credentials, and production AI-specific cost controls.
- Camera capture, desktop/Blender integration, and the proposed `reason`,
  `simulate`, `generate`, `twin`, and `agents` AI layers.
- Live model quality, latency, and cross-provider parity validation.

These are future milestones; their absence does not affect the existing
deterministic Reality APIs.
