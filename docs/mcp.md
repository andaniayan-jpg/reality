# Reality MCP adapter

`apps/mcp/reality_mcp` is an authenticated adapter over Reality Cloud. It has
no geometry implementation: all authoritative queries and edits call the
existing `/v1` API, whose workers call `reality.open()` and `RealityModel`.

The adapter offers tools for upload, inspect, parts, measure, distance,
clearance, intersections, topology, preview, export, plan/apply edit, edit
status, versions, and undo. It is transport-neutral so it can be bound to an
MCP stdio/HTTP host without putting an API key into browser code.

```python
from reality_mcp import RealityMCPServer

server = RealityMCPServer(api_key="rlt_live_...", base_url="https://api.reality.dev")
model = server.upload("bracket.step")
print(server.inspect(model["id"]))

plan = server.plan_edit(model["id"], [{
    "operation": "translate", "parameters": {"target": "part-1", "x": 2.0}
}])
# A caller must show the plan to its user before this source-changing step.
job = server.apply_edit(model["id"], plan["operations"], confirmed=True)
```

`apply_edit` and `undo_edit` reject calls unless `confirmed=True`. Editing
creates an immutable derived model. `versions` exposes only that tenant's
source lineage; `undo_edit` selects a prior model ID and never deletes data.
The API enforces scopes, rate limits, key revocation, and tenant isolation.

Install the adapter and its optional official MCP SDK with `pip install -r
apps/mcp/requirements.txt`, then call `create_mcp_server(adapter)` to obtain a
`FastMCP` server for a host's stdio/HTTP transport. No ChatGPT plugin is bundled
or implied.
