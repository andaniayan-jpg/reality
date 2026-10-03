"""In-process cloud-key state, never persisted by the package."""

from __future__ import annotations

import os

_session_key: str | None = None


def login(api_key: str | None = None) -> None:
    """Use an existing Reality API key for this Python process only.

    Browser sign-in cannot safely authenticate an unrelated Python process.
    A hosted device-login flow can be added when the public service exists.
    """
    global _session_key
    candidate = api_key or os.getenv("REALITY_API_KEY")
    if not candidate or not candidate.strip():
        raise ValueError("Provide a Reality API key or set REALITY_API_KEY")
    _session_key = candidate.strip()


def logout() -> None:
    """Discard the in-process key; environment configuration is untouched."""
    global _session_key
    _session_key = None


def api_key() -> str | None:
    """Return the active key without writing it to disk."""
    return _session_key or os.getenv("REALITY_API_KEY")


def detect_mode() -> str:
    """A configured key chooses cloud; otherwise use the local runtime."""
    return "online" if api_key() else "local"
