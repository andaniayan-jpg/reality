"""Authenticated Reality Cloud transport; provider credentials remain server-side."""

from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from reality._core.auth import api_key

from .base import MAX_CLOUD_IMAGE_BYTES, AITask, AIUnavailableError, RetryableProviderError
from .openai_compatible import _image_mime


class CloudProvider:
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        normalized = base_url.rstrip("/")
        if not normalized.startswith("https://") and not normalized.startswith(
            ("http://127.0.0.1:", "http://localhost:")
        ):
            raise ValueError("cloud URL requires HTTPS except for loopback development")
        self.base_url = normalized
        self.timeout = timeout

    def complete(self, task: AITask, *, model: str) -> str:
        del model  # model selection is a server-side concern
        key = api_key()
        if not key:
            raise AIUnavailableError("cloud authentication is not configured")
        if task.image is not None and len(task.image) > MAX_CLOUD_IMAGE_BYTES:
            raise AIUnavailableError("cloud image exceeds the 8 MiB limit")
        path = "/v1/ai/perceive" if task.image is not None else "/v1/ai/copilot"
        body: dict[str, object] = {"prompt": task.prompt}
        if task.image is not None:
            body["mime_type"] = _image_mime(task.image)
            body["image_base64"] = base64.b64encode(task.image).decode("ascii")
        else:
            body["complexity"] = task.complexity
            body["realtime"] = task.realtime
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except HTTPError as error:
            if error.code == 429:
                try:
                    details = json.loads(error.read(8192))
                except (OSError, ValueError):
                    details = None
                if (
                    isinstance(details, dict)
                    and details.get("message") == "daily AI request allowance exhausted"
                ):
                    raise AIUnavailableError("daily AI request allowance exhausted") from error
            if error.code in {429, 500, 502, 503, 504}:
                raise RetryableProviderError(
                    "cloud AI capacity is temporarily unavailable"
                ) from error
            raise AIUnavailableError("cloud AI is not available for this account") from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise AIUnavailableError("cloud AI service could not be reached") from error
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise AIUnavailableError("cloud AI returned an invalid response")
        return str(result["text"])
