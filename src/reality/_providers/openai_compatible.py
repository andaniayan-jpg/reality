"""Server-side adapters for OpenAI-compatible chat completion endpoints."""

from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import (
    MAX_OUTPUT_TOKENS,
    SYSTEM_GUIDANCE,
    AITask,
    AIUnavailableError,
    RetryableProviderError,
)


def _image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise AIUnavailableError("image format is not supported by this provider")


class ChatCompletionsProvider:
    """Use only in trusted server code; the API key must never reach a browser."""

    def __init__(self, endpoint: str, api_key: str, *, timeout: float = 60.0) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("provider endpoint must use HTTPS")
        if not api_key:
            raise ValueError("provider API key is required")
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, task: AITask, *, model: str) -> str:
        if not model:
            raise AIUnavailableError("provider model is not configured")
        content: str | list[dict[str, object]] = task.prompt
        if task.image is not None:
            encoded = base64.b64encode(task.image).decode("ascii")
            image_url = f"data:{_image_mime(task.image)};base64,{encoded}"
            content = [
                {"type": "text", "text": task.prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        request = Request(
            self.endpoint,
            data=json.dumps(
                {
                    "model": model,
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "messages": [
                        {"role": "system", "content": SYSTEM_GUIDANCE},
                        {"role": "user", "content": content},
                    ],
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except HTTPError as error:
            if error.code in {408, 409, 429, 500, 502, 503, 504}:
                raise RetryableProviderError("provider temporarily unavailable") from error
            raise AIUnavailableError("provider rejected the request") from error
        except (URLError, TimeoutError, OSError) as error:
            raise RetryableProviderError("provider could not be reached") from error
        except ValueError as error:
            raise AIUnavailableError("provider returned invalid JSON") from error
        if not isinstance(result, dict):
            raise AIUnavailableError("provider returned an invalid response")
        choices = result.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AIUnavailableError("provider returned an invalid response")
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise AIUnavailableError("provider returned an invalid response")
        return str(message["content"])
