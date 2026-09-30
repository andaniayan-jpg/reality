"""Persistence-backed processing jobs that invoke the Reality package itself."""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

import reality

from .config import Settings
from .database import Account, ApiKey, AuditLog, FileRecord, Job, RequestLog
from .serialization import model_summary, part
from .storage import ObjectStorage


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def file_view(record: FileRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "filename": record.filename,
        "size_bytes": record.size_bytes,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "error": record.error,
    }


def job_view(job: Job) -> dict[str, object]:
    return {
        "id": job.id,
        "file_id": job.file_id,
        "status": job.status,
        "kind": job.kind,
        "error": job.error,
        "result_model_id": job.result_file_id,
    }


def audit(session: Session, owner_id: str, action: str, target_type: str, target_id: str) -> None:
    session.add(
        AuditLog(owner_id=owner_id, action=action, target_type=target_type, target_id=target_id)
    )


def quota_used(session: Session, owner_id: str) -> int:
    return int(
        session.scalar(
            select(func.coalesce(func.sum(FileRecord.size_bytes), 0)).where(
                FileRecord.owner_id == owner_id
            )
        )
        or 0
    )


def validate_upload_header(filename: str, content_type: str, prefix: bytes) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    allowed = {"obj", "stl", "ply", "glb", "gltf", "step", "stp"}
    if suffix not in allowed:
        raise ValueError(f"unsupported file extension .{suffix}")
    if content_type not in {
        "",
        "application/octet-stream",
        "model/gltf-binary",
        "model/gltf+json",
        "text/plain",
    }:
        raise ValueError("unsupported content type")
    if suffix == "glb" and prefix[:4] != b"glTF":
        raise ValueError("GLB upload is missing its glTF magic header")
    if suffix in {"step", "stp"} and b"ISO-10303-21" not in prefix[:4096]:
        raise ValueError("STEP upload is missing its ISO-10303-21 header")
    if suffix == "ply" and not prefix.startswith(b"ply"):
        raise ValueError("PLY upload is missing its PLY header")
    return suffix


def save_upload(
    session: Session,
    storage: ObjectStorage,
    settings: Settings,
    owner: Account,
    filename: str,
    content_type: str,
    chunks: list[bytes],
    idempotency_key: str | None,
    *,
    parent_file_id: str | None = None,
) -> FileRecord:
    if idempotency_key:
        existing = session.scalar(
            select(FileRecord).where(
                FileRecord.owner_id == owner.id, FileRecord.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return existing
    payload = b"".join(chunks)
    if not payload:
        raise ValueError("upload is empty")
    if len(payload) > settings.max_upload_bytes:
        raise ValueError("upload exceeds configured size limit")
    if quota_used(session, owner.id) + len(payload) > owner.quota_bytes:
        raise ValueError("account storage quota exceeded")
    suffix = validate_upload_header(filename, content_type, payload[:4096])
    digest = hashlib.sha256(payload).hexdigest()
    safe_name = Path(filename).name
    record = FileRecord(
        owner_id=owner.id,
        parent_file_id=parent_file_id,
        # Keep the extension in the storage key: Reality selects a parser based
        # on extension as well as content validation, including after S3 download.
        storage_key=f"tenants/{owner.id}/objects/{digest[:2]}/{digest}.{suffix}",
        filename=safe_name,
        content_type=content_type or "application/octet-stream",
        size_bytes=len(payload),
        sha256=digest,
        status="uploaded",
        idempotency_key=idempotency_key,
    )
    with tempfile.TemporaryDirectory(prefix="reality-upload-") as directory:
        source = Path(directory) / safe_name
        source.write_bytes(payload)
        storage.put_file(record.storage_key, source)
    session.add(record)
    session.flush()
    audit(session, owner.id, "file.created", "file", record.id)
    return record


def enqueue_analysis(
    session: Session, record: FileRecord, idempotency_key: str | None = None
) -> Job:
    existing = session.scalar(
        select(Job).where(Job.file_id == record.id, Job.status.in_(("queued", "processing")))
    )
    if existing is not None:
        return existing
    record.status = "queued"
    job = Job(owner_id=record.owner_id, file_id=record.id, idempotency_key=idempotency_key)
    session.add(job)
    session.flush()
    audit(session, record.owner_id, "model.analyze.queued", "job", job.id)
    return job


def enqueue_edit(session: Session, record: FileRecord, operations: list[dict[str, object]]) -> Job:
    existing = session.scalar(
        select(Job).where(
            Job.file_id == record.id, Job.kind == "edit", Job.status.in_(("queued", "processing"))
        )
    )
    if existing is not None:
        return existing
    job = Job(
        owner_id=record.owner_id,
        file_id=record.id,
        kind="edit",
        payload_json=json.dumps(operations),
    )
    session.add(job)
    session.flush()
    audit(session, record.owner_id, "model.edit.queued", "job", job.id)
    return job


def claim_job(session: Session, job_id: str) -> bool:
    """Atomically lease a queued job across independent API and worker replicas."""
    claimed = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "queued")
        .values(status="processing", updated_at=now())
    ).rowcount
    session.commit()
    return bool(claimed)


