"""AI routing contracts; these tests do not claim live provider credentials."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest

import reality
from reality._core import detector, installer
from reality._core.router import ModelRouter, select_local_model
from reality._providers.base import AITask, AIUnavailableError, RetryableProviderError
from reality._providers.cloud import CloudProvider
from reality._providers.gemini import GeminiProvider
from reality._providers.groq import GroqProvider
from reality._providers.nim import NIMProvider
from reality._providers.ollama import OllamaProvider
from reality._providers.openrouter import OpenRouterProvider


class RecordingProvider:
    def __init__(self, *, fail_retryable: bool = False) -> None:
        self.calls: list[tuple[AITask, str]] = []
        self.fail_retryable = fail_retryable

    def complete(self, task: AITask, *, model: str) -> str:
        self.calls.append((task, model))
        if self.fail_retryable:
            raise RetryableProviderError("rate limited")
        return "Model guidance, not a measured physical result."


def test_mode_detects_key_without_writing_session_to_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(reality.detect_hardware(), reality.HardwareProfile)
    monkeypatch.delenv("REALITY_API_KEY", raising=False)
    reality.logout()
    assert reality.detect_mode() == "local"
    reality.login("rlt_test_example")
    assert reality.detect_mode() == "online"
    reality.logout()
    assert reality.detect_mode() == "local"
    with pytest.raises(ValueError, match="API key"):
        reality.login()


def test_cloud_mode_fails_closed_without_deployed_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REALITY_API_KEY", "rlt_test_example")
    monkeypatch.delenv("REALITY_API_BASE", raising=False)
    with pytest.raises(AIUnavailableError, match="not deployed"):
        reality.copilot("Explain distance")


def test_router_retries_only_transient_failure_without_exposing_rate_limit() -> None:
    primary = RecordingProvider(fail_retryable=True)
    backup = RecordingProvider()
    router = ModelRouter({"groq": primary, "openrouter": backup})
    result = router.route(AITask("Explain falling objects"), mode="online")
    assert result.mode == "online"
    assert "Model guidance" in str(result)
    assert len(primary.calls) == len(backup.calls) == 1
    assert backup.calls[0][1] == "openrouter/free"
    with pytest.raises(AIUnavailableError, match="unavailable"):
        ModelRouter({"groq": primary}).route(AITask("test"), mode="online")
    gemini = RecordingProvider()
    assert ModelRouter({"gemini": gemini}).route(AITask("test"), mode="online").text


def test_local_model_selection_uses_only_installed_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REALITY_LOCAL_MODEL", raising=False)
    monkeypatch.delenv("REALITY_LOCAL_VISION_MODEL", raising=False)
    task = AITask("Describe motion")
    assert select_local_model(task, ("phi4:mini",)) == "phi4:mini"
    with pytest.raises(AIUnavailableError, match="installed"):
        select_local_model(task, ())
    vision = AITask("Describe", kind="vision", image=b"image")
    assert select_local_model(vision, ("qwen2-vl:7b",)) == "qwen2-vl:7b"


def test_hardware_probe_reports_observed_values_only(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        returncode = 0
        stdout = "NVIDIA Example, 8192\n"

    monkeypatch.setattr(detector, "_ram_bytes", lambda: 16 * 1024**3)
    monkeypatch.setattr(detector.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(detector.subprocess, "run", lambda *args, **kwargs: Completed())
    profile = reality.detect_hardware()
    assert profile.ram_bytes == 16 * 1024**3
    assert profile.vram_bytes == 8192 * 1024**2
    assert profile.gpu_name == "NVIDIA Example"
    assert profile.cpu_cores == 8


def test_setup_plan_is_read_only_and_conservative(monkeypatch: pytest.MonkeyPatch) -> None:
    class InstalledProvider:
        def available_models(self) -> tuple[str, ...]:
            return ("phi4:mini",)

    monkeypatch.setattr(
        installer,
        "detect_hardware",
        lambda: reality.HardwareProfile(16 * 1024**3, None, None, 8),
    )
    plan = reality.local_setup_plan(InstalledProvider())  # type: ignore[arg-type]
    assert plan.ready is True
    assert plan.suggested_model == "phi4:mini"
    assert plan.installed_models == ("phi4:mini",)


def test_copilot_and_perceive_use_injected_provider(tmp_path: Path) -> None:
    provider = RecordingProvider()
    router = ModelRouter({"local": provider}, local_models=("phi4:mini", "qwen2-vl:7b"))
    assert reality.copilot("What would happen?", router=router).mode == "local"
    image = tmp_path / "sample.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"data")
    result = reality.perceive.from_image(image, router=router)
    assert result.mode == "local"
    assert provider.calls[-1][0].kind == "vision"
    assert provider.calls[-1][1] == "qwen2-vl:7b"
    image.write_bytes(b"not a png")
    with pytest.raises(ValueError, match="content"):
        reality.perceive.from_image(image, router=router)


@contextmanager
def local_engine() -> Iterator[tuple[str, list[str]]]:
    paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            paths.append(self.path)
            body = json.dumps({"models": [{"name": "phi4:mini"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            paths.append(self.path)
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            assert request["model"] == "phi4:mini"
            body = json.dumps({"message": {"content": "A local answer"}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", paths
    finally:
        server.shutdown()
        worker.join(timeout=2)
        server.server_close()


def test_local_http_adapter_uses_installed_model_without_pull() -> None:
    with local_engine() as (url, paths):
        provider = OllamaProvider(url)
        models = provider.available_models()
        router = ModelRouter({"local": provider}, local_models=models)
        answer = router.route(AITask("Hello"), mode="local")
        assert str(answer) == "A local answer"
        assert paths == ["/api/tags", "/api/chat"]


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, *args: object) -> bytes:
        del args
        return json.dumps(self.payload).encode()


def test_server_provider_adapters_form_real_wire_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeHTTPResponse:
        assert timeout == 1
        requests.append(request)
        if "generativelanguage" in request.full_url:
            return FakeHTTPResponse({"candidates": [{"content": {"parts": [{"text": "Gemini"}]}}]})
        return FakeHTTPResponse({"choices": [{"message": {"content": "Chat"}}]})

    monkeypatch.setattr("reality._providers.openai_compatible.urlopen", fake_urlopen)
    monkeypatch.setattr("reality._providers.gemini.urlopen", fake_urlopen)
    image_task = AITask("Describe", kind="vision", image=b"\x89PNG\r\n\x1a\nimage")
    assert GeminiProvider("secret", timeout=1).complete(image_task, model="gemini-2.5-flash") == (
        "Gemini"
    )
    assert (
        json.loads(requests[-1].data or b"{}")["contents"][0]["parts"][1]["inline_data"][
            "mime_type"
        ]
        == "image/png"
    )
    assert json.loads(requests[-1].data or b"{}")["generationConfig"]["maxOutputTokens"] == 1024
    assert requests[-1].get_header("X-goog-api-key") == "secret"
    for provider, model in (
        (GroqProvider("secret", timeout=1), "meta-llama/llama-4-scout-17b-16e-instruct"),
        (NIMProvider("secret", timeout=1), "configured-model"),
        (OpenRouterProvider("secret", timeout=1), "openrouter/free"),
    ):
        assert provider.complete(AITask("Explain"), model=model) == "Chat"
        body = json.loads(requests[-1].data or b"{}")
        assert body["model"] == model
        assert body["max_tokens"] == 1024
        assert requests[-1].get_header("Authorization") == "Bearer secret"


def test_retryable_provider_error_does_not_expose_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rate_limited(request: Request, *, timeout: float) -> Any:
        del request, timeout
        raise HTTPError("https://example.com", 429, "secret", {}, None)

    monkeypatch.setattr("reality._providers.openai_compatible.urlopen", rate_limited)
    with pytest.raises(RetryableProviderError) as error:
        GroqProvider("secret").complete(AITask("Hello"), model="configured-model")
    assert "secret" not in str(error.value)


def test_real_adapter_fallback_on_transient_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeHTTPResponse:
        del timeout
        urls.append(request.full_url)
        if "api.groq.com" in request.full_url:
            raise HTTPError(request.full_url, 429, "busy", {}, None)
        return FakeHTTPResponse({"choices": [{"message": {"content": "Fallback guidance"}}]})

    monkeypatch.setattr("reality._providers.openai_compatible.urlopen", fake_urlopen)
    router = ModelRouter(
        {"groq": GroqProvider("private"), "openrouter": OpenRouterProvider("private")}
    )
    response = router.route(AITask("Explain a joint"), mode="online")
    assert response.text == "Fallback guidance"
    assert response.mode == "online"
    assert len(urls) == 2


def test_invalid_provider_credentials_do_not_trigger_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []

    def unauthorized(request: Request, *, timeout: float) -> FakeHTTPResponse:
        del timeout
        urls.append(request.full_url)
        raise HTTPError(request.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr("reality._providers.openai_compatible.urlopen", unauthorized)
    router = ModelRouter(
        {"groq": GroqProvider("private"), "openrouter": OpenRouterProvider("private")}
    )
    with pytest.raises(AIUnavailableError, match="rejected"):
        router.route(AITask("Explain a joint"), mode="online")
    assert len(urls) == 1


def test_cloud_image_request_is_authenticated_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Request] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeHTTPResponse:
        assert timeout == 1
        requests.append(request)
        return FakeHTTPResponse({"text": "Image guidance", "mode": "online"})

    monkeypatch.setenv("REALITY_API_KEY", "rlt_test_example")
    monkeypatch.setattr("reality._providers.cloud.urlopen", fake_urlopen)
    image = b"\x89PNG\r\n\x1a\nimage"
    response = CloudProvider("https://reality.example", timeout=1).complete(
        AITask("Describe", kind="vision", image=image), model=""
    )
    assert response == "Image guidance"
    assert requests[0].full_url == "https://reality.example/v1/ai/perceive"
    assert requests[0].get_header("Authorization") == "Bearer rlt_test_example"
    body = json.loads(requests[0].data or b"{}")
    assert body["mime_type"] == "image/png"
    assert body["image_base64"] == "iVBORw0KGgppbWFnZQ=="
    with pytest.raises(AIUnavailableError, match="8 MiB"):
        CloudProvider("https://reality.example").complete(
            AITask("Describe", kind="vision", image=b"x" * (8 * 1024 * 1024 + 1)), model=""
        )
