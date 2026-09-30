# Deploying Reality Cloud

## Prerequisites

- PostgreSQL 16 or newer.
- S3-compatible storage for production, or a persistent local volume for development.
- A generated `REALITY_API_SECRET`.
- `reality[cad]` on workers that must process STEP/STP.

Copy `.env.example` to `.env`, set a strong `REALITY_API_SECRET` and `POSTGRES_PASSWORD`, then use:

```bash
docker compose up --build
```

The API is at `http://localhost:8000`; the dashboard is at `http://localhost:3000`. Run
`apps/api/migrations/001_initial.sql` and `002_model_versions.sql` before the first
production rollout. Local development uses SQLite through the same SQLAlchemy repository
interface.

## Scale-out model

API replicas accept uploads and enqueue persisted jobs. Worker replicas poll the shared PostgreSQL jobs table and read/write shared object storage; no model or job state is kept in a Python process. Put an external queue with leases/`SKIP LOCKED` in front of high-volume worker fleets before operating at large scale.

Health checks:

- `GET /healthz` verifies process liveness.
- `GET /readyz` verifies database reachability.

Set `REALITY_ENV=production`, `REALITY_DATABASE_URL`, `REALITY_STORAGE_BACKEND=s3`, `REALITY_S3_BUCKET`, and `REALITY_S3_ENDPOINT_URL` for production. Restrict `REALITY_CORS_ORIGINS` to the deployed dashboard domain.

## Web deployment

`apps/web` is a static responsive dashboard served by Nginx. It uses cookie-authenticated dashboard requests, so an API key is not placed in browser source. Set `REALITY_API_BASE` at deployment time if the dashboard and API have separate origins.