def claim_next_job(session: Session) -> str | None:
    candidate = session.scalar(
        select(Job.id).where(Job.status == "queued").order_by(Job.created_at)
    )
    return candidate if candidate is not None and claim_job(session, candidate) else None


def process_job(session: Session, storage: ObjectStorage, settings: Settings, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise LookupError("job not found")
    if job.status == "ready":
        return job
    if job.kind == "edit":
        return process_edit_job(session, storage, settings, job)
    record = session.get(FileRecord, job.file_id)
    if record is None:
        job.status, job.error = "failed", "source file was deleted"
        return job
    # The caller has already atomically claimed this queued job.
    job.status = "processing"
    record.status = "processing"
    session.commit()
    try:
        with storage.materialize(record.storage_key) as source:
            # This is the authority for every geometry result exposed by the API.
            model = reality.open(source, max_bytes=settings.max_upload_bytes)
            record.summary_json = json.dumps(model_summary(model), default=str)
            record.parts_json = json.dumps([part(item) for item in model.parts], default=str)
        record.status = "ready"
        record.error = None
        job.status = "ready"
        job.error = None
        audit(session, record.owner_id, "model.analyze.ready", "job", job.id)
    except Exception as error:
        record.status = "failed"
        record.error = str(error)[:4000]
        job.status = "failed"
        job.error = record.error
        audit(session, record.owner_id, "model.analyze.failed", "job", job.id)
    session.commit()
    return job


def process_edit_job(session: Session, storage: ObjectStorage, settings: Settings, job: Job) -> Job:
    """Run a persisted plan through Reality's transactional editor and keep the source immutable."""
    record = session.get(FileRecord, job.file_id)
    if record is None:
        job.status, job.error = "failed", "source file was deleted"
        session.commit()
        return job
    job.status = "processing"
    session.commit()
    try:
        operations = json.loads(job.payload_json or "[]")
        with storage.materialize(record.storage_key) as source:
            model = reality.open(source, max_bytes=settings.max_upload_bytes)
            edit = model.edit()
            for item in operations:
                edit.apply(item["operation"], **item.get("parameters", {}))
            result = edit.commit()
            validation = result.validate()
            if not validation.valid:
                raise ValueError("edit validation failed: " + "; ".join(validation.errors))
            extension = (
                "step" if all(part.solid is not None for part in result.model.parts) else "glb"
            )
            with tempfile.TemporaryDirectory(prefix="reality-edit-") as directory:
                output = Path(directory) / f"edited.{extension}"
                result.model.export(output)
                payload = output.read_bytes()
        account = session.get(Account, record.owner_id)
        if account is None:
            raise ValueError("edit owner no longer exists")
        edited_file = save_upload(
            session,
            storage,
            settings,
            account,
            f"edited.{extension}",
            "application/octet-stream",
            [payload],
            None,
            parent_file_id=record.id,
        )
        edited_file.status = "ready"
        edited_file.summary_json = json.dumps(model_summary(result.model), default=str)
        edited_file.parts_json = json.dumps(
            [part(item) for item in result.model.parts], default=str
        )
        job.status = "ready"
        job.result_file_id = edited_file.id
        job.error = None
        audit(session, record.owner_id, "model.edit.ready", "job", job.id)
    except Exception as error:
        job.status = "failed"
        job.error = str(error)[:4000]
        audit(session, record.owner_id, "model.edit.failed", "job", job.id)
    session.commit()
    return job


def load_model(
    record: FileRecord, storage: ObjectStorage, settings: Settings
) -> reality.RealityModel:
    if record.status != "ready":
        raise RuntimeError("model is not ready; enqueue or wait for analysis")
    # A caller needing multiple queries gets each answer from the persisted source
    # model, not a process-local geometry cache. Workers can scale independently.
    with storage.materialize(record.storage_key) as source:
        return reality.open(source, max_bytes=settings.max_upload_bytes)


def usage(session: Session, owner: Account) -> dict[str, int]:
    requests = int(
        session.scalar(select(func.count(RequestLog.id)).where(RequestLog.owner_id == owner.id))
        or 0
    )
    keys = int(
        session.scalar(select(func.count(ApiKey.id)).where(ApiKey.owner_id == owner.id)) or 0
    )
    return {
        "stored_bytes": quota_used(session, owner.id),
        "quota_bytes": owner.quota_bytes,
        "request_count": requests,
        "keys": keys,
    }
