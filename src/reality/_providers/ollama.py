"""Local HTTP inference against a user-installed engine."""

from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import SYSTEM_GUIDANCE, AITask, AIUnavailableError, RetryableProviderError


class OllamaProvider:
    """No subprocess installation, model download, or network call at import."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 120.0) -> None:
        if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("local runtime URL must use loopback")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, payload: dict[str, object] | None = None) -> object:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code in {429, 500, 502, 503, 504}:
                raise RetryableProviderError("local AI engine is temporarily busy") from error
            raise AIUnavailableError("local AI request was rejected") from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise AIUnavailableError("local AI engine is not available") from error

    def available_models(self) -> tuple[str, ...]:
        """List models already installed; never pull one implicitly."""
        response = self._request("/api/tags")
        if not isinstance(response, dict) or not isinstance(response.get("models"), list):
            raise AIUnavailableError("local AI engine returned an invalid model list")
        models: list[str] = []
        for item in response["models"]:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                models.append(item["name"])
        return tuple(models)

    def complete(self, task: AITask, *, model: str) -> str:
        message: dict[str, object] = {"role": "user", "content": task.prompt}
        if task.image is not None:
            message["images"] = [base64.b64encode(task.image).decode("ascii")]
        response = self._request(
            "/api/chat",
            {
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": SYSTEM_GUIDANCE},
                    message,
                ],
            },
        )
        if not isinstance(response, dict) or not isinstance(response.get("message"), dict):
            raise AIUnavailableError("local AI engine returned an invalid response")
        content = response["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIUnavailableError("local AI engine returned no text")
        return content
