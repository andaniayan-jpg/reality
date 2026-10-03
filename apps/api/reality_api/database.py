"""SQLAlchemy persistence shared by SQLite development and PostgreSQL production."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, inspect
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_e164: Mapped[str | None] = mapped_column(
        String(16), unique=True, index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    quota_bytes: Mapped[int] = mapped_column(Integer, default=5 * 1024**3)
    keys: Mapped[list[ApiKey]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(32), index=True)
    environment: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="active")
    scopes_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    owner: Mapped[Account] = relationship(back_populates="keys")


class SessionToken(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PhoneStartAttempt(Base):
    __tablename__ = "phone_start_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    phone_hash: Mapped[str] = mapped_column(String(128), index=True)
    ip_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    # Derived models retain their source instead of replacing it.  This enables
    # tenant-safe version history and an explicit immutable undo target.
    parent_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="uploaded")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    parts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="analyze")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    api_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    method: Mapped[str] = mapped_column(String(12))
    path: Mapped[str] = mapped_column(String(512))
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AIDailyUsage(Base):
    """UTC-day reservations shared by all API replicas for one account."""

    __tablename__ = "ai_daily_usage"

    owner_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Database:
    def __init__(self, url: str) -> None:
        connect_args: dict[str, Any] = (
            {"check_same_thread": False} if url.startswith("sqlite") else {}
        )
        self.engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
        self.sessions = sessionmaker(self.engine, autoflush=False, expire_on_commit=False)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)
        columns = {column["name"] for column in inspect(self.engine).get_columns("accounts")}
        if "phone_e164" not in columns:
            raise RuntimeError(
                "the account database is from an older Reality API schema; apply migration "
                "003_phone_auth.sql before starting this version"
            )

    def session(self) -> Generator[Session, None, None]:
        session = self.sessions()
        try:
            yield session
        finally:
            session.close()
