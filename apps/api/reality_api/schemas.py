"""OpenAPI-facing request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(APIModel):
    error: str
    message: str
    request_id: str


class AccountCreate(APIModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=512)


class Login(APIModel):
    email: EmailStr
    password: str


class AccountResponse(APIModel):
    id: str
    email: EmailStr | None
    phone: str | None = None
    created_at: datetime


class PhoneStart(APIModel):
    phone: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")


class PhoneCheck(PhoneStart):
    code: str = Field(min_length=4, max_length=10, pattern=r"^[0-9]+$")


class PhoneStartResponse(APIModel):
    status: Literal["sent"]


class KeyCreate(APIModel):
    environment: Literal["test", "live"] = "test"
    scopes: list[str] = Field(
        default_factory=lambda: ["files:read", "files:write", "models:read", "models:write"]
    )


class KeyResponse(APIModel):
    id: str
    prefix: str
    environment: str
    status: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None


class KeyReveal(KeyResponse):
    key: str = Field(description="Only returned at creation or rotation time.")


class FileResponse(APIModel):
    id: str
    filename: str
    size_bytes: int
    status: Literal["uploaded", "queued", "processing", "ready", "failed"]
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class JobResponse(APIModel):
    id: str
    file_id: str
    status: Literal["queued", "processing", "ready", "failed"]
    kind: str
    error: str | None = None
    result_model_id: str | None = None


class EditOperationRequest(APIModel):
    operation: str = Field(description="Reality edit operation, for example translate or hole.")
    parameters: dict[str, Any] = Field(default_factory=dict)


class EditRequest(APIModel):
    operations: list[EditOperationRequest] = Field(min_length=1, max_length=100)


class PartReference(APIModel):
    first: str
    second: str


class MeasureRequest(APIModel):
    part: str


class LimitRequest(APIModel):
    part: str
    limit: int = Field(default=1, ge=1, le=100)


class ConvertRequest(APIModel):
    format: Literal["glb", "stl", "step"]


class StructuredResult(APIModel):
    value: Any
    measurement: float | None
    units: str
    tolerance: float
    backend: str
    reason: str
    objects: list[dict[str, Any]]
    evidence: dict[str, Any]


class UsageResponse(APIModel):
    stored_bytes: int
    quota_bytes: int
    request_count: int
    keys: int


class RequestHistory(APIModel):
    request_id: str
    method: str
    path: str
    status_code: int
    created_at: datetime


class TopologyRequest(APIModel):
    part: str | None = None
