"""Gateway authorization and routing tests; no live model is claimed."""

from __future__ import annotations

import base64
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient
from reality_api.config import Settings
from reality_api.main import create_app

import reality
from reality._core.router import ModelRouter
from reality._providers.base import AITask, AIUnavailableError


class RecordingProvider:
    def __init__(self) -> None:
        self.tasks: list[AITask] = []

    def complete(self, task: AITask, *, model: str) -> str:
        assert model
        self.tasks.append(task)
        return "This is generated guidance, not measured physics."


def _settings(
    tmp_path: Path, *, ai_daily_limit: int = 100, ai_max_bytes: int = 12 * 1024 * 1024
) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'reality.db'}",
        storage_backend="local",
        storage_root=tmp_path / "objects",
        s3_bucket=None,
        s3_endpoint_url=None,
        api_secret="test-only-secret-not-a-deployment-credential",
        environment="test",
        cors_origins=("http://testserver",),
        max_upload_bytes=1024,
        sync_analysis_bytes=1024,
        rate_limit_per_minute=20,
        default_quota_bytes=2048,
        ai_daily_request_limit=ai_daily_limit,
        ai_max_request_bytes=ai_max_bytes,
    )


def _key(client: TestClient, scopes: list[str], email: str) -> str:
    response = client.post("/v1/accounts", json={"email": email, "password": "secure-password-123"})
    assert response.status_code == 201
    created = client.post("/v1/keys", json={"environment": "test", "scopes": scopes})
    assert created.status_code == 201
    return str(created.json()["key"])


