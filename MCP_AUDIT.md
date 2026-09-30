# Reality MCP audit

`REALITY_MCP_STATUS=PASS`

- Test return code: `0`

## Evidence

- MCP tests upload and inspect actual GLB/OBJ bytes through FastAPI.
- MCP measure, topology, preview, conversion, edit, versions, and undo call /v1.
- Destructive apply/undo require explicit confirmation.
- A second account receives a real API 404 for another tenant's model.

## Boundaries

- The adapter is transport-neutral; a host chooses the MCP stdio/HTTP SDK integration.
- No hosted production endpoint is claimed by this local integration audit.

The full local end-to-end evidence is retained in `MCP_RESULTS.json`.
