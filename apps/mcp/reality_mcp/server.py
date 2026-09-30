"""MCP-shaped adapter over the authenticated Reality Cloud API.

No mesh/CAD calculation exists here: every authoritative answer is a request
to ``apps/api``, whose workers invoke the installed ``reality`` package.  The
class can be embedded by an MCP transport (stdio, HTTP, or a host integration)
without exposing a customer API key to an LLM or browser.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import httpx


class _HTTPClient(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


class MCPConfirmationRequired(PermissionError):
    """Raised before an MCP caller can send a source-changing edit."""


class RealityMCPServer:
    """Authenticated Reality API tools suitable for an MCP server transport."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.reality.dev",
        client: _HTTPClient | None = None,
    ) -> None:
        if not api_key.startswith("rlt_"):
            raise ValueError("Reality API keys begin with rlt_")
        self._owned_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {api_key}"}
        )

    def upload(self, path: str | Path) -> Mapping[str, Any]:
        source = Path(path)
        with source.open("rb") as handle:
            response = self._client.request(
                "POST",
                "/v1/files",
                files={"file": (source.name, handle, "application/octet-stream")},
            )
        return self._decode(response)

    def inspect(self, model_id: str) -> Mapping[str, Any]:
        return self._request("GET", f"/v1/models/{model_id}/summary")

    def parts(self, model_id: str) -> list[Mapping[str, Any]]:
        return self._request("GET", f"/v1/models/{model_id}/parts")

    def measure(self, model_id: str, part: str) -> Mapping[str, Any]:
        return self._request("POST", f"/v1/models/{model_id}/measure", json={"part": part})

    def distance(self, model_id: str, first: str, second: str) -> Mapping[str, Any]:
        return self._request(
            "POST", f"/v1/models/{model_id}/distance", json={"first": first, "second": second}
        )

    def clearance(self, model_id: str, first: str, second: str) -> Mapping[str, Any]:
        return self._request(
            "POST", f"/v1/models/{model_id}/clearance", json={"first": first, "second": second}
        )

    def intersections(self, model_id: str) -> list[Mapping[str, Any]]:
        return self._request("POST", f"/v1/models/{model_id}/intersections")

    def topology(self, model_id: str, part: str | None = None) -> Mapping[str, Any]:
        return self._request("POST", f"/v1/models/{model_id}/topology", json={"part": part})

    def preview(self, model_id: str) -> bytes:
        response = self._client.request("GET", f"/v1/models/{model_id}/preview")
        self._raise(response)
        return bytes(response.content)

    def export(self, model_id: str, format: str) -> Mapping[str, Any]:
        return self._request("POST", f"/v1/models/{model_id}/convert", json={"format": format})

    def plan_edit(
        self, model_id: str, operations: Sequence[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        """Return a non-mutating, API-backed edit plan for user review."""
        if not operations:
            raise ValueError("at least one edit operation is required")
        known = {str(part["id"]) for part in self.parts(model_id)} | {
            str(part["name"]) for part in self.parts(model_id)
        }
        normalized: list[dict[str, Any]] = []
        for operation in operations:
            name = str(operation.get("operation", ""))
            parameters = dict(operation.get("parameters", {}))
            target = parameters.get("target")
            if target is not None and str(target) not in known:
                raise ValueError(f"unknown source part {target!r}")
            normalized.append({"operation": name, "parameters": parameters})
        return {
            "model_id": model_id,
            "operations": normalized,
            "confirmation_required": True,
            "authority": "Reality API edit job; source geometry remains immutable",
        }

    def apply_edit(
        self, model_id: str, operations: Sequence[Mapping[str, Any]], *, confirmed: bool = False
    ) -> Mapping[str, Any]:
        """Queue an immutable edit only after an explicit caller confirmation."""
        if not confirmed:
            raise MCPConfirmationRequired(
                "set confirmed=True only after the user reviews the edit plan"
            )
        plan = self.plan_edit(model_id, operations)
        return self._request(
            "POST", f"/v1/models/{model_id}/edits", json={"operations": plan["operations"]}
        )

    def edit_status(self, job_id: str) -> Mapping[str, Any]:
        return self._request("GET", f"/v1/edits/{job_id}")

    def undo_edit(self, model_id: str, *, confirmed: bool = False) -> Mapping[str, Any]:
        if not confirmed:
            raise MCPConfirmationRequired(
                "set confirmed=True before switching to a prior model version"
            )
        return self._request("POST", f"/v1/models/{model_id}/undo")

    def versions(self, model_id: str) -> list[Mapping[str, Any]]:
        return self._request("GET", f"/v1/models/{model_id}/versions")

    def wait_for_edit(self, job_id: str, *, timeout: float = 30.0) -> Mapping[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.edit_status(job_id)
            if job["status"] == "ready":
                return job
            if job["status"] == "failed":
                raise RuntimeError(f"Reality edit failed: {job.get('error')}")
            time.sleep(0.1)
        raise TimeoutError("Reality edit job did not finish before timeout")

    def close(self) -> None:
        if self._owned_client:
            close = getattr(self._client, "close", None)
            if close is not None:
                close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._decode(self._client.request(method, path, **kwargs))

    @staticmethod
    def _raise(response: Any) -> None:
        if getattr(response, "is_error", False):
            try:
                message = response.json().get("message", response.text)
            except ValueError:
                message = response.text
            raise RuntimeError(f"Reality API {response.status_code}: {message}")

    @classmethod
    def _decode(cls, response: Any) -> Any:
        cls._raise(response)
        return response.json()


def create_mcp_server(adapter: RealityMCPServer) -> Any:
    """Bind the adapter to the optional official Python MCP stdio server.

    Importing this module never requires an MCP SDK.  Production hosts install
    the SDK explicitly and inject an already-authenticated adapter, keeping the
    API key in the host process rather than in an LLM tool argument.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:  # pragma: no cover - optional transport package
        raise RuntimeError("install the MCP SDK to expose the Reality stdio server") from error
    server = FastMCP("Reality")

    @server.tool()
    def inspect_model(model_id: str) -> Mapping[str, Any]:
        return adapter.inspect(model_id)

    @server.tool()
    def inspect_parts(model_id: str) -> list[Mapping[str, Any]]:
        return adapter.parts(model_id)

    @server.tool()
    def measure_geometry(model_id: str, part: str) -> Mapping[str, Any]:
        return adapter.measure(model_id, part)

    @server.tool()
    def measure_distance(model_id: str, first: str, second: str) -> Mapping[str, Any]:
        return adapter.distance(model_id, first, second)

    @server.tool()
    def measure_clearance(model_id: str, first: str, second: str) -> Mapping[str, Any]:
        return adapter.clearance(model_id, first, second)

    @server.tool()
    def inspect_intersections(model_id: str) -> list[Mapping[str, Any]]:
        return adapter.intersections(model_id)

    @server.tool()
    def inspect_topology(model_id: str, part: str | None = None) -> Mapping[str, Any]:
        return adapter.topology(model_id, part)

    @server.tool()
    def preview_model(model_id: str) -> bytes:
        return adapter.preview(model_id)

    @server.tool()
    def export_model(model_id: str, format: str) -> Mapping[str, Any]:
        return adapter.export(model_id, format)

    @server.tool()
    def plan_edit(model_id: str, operations: list[dict[str, Any]]) -> Mapping[str, Any]:
        return adapter.plan_edit(model_id, operations)

    @server.tool()
    def apply_edit(
        model_id: str, operations: list[dict[str, Any]], confirmed: bool = False
    ) -> Mapping[str, Any]:
        return adapter.apply_edit(model_id, operations, confirmed=confirmed)

    @server.tool()
    def undo_edit(model_id: str, confirmed: bool = False) -> Mapping[str, Any]:
        return adapter.undo_edit(model_id, confirmed=confirmed)

    return server
