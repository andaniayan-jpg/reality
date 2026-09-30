"""Password, session, and API-key primitives with non-reversible storage."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from .config import Settings

DEFAULT_SCOPES = ("files:read", "files:write", "models:read", "models:write")


def hash_secret(value: str, settings: Settings) -> str:
    return hmac.new(settings.api_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def verify_secret(value: str, stored_hash: str, settings: Settings) -> bool:
    return hmac.compare_digest(hash_secret(value, settings), stored_hash)


def hash_password(password: str, *, salt: str | None = None) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt.encode(), 600_000)
    return f"pbkdf2_sha256${actual_salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    algorithm, salt, stored = encoded.split("$", maxsplit=2)
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hash_password(password, salt=salt).split("$", maxsplit=2)[2]
    return hmac.compare_digest(candidate, stored)


def new_api_key(environment: str) -> tuple[str, str]:
    if environment not in {"test", "live"}:
        raise ValueError("key environment must be 'test' or 'live'")
    raw = f"rlt_{environment}_{secrets.token_urlsafe(32)}"
    return raw, raw[:17]


def new_session_token() -> tuple[str, datetime]:
    return secrets.token_urlsafe(48), datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
