from __future__ import annotations

from pathlib import Path

import pytest
import trimesh
from fastapi.testclient import TestClient
from reality_api.config import Settings
from reality_api.main import create_app
from reality_mcp import MCPConfirmationRequired, RealityMCPServer


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'mcp.db'}",
        storage_backend="local",
        storage_root=tmp_path / "objects",
        s3_bucket=None,
        s3_endpoint_url=None,
        api_secret="mcp-test-secret",
        environment="test",
        cors_origins=("http://testserver",),
        max_upload_bytes=10 * 1024 * 1024,
        sync_analysis_bytes=10 * 1024 * 1024,
        rate_limit_per_minute=100,
        default_quota_bytes=20 * 1024 * 1024,
    )


def _key(client: TestClient, email: str) -> str:
    assert (
        client.post(
            "/v1/accounts", json={"email": email, "password": "secure-password-123"}
        ).status_code
        == 201
    )
    response = client.post("/v1/keys", json={"environment": "test"})
    assert response.status_code == 201
    return str(response.json()["key"])


def test_mcp_calls_real_api_for_inspection_edit_versions_and_export(tmp_path: Path) -> None:
    source = tmp_path / "block.glb"
    source.write_bytes(trimesh.Scene({"block": trimesh.creation.box()}).export(file_type="glb"))
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        server = RealityMCPServer(api_key=_key(client, "mcp@example.com"), client=client)
        uploaded = server.upload(source)
        model_id = str(uploaded["id"])
        assert server.inspect(model_id)["format"] == "glb"
        assert server.measure(model_id, "block")["value"]["surface_area"] == pytest.approx(6.0)
        assert server.topology(model_id)["part-1"] is None
        plan = server.plan_edit(
            model_id, [{"operation": "translate", "parameters": {"target": "block", "x": 3.0}}]
        )
        assert plan["confirmation_required"] is True
        with pytest.raises(MCPConfirmationRequired):
            server.apply_edit(model_id, plan["operations"])
        job = server.apply_edit(model_id, plan["operations"], confirmed=True)
        edited = server.wait_for_edit(str(job["id"]))
        result_id = str(edited["result_model_id"])
        assert server.versions(result_id)[1]["id"] == model_id
        assert server.undo_edit(result_id, confirmed=True)["id"] == model_id
        converted = server.export(result_id, "stl")
        assert converted["status"] in {"queued", "ready"}
        assert server.preview(result_id).startswith(b"glTF")


def test_mcp_does_not_bypass_api_tenant_isolation(tmp_path: Path) -> None:
    source = tmp_path / "cube.obj"
    source.write_text(trimesh.creation.box().export(file_type="obj"), encoding="utf-8")
    app = create_app(_settings(tmp_path))
    with TestClient(app) as first, TestClient(app) as second:
        owner = RealityMCPServer(api_key=_key(first, "owner@example.com"), client=first)
        other = RealityMCPServer(api_key=_key(second, "other@example.com"), client=second)
        model_id = str(owner.upload(source)["id"])
        with pytest.raises(RuntimeError, match="404"):
            other.inspect(model_id)
