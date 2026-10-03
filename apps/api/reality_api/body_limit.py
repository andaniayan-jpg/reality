"""Bound AI JSON request bodies before FastAPI parses them."""

from __future__ import annotations

import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class AIRequestBodyLimit:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in {"/v1/ai/copilot", "/v1/ai/perceive"}
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > self.max_bytes:
            await self._reject(scope, receive, send, headers)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._reject(scope, receive, send, headers)
                return
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _reject(
        self, scope: Scope, receive: Receive, send: Send, headers: dict[bytes, bytes]
    ) -> None:
        candidate = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = (
            candidate
            if candidate.isascii() and 1 <= len(candidate) <= 64
            else secrets.token_hex(16)
        )
        response = JSONResponse(
            status_code=413,
            content={
                "error": "request_rejected",
                "message": "AI request body exceeds configured limit",
                "request_id": request_id,
            },
            headers={"X-Request-Id": request_id},
        )
        await response(scope, receive, send)
