# Reality Cloud API

Reality Cloud exposes the existing `reality` Python package through a tenant-scoped HTTP API. It does not implement alternate geometry rules: analysis workers call `reality.open()` and the public inspection methods.

Interactive OpenAPI is available at `/docs`; the machine-readable specification is `/v1/openapi.json`.

## Authentication

Create an account in the dashboard, then create a test or live key. Phone
sign-in uses a one-time SMS code delivered by a configured Twilio Verify
service. Email/password sign-in remains available for existing accounts. The
dashboard keeps its session in an HttpOnly cookie; the API key is shown once.
Send that key only from a server you control:

```bash
curl http://localhost:8000/v1/files \
  -H "Authorization: Bearer $REALITY_API_KEY" \
  -F "file=@engine.step"
```

Keys are `rlt_test_...` or `rlt_live_...`. The raw value is returned only when it is created or rotated. Browser apps should use a backend-for-frontend or the authenticated dashboard; never bundle an API key into client JavaScript.

Phone endpoints are `POST /v1/phone/start` with `{"phone":"+14155552671"}`
and `POST /v1/phone/check` with the same E.164 number plus the received numeric
`code`. A successful check creates or resumes the account and sets the same
dashboard session cookie as email login. A missing SMS configuration returns
`503`; malformed numbers return `422`; incorrect or expired codes return `401`.
These endpoints require real Twilio credentials to deliver a code. There is no
development backdoor that accepts a fixed code.

## Files and jobs

| Endpoint | Description |
| --- | --- |
| `POST /v1/files` | Upload a supported source file and enqueue analysis. |
| `GET /v1/files` | List up to 100 files owned by the caller. |
| `GET /v1/files/{id}` | Poll state: `uploaded`, `queued`, `processing`, `ready`, or `failed`. |
| `DELETE /v1/files/{id}` | Delete the tenant-owned source and derived records. |
| `POST /v1/models/{id}/analyze` | Idempotently enqueue analysis again. |
| `POST /v1/models/{id}/edits` | Queue an immutable, package-backed edit plan. |
| `GET /v1/edits/{job_id}` | Poll edit state and retrieve its tenant-scoped result model ID. |

Use `Idempotency-Key` on upload and analysis retries. IDs are UUIDs, not server paths. An object owned by a different tenant returns `404`.

## Model inspection

After a model is `ready`:

```bash
curl http://localhost:8000/v1/models/$MODEL_ID/summary \
  -H "Authorization: Bearer $REALITY_API_KEY"

curl http://localhost:8000/v1/models/$MODEL_ID/distance \
  -H "Authorization: Bearer $REALITY_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"first":"part-1","second":"part-2"}'
```

Available operations are `summary`, `parts`, `measure`, `distance`, `clearance`, `intersections`, `convert`, and `preview`. `preview` returns a GLB for display only. The typed calculation responses include `value`, `measurement`, `units`, `tolerance`, `backend`, `reason`, affected `objects`, and `evidence`.

`POST /v1/models/{id}/convert` accepts `{"format":"glb"}`, `stl`, or `step`. CAD-to-mesh conversion carries Reality's explicit loss warning semantics; mesh-to-STEP is rejected by the engine rather than fabricating B-rep facts.

## Editing

Edits are asynchronous because real CAD and mesh operations may be expensive.
Submit an ordered plan whose operation names and parameters match the public
`RealityModel.edit()` API:

```bash
curl "http://localhost:8000/v1/models/$MODEL_ID/edits" \
  -X POST \
  -H "Authorization: Bearer $REALITY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operations":[{"operation":"translate","parameters":{"target":"housing","x":2.0}}]}'
```

The response is a job with `status`. Poll `GET /v1/edits/{job_id}` until it is
`ready`, then use `result_model_id` for normal summary, parts, measurement,
conversion, and preview endpoints. The original source remains unchanged.
Supported plans run through the same `reality` package, not a service-specific
geometry implementation. Invalid topology or incompatible CAD/mesh operations
fail the job with an explanatory error.

## Errors

Every API response provides `X-Request-Id`. Error JSON is stable:

```json
{"error":"request_rejected","message":"model is not ready; poll the file status and retry","request_id":"..."}
```

Common errors: `401` invalid/revoked key, `403` missing scope, `404` absent or other-tenant resource, `409` model not ready, `413` oversize upload, `422` unsupported or malformed upload, and `429` per-key rate limit.

## Official clients

Python (`packages/client-python`):

```python
from reality_cloud import Reality

client = Reality(api_key="rlt_live_...")
model = client.upload("engine.step").wait()
print(model.summary())
```

JavaScript (`packages/client-js`) is deliberately server-side Node.js only:

```javascript
const reality = new Reality({ apiKey: process.env.REALITY_API_KEY });
const model = await reality.upload("engine.step");
console.log(await model.summary());
```

## MCP adapter and versioned edits

The transport-neutral MCP adapter is in `apps/mcp`; see [MCP documentation](mcp.md).
It invokes these endpoints with the caller's tenant-scoped API key and contains
no geometry implementation. `POST /v1/models/{id}/topology` exposes source
topology where available. `GET /v1/models/{id}/versions` lists immutable model
lineage, and `POST /v1/models/{id}/undo` returns the prior version ID without
deleting the current model. MCP requires explicit confirmation before calling
the source-changing edit or undo endpoints.
