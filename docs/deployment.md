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
`003_phone_auth.sql` in order before the first
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
