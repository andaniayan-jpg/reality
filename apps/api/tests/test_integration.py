from __future__ import annotations

from pathlib import Path

import pytest
import trimesh
from fastapi.testclient import TestClient
from reality_api.config import Settings
from reality_api.main import create_app


def settings(tmp_path: Path, *, rate_limit: int = 120) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'reality.db'}",
        storage_backend="local",
        storage_root=tmp_path / "objects",
        s3_bucket=None,
        s3_endpoint_url=None,
        api_secret="test-only-secret-not-a-deployment-credential",
        environment="test",
        cors_origins=("http://testserver",),
        max_upload_bytes=10 * 1024 * 1024,
        sync_analysis_bytes=10 * 1024 * 1024,
        rate_limit_per_minute=rate_limit,
        default_quota_bytes=20 * 1024 * 1024,
    )


def account_and_key(client: TestClient, email: str) -> str:
    registered = client.post(
        "/v1/accounts", json={"email": email, "password": "secure-password-123"}
    )
    assert registered.status_code == 201, registered.text
    key = client.post("/v1/keys", json={"environment": "test"})
    assert key.status_code == 201, key.text
    raw = key.json()["key"]
    assert raw.startswith("rlt_test_")
    return raw


def upload(client: TestClient, key: str, name: str, payload: bytes) -> dict[str, object]:
    response = client.post(
        "/v1/files",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": (name, payload, "application/octet-stream")},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_real_obj_and_glb_analysis_and_tenant_isolation(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))
    with TestClient(app) as first, TestClient(app) as second:
        key_one = account_and_key(first, "one@example.com")
        key_two = account_and_key(second, "two@example.com")
        cube = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
        obj = upload(first, key_one, "cube.obj", cube.export(file_type="obj").encode())
        file_id = str(obj["id"])
        status = first.get(f"/v1/files/{file_id}", headers={"Authorization": f"Bearer {key_one}"})
        assert status.json()["status"] == "ready"
        summary = first.get(
            f"/v1/models/{file_id}/summary", headers={"Authorization": f"Bearer {key_one}"}
        )
        assert summary.status_code == 200
        assert summary.json()["format"] == "obj"
        assert summary.json()["statistics"]["mesh_parts"] == 1
        blocked = second.get(f"/v1/files/{file_id}", headers={"Authorization": f"Bearer {key_two}"})
        assert blocked.status_code == 404

        glb = trimesh.Scene(cube).export(file_type="glb")
        glb_file = upload(first, key_one, "cube.glb", glb)
        glb_summary = first.get(
            f"/v1/models/{glb_file['id']}/summary", headers={"Authorization": f"Bearer {key_one}"}
        )
        assert glb_summary.status_code == 200
        assert glb_summary.json()["format"] == "glb"


def test_step_http_analysis_uses_real_cad_backend(tmp_path: Path) -> None:
    cq = pytest.importorskip("cadquery")
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        key = account_and_key(client, "cad@example.com")
        source = tmp_path / "hole.step"
        shape = cq.Workplane("XY").box(10, 10, 10).cut(cq.Workplane("XY").cylinder(10, 2)).val()
        cq.exporters.export(shape, str(source), "STEP")
        record = upload(client, key, source.name, source.read_bytes())
        summary = client.get(
            f"/v1/models/{record['id']}/summary", headers={"Authorization": f"Bearer {key}"}
        )
        assert summary.status_code == 200
        assert summary.json()["format"] == "step"
        assert summary.json()["metadata"]["brep_preserved"] is True


def test_revocation_and_persistence_backed_rate_limit(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path, rate_limit=2))
    with TestClient(app) as client:
        key = account_and_key(client, "rate@example.com")
        cube = trimesh.creation.box()
        record = upload(client, key, "cube.obj", cube.export(file_type="obj").encode())
        headers = {"Authorization": f"Bearer {key}"}
        assert client.get(f"/v1/files/{record['id']}", headers=headers).status_code == 200
        assert client.get(f"/v1/files/{record['id']}", headers=headers).status_code == 429
        keys = client.get("/v1/keys").json()
        assert client.post(f"/v1/keys/{keys[0]['id']}/revoke").status_code == 200
        assert client.get(f"/v1/files/{record['id']}", headers=headers).status_code == 401


def test_openapi_exposes_required_model_surface(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))
    required = {
        "/v1/files",
        "/v1/files/{file_id}",
        "/v1/models/{model_id}/analyze",
        "/v1/models/{model_id}/summary",
        "/v1/models/{model_id}/parts",
        "/v1/models/{model_id}/measure",
        "/v1/models/{model_id}/distance",
        "/v1/models/{model_id}/clearance",
        "/v1/models/{model_id}/intersections",
        "/v1/models/{model_id}/convert",
    }
    with TestClient(app) as client:
        specification = client.get("/v1/openapi.json").json()
    assert required <= set(specification["paths"])


def test_dashboard_logout_revokes_its_persisted_session(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        account_and_key(client, "session@example.com")
        assert client.delete("/v1/sessions").status_code == 204
        assert client.get("/v1/keys").status_code == 401


def test_api_edit_job_creates_an_independent_real_geometry_version(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        key = account_and_key(client, "editing@example.com")
        mesh = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
        source = tmp_path / "editable.glb"
        trimesh.Scene({"block": mesh}).export(source)
        uploaded = upload(client, key, source.name, source.read_bytes())
        headers = {"Authorization": f"Bearer {key}"}
        job = client.post(
            f"/v1/models/{uploaded['id']}/edits",
            headers=headers,
            json={
                "operations": [
                    {"operation": "translate", "parameters": {"target": "block", "x": 5.0}}
                ]
            },
        )
        assert job.status_code == 202, job.text
        completed = client.get(f"/v1/edits/{job.json()['id']}", headers=headers)
        assert completed.json()["status"] == "ready"
        result_id = completed.json()["result_model_id"]
        assert result_id and result_id != uploaded["id"]
        original = client.get(f"/v1/models/{uploaded['id']}/parts", headers=headers).json()
        edited = client.get(f"/v1/models/{result_id}/parts", headers=headers).json()
        assert edited[0]["bounds"]["minimum"][0] == pytest.approx(
            original[0]["bounds"]["minimum"][0] + 5.0
        )
