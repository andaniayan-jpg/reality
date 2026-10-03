"""Configuration for the horizontally deployable Reality API."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    storage_backend: str
    storage_root: Path
    s3_bucket: str | None
    s3_endpoint_url: str | None
    api_secret: str
    environment: str
    cors_origins: tuple[str, ...]
    max_upload_bytes: int
    sync_analysis_bytes: int
    rate_limit_per_minute: int
    default_quota_bytes: int
    ai_daily_request_limit: int = 100
    ai_max_request_bytes: int = 12 * 1024 * 1024
    ai_enabled: bool = True
    ai_allowed_account_ids: tuple[str, ...] = ()
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_verify_service_sid: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        environment = os.getenv("REALITY_ENV", "development")
        configured_secret = os.getenv("REALITY_API_SECRET")
        if environment == "production" and not configured_secret:
            raise RuntimeError("REALITY_API_SECRET must be configured in production")
        # A random development secret is safer than a baked-in credential. It is
        # intentionally not stable across a process restart.
        api_secret = configured_secret or secrets.token_urlsafe(48)
        origins = tuple(
            origin.strip()
            for origin in os.getenv("REALITY_CORS_ORIGINS", "http://localhost:3000").split(",")
            if origin.strip()
        )
        ai_daily_limit = int(os.getenv("REALITY_AI_DAILY_REQUEST_LIMIT", "100"))
        ai_max_request_bytes = int(os.getenv("REALITY_AI_MAX_REQUEST_BYTES", str(12 * 1024**2)))
        if ai_daily_limit <= 0 or ai_max_request_bytes <= 0:
            raise ValueError("AI request limits must be positive")
        enabled_default = "false" if environment == "production" else "true"
        ai_enabled = os.getenv("REALITY_AI_ENABLED", enabled_default).lower() == "true"
        ai_allowed_accounts = tuple(
            account.strip()
            for account in os.getenv("REALITY_AI_ALLOWED_ACCOUNT_IDS", "").split(",")
            if account.strip()
        )
        if environment == "production" and ai_enabled and not ai_allowed_accounts:
            raise RuntimeError("production AI requires REALITY_AI_ALLOWED_ACCOUNT_IDS")
        return cls(
            database_url=os.getenv("REALITY_DATABASE_URL", "sqlite:///./reality-api.db"),
            storage_backend=os.getenv("REALITY_STORAGE_BACKEND", "local"),
            storage_root=Path(os.getenv("REALITY_STORAGE_ROOT", "./.reality-storage")),
            s3_bucket=os.getenv("REALITY_S3_BUCKET"),
            s3_endpoint_url=os.getenv("REALITY_S3_ENDPOINT_URL"),
            api_secret=api_secret,
            environment=environment,
            cors_origins=origins,
            max_upload_bytes=int(os.getenv("REALITY_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024))),
            sync_analysis_bytes=int(
                os.getenv("REALITY_SYNC_ANALYSIS_BYTES", str(16 * 1024 * 1024))
            ),
            rate_limit_per_minute=int(os.getenv("REALITY_RATE_LIMIT_PER_MINUTE", "120")),
            default_quota_bytes=int(os.getenv("REALITY_DEFAULT_QUOTA_BYTES", str(5 * 1024**3))),
            ai_daily_request_limit=ai_daily_limit,
            ai_max_request_bytes=ai_max_request_bytes,
            ai_enabled=ai_enabled,
            ai_allowed_account_ids=ai_allowed_accounts,
            twilio_account_sid=os.getenv("REALITY_TWILIO_ACCOUNT_SID"),
            twilio_auth_token=os.getenv("REALITY_TWILIO_AUTH_TOKEN"),
            twilio_verify_service_sid=os.getenv("REALITY_TWILIO_VERIFY_SERVICE_SID"),
        )