def test_ai_gateway_requires_explicit_scope_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for variable in (
        "REALITY_GEMINI_API_KEY",
        "REALITY_GROQ_API_KEY",
        "REALITY_NIM_API_KEY",
        "REALITY_OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        ordinary_key = _key(client, ["models:read"], "ordinary@example.com")
        response = client.post(
            "/v1/ai/copilot",
            json={"prompt": "Explain a distance query"},
            headers={"Authorization": f"Bearer {ordinary_key}"},
        )
        assert response.status_code == 403
        ai_key = _key(client, ["ai:use"], "ai@example.com")
        response = client.post(
            "/v1/ai/copilot",
            json={"prompt": "Explain a distance query"},
            headers={"Authorization": f"Bearer {ai_key}"},
        )
        assert response.status_code == 503
        assert "provider" not in response.text.lower()
        usage = client.get("/v1/ai/usage", headers={"Authorization": f"Bearer {ai_key}"})
        assert usage.json()["request_count"] == 0


def test_ai_gateway_routes_authenticated_request_without_leaking_provider(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))
    provider = RecordingProvider()
    app.state.ai_router = ModelRouter({"groq": provider})
    with TestClient(app) as client:
        key = _key(client, ["ai:use"], "routed@example.com")
        response = client.post(
            "/v1/ai/copilot",
            json={"prompt": "Explain a clearance query", "complexity": "fast"},
            headers={"Authorization": f"Bearer {key}"},
        )
        key_id = client.get("/v1/keys").json()[0]["id"]
        assert client.post(f"/v1/keys/{key_id}/revoke").status_code == 200
        revoked = client.post(
            "/v1/ai/copilot",
            json={"prompt": "Explain a clearance query"},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert revoked.status_code == 401
    assert response.status_code == 200, response.text
    assert response.json() == {
        "text": "This is generated guidance, not measured physics.",
        "mode": "online",
    }
    assert len(provider.tasks) == 1
    assert provider.tasks[0].prompt == "Explain a clearance query"
    assert "groq" not in response.text.lower()


def test_image_gateway_validates_content_and_requires_ai_scope(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    provider = RecordingProvider()
    app.state.ai_router = ModelRouter({"gemini": provider})
    image = b"\x89PNG\r\n\x1a\n" + b"sample"
    payload = {
        "prompt": "Describe the visible object",
        "mime_type": "image/png",
        "image_base64": base64.b64encode(image).decode("ascii"),
    }
    with TestClient(app) as client:
        ordinary_key = _key(client, ["models:read"], "ordinary-image@example.com")
        denied = client.post(
            "/v1/ai/perceive",
            json=payload,
            headers={"Authorization": f"Bearer {ordinary_key}"},
        )
        assert denied.status_code == 403
        ai_key = _key(client, ["ai:use"], "image@example.com")
        headers = {"Authorization": f"Bearer {ai_key}"}
        bad = client.post(
            "/v1/ai/perceive", json={**payload, "mime_type": "image/jpeg"}, headers=headers
        )
        assert bad.status_code == 422
        assert not provider.tasks
        good = client.post("/v1/ai/perceive", json=payload, headers=headers)
        assert good.status_code == 200, good.text
        assert good.json()["mode"] == "online"
        assert provider.tasks[0].kind == "vision"
        assert provider.tasks[0].image == image


def test_ai_daily_allowance_is_persistent_and_account_scoped(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, ai_daily_limit=2))
    provider = RecordingProvider()
    app.state.ai_router = ModelRouter({"groq": provider})
    with TestClient(app) as client:
        first_key = _key(client, ["ai:use"], "quota@example.com")
        second_key_response = client.post(
            "/v1/keys", json={"environment": "test", "scopes": ["ai:use"]}
        )
        assert second_key_response.status_code == 201
        second_key = str(second_key_response.json()["key"])
        payload = {"prompt": "Explain clearance"}
        for key in (first_key, second_key):
            accepted = client.post(
                "/v1/ai/copilot", json=payload, headers={"Authorization": f"Bearer {key}"}
            )
            assert accepted.status_code == 200
        rejected = client.post(
            "/v1/ai/copilot",
            json=payload,
            headers={"Authorization": f"Bearer {first_key}"},
        )
        assert rejected.status_code == 429
        assert len(provider.tasks) == 2
        usage = client.get("/v1/ai/usage", headers={"Authorization": f"Bearer {first_key}"}).json()
        assert usage["request_count"] == 2
        assert usage["daily_limit"] == 2
        assert usage["prompt_chars"] == 2 * len(payload["prompt"])
        assert usage["output_chars"] == 2 * len("This is generated guidance, not measured physics.")
        unrelated_key = _key(client, ["ai:use"], "unrelated@example.com")
        unrelated = client.post(
            "/v1/ai/copilot",
            json=payload,
            headers={"Authorization": f"Bearer {unrelated_key}"},
        )
        assert unrelated.status_code == 200
    restarted = create_app(_settings(tmp_path, ai_daily_limit=2))
    restarted.state.ai_router = ModelRouter({"groq": provider})
    with TestClient(restarted) as client:
        still_exhausted = client.post(
            "/v1/ai/copilot",
            json=payload,
            headers={"Authorization": f"Bearer {first_key}"},
        )
        assert still_exhausted.status_code == 429


def test_ai_body_limit_rejects_before_model_invocation(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, ai_max_bytes=120))
    provider = RecordingProvider()
    app.state.ai_router = ModelRouter({"groq": provider})
    with TestClient(app) as client:
        key = _key(client, ["ai:use"], "body-limit@example.com")
        response = client.post(
            "/v1/ai/copilot",
            content=b"{" + b" " * 121,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert response.headers.get("X-Request-Id")
        chunked = client.post(
            "/v1/ai/copilot",
            content=iter([b"{" + b" " * 60, b" " * 61]),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        assert chunked.status_code == 413
        assert not provider.tasks
        usage = client.get("/v1/ai/usage", headers={"Authorization": f"Bearer {key}"})
        assert usage.json()["request_count"] == 0


def test_package_client_reaches_real_gateway_over_loopback_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(_settings(tmp_path, ai_daily_limit=2))
    provider = RecordingProvider()
    app.state.ai_router = ModelRouter({"groq": provider, "gemini": provider})
    with TestClient(app) as client:
        key = _key(client, ["ai:use"], "loopback@example.com")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on")
    )
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        monkeypatch.setenv("REALITY_API_BASE", f"http://127.0.0.1:{port}")
        reality.login(key)
        assert reality.copilot("Explain distance").mode == "online"
        image = tmp_path / "tiny.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"transport fixture")
        assert reality.perceive.from_image(image).mode == "online"
        with pytest.raises(AIUnavailableError, match="daily AI request allowance"):
            reality.copilot("One more request")
        assert [task.kind for task in provider.tasks] == ["text", "vision"]
    finally:
        reality.logout()
        server.should_exit = True
        worker.join(timeout=10)
    assert not worker.is_alive()


def test_production_ai_entitlement_is_not_self_service(tmp_path: Path) -> None:
    restricted = replace(
        _settings(tmp_path),
        environment="production",
        ai_enabled=True,
        ai_allowed_account_ids=("an-approved-account-id",),
    )
    app = create_app(restricted)
    with TestClient(app, base_url="https://testserver") as client:
        registered = client.post(
            "/v1/accounts",
            json={"email": "not-approved@example.com", "password": "secure-password-123"},
        )
        assert registered.status_code == 201
        denied = client.post("/v1/keys", json={"scopes": ["ai:use"]})
        assert denied.status_code == 403
        session_denied = client.post("/v1/ai/copilot", json={"prompt": "Explain geometry"})
        assert session_denied.status_code == 403

    approved_id = str(registered.json()["id"])
    approved = replace(restricted, ai_allowed_account_ids=(approved_id,))
    approved_app = create_app(approved)
    provider = RecordingProvider()
    approved_app.state.ai_router = ModelRouter({"groq": provider})
    with TestClient(approved_app, base_url="https://testserver") as client:
        signed_in = client.post(
            "/v1/sessions",
            json={"email": "not-approved@example.com", "password": "secure-password-123"},
        )
        assert signed_in.status_code == 200
        created = client.post("/v1/keys", json={"scopes": ["ai:use"]})
        assert created.status_code == 201
        key = str(created.json()["key"])
        accepted = client.post(
            "/v1/ai/copilot",
            json={"prompt": "Explain geometry"},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert accepted.status_code == 200


def test_production_ai_config_fails_closed_without_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REALITY_ENV", "production")
    monkeypatch.setenv("REALITY_API_SECRET", "test-only-secret-not-a-deployment-credential")
    monkeypatch.setenv("REALITY_AI_ENABLED", "true")
    monkeypatch.delenv("REALITY_AI_ALLOWED_ACCOUNT_IDS", raising=False)
    with pytest.raises(RuntimeError, match="ALLOWED_ACCOUNT_IDS"):
        Settings.from_env()
