"""Google Gemini generateContent adapter for trusted server processes."""

from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .base import (
    MAX_OUTPUT_TOKENS,
    SYSTEM_GUIDANCE,
    AITask,
    AIUnavailableError,
    RetryableProviderError,
)
from .openai_compatible import _image_mime

VISION_MODELS = ("gemini-3.8-flash", "gemini-3.6-flash")


class GeminiProvider:
    def __init__(self, api_key: str, *, timeout: float = 60.0) -> None:
        if not api_key:
            raise ValueError("provider API key is required")
        self.api_key = api_key
        self.timeout = timeout

    def complete_vision(self, task: AITask) -> str:
        """Try currently supported vision-capable endpoints in priority order.

        Provider details stay internal; callers may then try a local engine.
        """
        if task.kind != "vision":
            raise ValueError("complete_vision requires a vision task")
        for model in VISION_MODELS:
            try:
                answer = self.complete(task, model=model)
                if answer.strip():
                    return answer
            except (AIUnavailableError, RetryableProviderError):
                continue
        raise AIUnavailableError("cloud vision is unavailable")

    def complete(self, task: AITask, *, model: str) -> str:
        if not model or "/" in model:
            raise AIUnavailableError("provider model is not configured")
        parts: list[dict[str, object]] = [{"text": task.prompt}]
        if task.image is not None:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": _image_mime(task.image),
                        "data": base64.b64encode(task.image).decode("ascii"),
                    }
                }
            )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model)}:generateContent"
        request = Request(
            url,
            data=json.dumps(
                {
                    "systemInstruction": {"parts": [{"text": SYSTEM_GUIDANCE}]},
                    "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
                    "contents": [{"parts": parts}],
                }
            ).encode("utf-8"),
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
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
        if not isinstance(result, dict) or not isinstance(result.get("candidates"), list):
            raise AIUnavailableError("provider returned an invalid response")
        candidates = result["candidates"]
        if not candidates or not isinstance(candidates[0], dict):
            raise AIUnavailableError("provider returned no text")
        content = candidates[0].get("content")
        if not isinstance(content, dict) or not isinstance(content.get("parts"), list):
            raise AIUnavailableError("provider returned an invalid response")
        texts = [
            part["text"]
            for part in content["parts"]
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        if not texts:
            raise AIUnavailableError("provider returned no text")
        return "\n".join(texts)
