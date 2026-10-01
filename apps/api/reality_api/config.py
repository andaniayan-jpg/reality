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
            twilio_account_sid=os.getenv("REALITY_TWILIO_ACCOUNT_SID"),
            twilio_auth_token=os.getenv("REALITY_TWILIO_AUTH_TOKEN"),
            twilio_verify_service_sid=os.getenv("REALITY_TWILIO_VERIFY_SERVICE_SID"),
        )
