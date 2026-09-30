"""Small typed server-side client; it never exposes API keys to browsers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class RealityCloudError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Model:
    client: Reality
    id: str

    def status(self) -> dict[str, Any]:
        return self.client._request("GET", f"/v1/files/{self.id}")

    def summary(self) -> dict[str, Any]:
        return self.client._request("GET", f"/v1/models/{self.id}/summary")

    def parts(self) -> list[dict[str, Any]]:
        return self.client._request("GET", f"/v1/models/{self.id}/parts")

    def measure(self, part: str) -> dict[str, Any]:
        return self.client._request("POST", f"/v1/models/{self.id}/measure", json={"part": part})

    def distance(self, first: str, second: str) -> dict[str, Any]:
        return self.client._request(
            "POST", f"/v1/models/{self.id}/distance", json={"first": first, "second": second}
        )

    def wait(self, timeout: float = 30.0, interval: float = 0.25) -> Model:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.status()["status"]
            if state == "ready":
                return self
            if state == "failed":
                raise RealityCloudError("model analysis failed")
            time.sleep(interval)
        raise TimeoutError("model analysis did not complete before timeout")


class Reality:
    def __init__(
        self, *, api_key: str, base_url: str = "https://api.reality.dev", timeout: float = 30.0
    ) -> None:
        if not api_key.startswith("rlt_"):
            raise ValueError("Reality API keys begin with rlt_")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def upload(self, path: str | Path, *, idempotency_key: str | None = None) -> Model:
        source = Path(path)
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        with source.open("rb") as handle:
            payload = self._client.post(
                "/v1/files", files={"file": (source.name, handle)}, headers=headers
            )
        data = self._decode(payload)
        return Model(self, data["id"])

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._decode(self._client.request(method, path, **kwargs))

    @staticmethod
    def _decode(response: httpx.Response) -> Any:
        if response.is_error:
            try:
                detail = response.json().get("message", response.text)
            except ValueError:
                detail = response.text
            raise RealityCloudError(f"Reality API {response.status_code}: {detail}")
        return response.json()

    def close(self) -> None:
        self._client.close()
