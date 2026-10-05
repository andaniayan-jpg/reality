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
capture = reality.reality.capture(source="frame.png")  # same file-only analysis

# After `pip install "reality[video]"`:
observations = reality.twin.from_video("scan.mp4")
print(observations.sampled_frames)
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
only models actually installed. The new feature-specific route requires the
configured local reasoning model for `copilot`, the fast local model for
real-time requests, and the coding model for generation requests; it does not
silently substitute a smaller text model. Vision uses the cloud vision adapter
when configured and falls back to an installed local vision model. The older
injectable `ModelRouter.route()` behavior is retained for compatibility;
its `REALITY_LOCAL_MODEL` and `REALITY_LOCAL_VISION_MODEL` overrides apply only
to that legacy route. The hardware plan's RAM-based recommendation is an
estimate, not proof that a model fits or runs fast. A custom `Provider` can
also be passed through `ModelRouter`.

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

Trusted server code configures `REALITY_GEMINI_API_KEY` (or `GEMINI_API_KEY`),
`REALITY_GROQ_API_KEY`, `REALITY_NIM_API_KEY`, and/or
`REALITY_OPENROUTER_API_KEY`; the gateway creates the matching adapters for
each request. Their HTTPS wire shapes, access scope, fail-closed behavior, and
fallback are tested. A configured image key also enables direct package vision
when no Reality Cloud key is present; this transmits the image to Google's
service. Without the key, image analysis needs a running local engine with a
compatible installed vision model. A failed cloud image call can fall back to
that local model; if neither works, Reality reports an error rather than
inventing a scene. The existing API
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
- Camera/webcam/live-frame capture is intentionally out of scope. The file-only
  capture alias returns `AIResponse`, not an exact geometric `World`.
- `twin.from_video()` validates an MP4 up to 100 MiB, uses a 60-second bounded
  decoder process to sample at most four frames, and returns typed
  `VideoObservations`. Install the optional `video` extra for its decoder. The
  original video stays local; extracted images may be sent to the configured
  cloud vision service. It does not build a 3D digital twin or predict physics.
- The proposed `reason`, `simulate`, `generate`, and `agents` AI public layers,
  plus digital-twin prediction, remain unimplemented. Their internal routing
  map is defined and tested but is not evidence that the layers exist.
- Live model quality, latency, and cross-provider parity validation.

These are future milestones; their absence does not affect the existing
deterministic Reality APIs.
