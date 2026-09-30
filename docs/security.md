# Reality Cloud security model

Reality Cloud treats uploaded 3D and CAD files as untrusted data and maintains tenant boundaries at every persistence lookup.

## Credentials

- API keys use the `rlt_test_` and `rlt_live_` prefixes.
- Only an HMAC-SHA-256 hash, prefix, scopes, owner, timestamps, and status are stored. Raw keys are shown only at creation/rotation.
- Verification recomputes the HMAC and uses constant-time comparison.
- Passwords use PBKDF2-HMAC-SHA256 with a unique random salt and 600,000 iterations.
- Dashboard sessions are random, hashed in the database, seven-day, `HttpOnly`, `SameSite=Lax`, and `Secure` in production.
- `REALITY_API_SECRET` is mandatory in production. It is never committed; `.env.example` has an empty value.

## Authorization and isolation

Every file/model query resolves through the authenticated owner ID. A missing resource and an other-tenant resource both return `404`. API keys hold scopes; dashboard sessions can administer the account. Revoked keys are rejected before a request reaches model operations.

The rate limiter records API-key activity in the shared database, rather than process memory, so it works across API replicas. Request and audit records include a request ID without recording raw API keys or model contents.

## Upload and processing safety

The API enforces a byte quota, request upload limit, extension allow-list, content type allow-list, and basic magic/content checks before storage. The worker then calls `reality.open()` with the same size limit; Reality validates format content and rejects unsafe glTF URI traversal.

Source objects live behind an `ObjectStorage` protocol. Local disk is for development; S3-compatible storage is available through environment configuration. Database rows expose stable IDs, never storage paths. Deletion removes the source object and cascades derived job records.

Production deployers should run workers in separate containers, use PostgreSQL, terminate TLS at a trusted proxy, constrain CORS to known dashboard origins, apply database migrations, and set object-store lifecycle rules. A separate worker process is also the correct boundary for hard CAD parser timeouts.
