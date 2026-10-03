# Deploying Reality Cloud

## Prerequisites

- PostgreSQL 16 or newer.
- S3-compatible storage for production, or a persistent local volume for development.
- A generated `REALITY_API_SECRET`.
- A Twilio account and Verify service for mobile-number sign-in.
- `reality[cad]` on workers that must process STEP/STP.

Copy `.env.example` to `.env` and set a strong `REALITY_API_SECRET` and
`POSTGRES_PASSWORD`. Set `REALITY_DATABASE_URL` to the same database credential,
URL-encoding any special characters in the password. The example leaves these
secrets blank. Then run:

```bash
docker compose up --build
```

The API is at `http://localhost:8000`; the dashboard is at `http://localhost:3000`. Run
`apps/api/migrations/001_initial.sql`, `002_model_versions.sql`, and
`003_phone_auth.sql`, and `004_ai_usage.sql` in order before the first
production rollout. Local development uses SQLite through the same SQLAlchemy repository
interface.

Configure `REALITY_TWILIO_ACCOUNT_SID`, `REALITY_TWILIO_AUTH_TOKEN`, and
`REALITY_TWILIO_VERIFY_SERVICE_SID` in the server environment. The API sends
codes using [Twilio Verify](https://www.twilio.com/docs/verify/api) and checks
them with the provider before creating a dashboard session. Do not put these
values in `apps/web` or expose them in browser JavaScript. Local email/password
accounts continue to work without Twilio configuration.
The provider must have a usable SMS route to the destination country; Twilio
trial accounts may require the receiving number to be verified in advance.
Apply the PostgreSQL migration to existing deployments before starting the
updated API. Existing local SQLite databases need an explicit schema migration
or a new disposable development database; startup reports the missing schema
instead of serving requests against incompatible tables.

## Optional AI gateway

Set provider credentials only on the API service using the
`REALITY_GEMINI_API_KEY`, `REALITY_GROQ_API_KEY`, `REALITY_NIM_API_KEY`, and/or
`REALITY_OPENROUTER_API_KEY` environment variables. NVIDIA agent routing also
requires an explicitly verified `REALITY_NIM_AGENT_MODEL`. The dashboard and
client bundles must never receive these secrets. API keys need the explicit
`ai:use` scope for `/v1/ai/copilot`, `/v1/ai/perceive`, and `/v1/ai/usage`.
Production AI is **off by default**. Set `REALITY_AI_ENABLED=true` and
`REALITY_AI_ALLOWED_ACCOUNT_IDS` to a comma-separated list of approved
account IDs (available from `/v1/me`) before adding provider keys. Startup
fails closed if AI is enabled in production without an allowlist. Unapproved
users cannot self-issue an `ai:use` key or call AI through a dashboard
session. This is a controlled-preview entitlement boundary, not a billing
system; public self-service access needs a persisted entitlement and payment
policy before the allowlist can be removed.

`REALITY_AI_DAILY_REQUEST_LIMIT` defaults to 100 calls per account and UTC
day. Reservations are atomic in the shared database across API replicas;
failed upstream calls still consume one reservation. The API records prompt,
image, and output *sizes*, not customer prompt or image content. The request
body cap defaults to 12 MiB and applies before JSON parsing, including
chunked requests. The client and server also enforce an 8 MiB image cap and
adapters cap generated output at 1,024 tokens. These are request bounds, **not
exact currency or token billing**. Production pricing/usage reconciliation
requires live provider response validation and a separate billing control.

Put a matching request-body limit and connection timeout at the ingress proxy;
do not rely on the application as the only protection. This repository has no
public AI gateway deployment or live-provider audit yet.

## Scale-out model

API replicas accept uploads and enqueue persisted jobs. Worker replicas poll the shared PostgreSQL jobs table and read/write shared object storage; no model or job state is kept in a Python process. Put an external queue with leases/`SKIP LOCKED` in front of high-volume worker fleets before operating at large scale.

Health checks:

- `GET /healthz` verifies process liveness.
- `GET /readyz` verifies database reachability.

Set `REALITY_ENV=production`, `REALITY_DATABASE_URL`, `REALITY_STORAGE_BACKEND=s3`, `REALITY_S3_BUCKET`, and `REALITY_S3_ENDPOINT_URL` for production. Restrict `REALITY_CORS_ORIGINS` to the deployed dashboard domain.

## Web deployment

`apps/web` is a static responsive dashboard served by Nginx. It uses cookie-authenticated dashboard requests, so an API key is not placed in browser source. Set `REALITY_API_BASE` at deployment time if the dashboard and API have separate origins.

For local website work without Docker, run `python tools/dev_web.py` after
starting the API on port 8000. `python tools/browser_smoke.py` exercises real
browser login, key creation, OBJ upload, analysis, preview fetching, part
inspection, and measurement. It does not send an SMS; live SMS requires
configured Twilio credentials and a real receiving number.
