"""Reality Cloud's versioned FastAPI service."""

from __future__ import annotations

import json
import secrets
import tempfile
from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    BackgroundTasks,
    Cookie,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .database import Account, ApiKey, Database, FileRecord, Job, RequestLog, SessionToken
from .schemas import (
    AccountCreate,
    AccountResponse,
    ConvertRequest,
    EditRequest,
    ErrorBody,
    FileResponse,
    JobResponse,
    KeyCreate,
    KeyResponse,
    KeyReveal,
    Login,
    MeasureRequest,
    PartReference,
    RequestHistory,
    StructuredResult,
    TopologyRequest,
    UsageResponse,
)
from .security import (
    DEFAULT_SCOPES,
    hash_password,
    hash_secret,
    new_api_key,
    new_session_token,
    verify_password,
    verify_secret,
)
from .serialization import result
from .services import (
    audit,
    claim_job,
    enqueue_analysis,
    enqueue_edit,
    file_view,
    job_view,
    load_model,
    process_job,
    save_upload,
    usage,
)
from .storage import ObjectStorage, storage_from_settings

ERROR_RESPONSES = {401: {"model": ErrorBody}, 404: {"model": ErrorBody}, 429: {"model": ErrorBody}}


class Principal:
    def __init__(self, account: Account, key: ApiKey | None = None) -> None:
        self.account = account
        self.key = key


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()
    database = Database(configured.database_url)
    storage = storage_from_settings(configured)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Local SQLite is convenient; production uses the same models after the
        # SQL migration has been applied to PostgreSQL.
        database.create_all()
        yield

    app = FastAPI(
        title="Reality Cloud API",
        version="0.2.0",
        description=(
            "Hosted access to Reality's deterministic 3D/CAD inspection engine. "
            "All model calculations are executed by the `reality` package."
        ),
        openapi_url="/v1/openapi.json",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = configured
    app.state.database = database
    app.state.storage = storage
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[..., Any]) -> Response:
        candidate = request.headers.get("X-Request-Id", "")
        request_id = (
            candidate
            if candidate.isascii() and 1 <= len(candidate) <= 64
            else secrets.token_hex(16)
        )
        request.state.request_id = request_id
        response = await call_next(request)
        # API-key authentication creates an immutable audit row before endpoint
        # execution. Update only its response status by request id afterwards.
        with database.sessions() as session:
            entries = session.scalars(
                select(RequestLog).where(
                    RequestLog.request_id == request_id, RequestLog.status_code == 0
                )
            ).all()
            for entry in entries:
                entry.status_code = response.status_code
            if entries:
                session.commit()
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def structured_http_error(request: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail if isinstance(error.detail, str) else "request rejected"
        code = "request_rejected" if error.status_code < 500 else "internal_error"
        return JSONResponse(
            status_code=error.status_code,
            content={"error": code, "message": detail, "request_id": request.state.request_id},
        )

    def session_dependency() -> Generator[Session, None, None]:
        yield from database.session()

    def account_from_cookie(
        session: Session,
        reality_session: Annotated[str | None, Cookie()] = None,
    ) -> Principal | None:
        if not reality_session:
            return None
        token_hash = hash_secret(reality_session, configured)
        token = session.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash))
        if (
            token is None
            or token.revoked_at is not None
            or token.expires_at < datetime.now(UTC).replace(tzinfo=None)
        ):
            return None
        account = session.get(Account, token.owner_id)
        return Principal(account) if account is not None else None

    def principal_dependency(
        request: Request,
        session: Session = Depends(session_dependency),
        authorization: Annotated[str | None, Header()] = None,
        reality_session: Annotated[str | None, Cookie()] = None,
    ) -> Principal:
        if authorization and authorization.startswith("Bearer "):
            raw_key = authorization.removeprefix("Bearer ").strip()
            if not raw_key.startswith("rlt_"):
                raise HTTPException(401, "invalid API key")
            prefix = raw_key[:17]
            candidates = session.scalars(select(ApiKey).where(ApiKey.prefix == prefix)).all()
            key = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.status == "active"
                    and verify_secret(raw_key, candidate.key_hash, configured)
                ),
                None,
            )
            if key is None:
                raise HTTPException(401, "invalid or revoked API key")
            recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
            count = int(
                session.scalar(
                    select(func.count(RequestLog.id)).where(
                        RequestLog.api_key_id == key.id, RequestLog.created_at >= recent
                    )
                )
                or 0
            )
            if count >= configured.rate_limit_per_minute:
                raise HTTPException(429, "per-key rate limit exceeded")
            account = session.get(Account, key.owner_id)
            if account is None:
                raise HTTPException(401, "API key owner is unavailable")
            key.last_used_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(
                RequestLog(
                    owner_id=account.id,
                    api_key_id=key.id,
                    request_id=request.state.request_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=0,
                )
            )
            session.commit()
            return Principal(account, key)
        principal = account_from_cookie(session, reality_session)
        if principal is None:
            raise HTTPException(
                401, "provide a bearer API key or an authenticated dashboard session"
            )
        return principal

    def account_dependency(
        principal: Principal = Depends(principal_dependency),
    ) -> Principal:
        if principal.key is not None:
            raise HTTPException(403, "dashboard session required")
        return principal

    def require_scope(scope: str) -> Callable[[Principal], Principal]:
        def check(principal: Principal = Depends(principal_dependency)) -> Principal:
            if principal.key is None:
                return principal
            scopes = json.loads(principal.key.scopes_json)
            if scope not in scopes:
                raise HTTPException(403, f"API key lacks required scope: {scope}")
            return principal

        return check

    def owned_file(session: Session, principal: Principal, file_id: str) -> FileRecord:
        record = session.get(FileRecord, file_id)
        # A 404 instead of a 403 prevents cross-tenant record enumeration.
        if record is None or record.owner_id != principal.account.id:
            raise HTTPException(404, "file or model was not found")
        return record

    def set_session_cookie(response: Response, raw_token: str) -> None:
        response.set_cookie(
            "reality_session",
            raw_token,
            httponly=True,
            secure=configured.environment == "production",
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )

    @app.get("/healthz", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    def readiness() -> dict[str, str]:
        try:
            with database.sessions() as session:
                session.execute(select(1))
        except Exception as error:
            raise HTTPException(503, "database is not ready") from error
        return {"status": "ready"}

    @app.post("/v1/accounts", response_model=AccountResponse, status_code=201, tags=["accounts"])
    def register(
        payload: AccountCreate, response: Response, session: Session = Depends(session_dependency)
    ) -> AccountResponse:
        if (
            session.scalar(select(Account).where(Account.email == payload.email.lower()))
            is not None
        ):
            raise HTTPException(409, "account already exists")
        account = Account(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            quota_bytes=configured.default_quota_bytes,
        )
        session.add(account)
        session.flush()
        raw_token, expires_at = new_session_token()
        session.add(
            SessionToken(
                owner_id=account.id,
                token_hash=hash_secret(raw_token, configured),
                expires_at=expires_at,
            )
        )
        session.commit()
        set_session_cookie(response, raw_token)
        return AccountResponse(id=account.id, email=account.email, created_at=account.created_at)

    @app.post("/v1/sessions", response_model=AccountResponse, tags=["accounts"])
    def login(
        payload: Login, response: Response, session: Session = Depends(session_dependency)
    ) -> AccountResponse:
        account = session.scalar(select(Account).where(Account.email == payload.email.lower()))
        if account is None or not verify_password(payload.password, account.password_hash):
            raise HTTPException(401, "invalid email or password")
        raw_token, expires_at = new_session_token()
        session.add(
            SessionToken(
                owner_id=account.id,
                token_hash=hash_secret(raw_token, configured),
                expires_at=expires_at,
            )
        )
        session.commit()
        set_session_cookie(response, raw_token)
        return AccountResponse(id=account.id, email=account.email, created_at=account.created_at)

    @app.delete("/v1/sessions", status_code=204, tags=["accounts"])
    def logout(
        session: Session = Depends(session_dependency),
        reality_session: Annotated[str | None, Cookie()] = None,
    ) -> Response:
        if reality_session:
            stored = session.scalar(
                select(SessionToken).where(
                    SessionToken.token_hash == hash_secret(reality_session, configured)
                )
            )
            if stored is not None:
                stored.revoked_at = datetime.now(UTC).replace(tzinfo=None)
                session.commit()
        response = Response(status_code=204)
        response.delete_cookie("reality_session")
        return response

    @app.post("/v1/keys", response_model=KeyReveal, status_code=201, tags=["keys"])
    def create_key(
        payload: KeyCreate,
        principal: Principal = Depends(account_dependency),
        session: Session = Depends(session_dependency),
    ) -> KeyReveal:
        raw_key, prefix = new_api_key(payload.environment)
        key = ApiKey(
            owner_id=principal.account.id,
            key_hash=hash_secret(raw_key, configured),
            prefix=prefix,
            environment=payload.environment,
            scopes_json=json.dumps(payload.scopes or list(DEFAULT_SCOPES)),
        )
        session.add(key)
        session.flush()
        audit(session, principal.account.id, "api_key.created", "api_key", key.id)
        session.commit()
        return KeyReveal(
            id=key.id,
            key=raw_key,
            prefix=key.prefix,
            environment=key.environment,
            status=key.status,
            scopes=json.loads(key.scopes_json),
            created_at=key.created_at,
            last_used_at=key.last_used_at,
        )

    @app.get("/v1/keys", response_model=list[KeyResponse], tags=["keys"])
    def list_keys(
        principal: Principal = Depends(account_dependency),
        session: Session = Depends(session_dependency),
    ) -> list[KeyResponse]:
        keys = session.scalars(select(ApiKey).where(ApiKey.owner_id == principal.account.id)).all()
        return [
            KeyResponse(
                id=key.id,
                prefix=key.prefix,
                environment=key.environment,
                status=key.status,
                scopes=json.loads(key.scopes_json),
                created_at=key.created_at,
                last_used_at=key.last_used_at,
            )
            for key in keys
        ]

    @app.post("/v1/keys/{key_id}/revoke", response_model=KeyResponse, tags=["keys"])
    def revoke_key(
        key_id: str,
        principal: Principal = Depends(account_dependency),
        session: Session = Depends(session_dependency),
    ) -> KeyResponse:
        key = session.get(ApiKey, key_id)
        if key is None or key.owner_id != principal.account.id:
            raise HTTPException(404, "API key was not found")
        key.status = "revoked"
        audit(session, principal.account.id, "api_key.revoked", "api_key", key.id)
        session.commit()
        return KeyResponse(
            id=key.id,
            prefix=key.prefix,
            environment=key.environment,
            status=key.status,
            scopes=json.loads(key.scopes_json),
            created_at=key.created_at,
            last_used_at=key.last_used_at,
        )

    @app.post("/v1/keys/{key_id}/rotate", response_model=KeyReveal, tags=["keys"])
    def rotate_key(
        key_id: str,
        principal: Principal = Depends(account_dependency),
        session: Session = Depends(session_dependency),
    ) -> KeyReveal:
        existing = session.get(ApiKey, key_id)
        if existing is None or existing.owner_id != principal.account.id:
            raise HTTPException(404, "API key was not found")
        existing.status = "revoked"
        raw_key, prefix = new_api_key(existing.environment)
        key = ApiKey(
            owner_id=existing.owner_id,
            key_hash=hash_secret(raw_key, configured),
            prefix=prefix,
            environment=existing.environment,
            scopes_json=existing.scopes_json,
        )
        session.add(key)
        session.flush()
        audit(session, principal.account.id, "api_key.rotated", "api_key", key.id)
        session.commit()
        return KeyReveal(
            id=key.id,
            key=raw_key,
            prefix=key.prefix,
            environment=key.environment,
            status=key.status,
            scopes=json.loads(key.scopes_json),
            created_at=key.created_at,
            last_used_at=key.last_used_at,
        )

    @app.post(
        "/v1/files",
        response_model=FileResponse,
        status_code=202,
        responses=ERROR_RESPONSES,
        tags=["files"],
    )
    async def upload_file(
        background: BackgroundTasks,
        file: Annotated[
            UploadFile, File(description="OBJ, STL, PLY, GLB, GLTF, STEP, or STP file")
        ],
        principal: Principal = Depends(require_scope("files:write")),
        session: Session = Depends(session_dependency),
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> FileResponse:
        chunks: list[bytes] = []
        total = 0
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > configured.max_upload_bytes:
                raise HTTPException(413, "upload exceeds configured size limit")
            chunks.append(chunk)
        try:
            record = save_upload(
                session,
                storage,
                configured,
                principal.account,
                file.filename or "upload",
                file.content_type or "",
                chunks,
                idempotency_key,
            )
            job = enqueue_analysis(session, record, idempotency_key)
            session.commit()
        except ValueError as error:
            session.rollback()
            raise HTTPException(422, str(error)) from error
        if record.size_bytes <= configured.sync_analysis_bytes and job.status == "queued":
            background.add_task(_background_process, database, storage, configured, job.id)
        return FileResponse(**file_view(record))

    @app.get(
        "/v1/files/{file_id}",
        response_model=FileResponse,
        responses=ERROR_RESPONSES,
        tags=["files"],
    )
    def get_file(
        file_id: str,
        principal: Principal = Depends(require_scope("files:read")),
        session: Session = Depends(session_dependency),
    ) -> FileResponse:
        return FileResponse(**file_view(owned_file(session, principal, file_id)))

    @app.delete("/v1/files/{file_id}", status_code=204, responses=ERROR_RESPONSES, tags=["files"])
    def delete_file(
        file_id: str,
        principal: Principal = Depends(require_scope("files:write")),
        session: Session = Depends(session_dependency),
    ) -> Response:
        record = owned_file(session, principal, file_id)
        storage.delete(record.storage_key)
        audit(session, principal.account.id, "file.deleted", "file", record.id)
        session.delete(record)
        session.commit()
        return Response(status_code=204)

    @app.post(
        "/v1/models/{model_id}/analyze",
        response_model=JobResponse,
        status_code=202,
        responses=ERROR_RESPONSES,
        tags=["models"],
    )
    def analyze_model(
        model_id: str,
        background: BackgroundTasks,
        principal: Principal = Depends(require_scope("models:write")),
        session: Session = Depends(session_dependency),
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> JobResponse:
        record = owned_file(session, principal, model_id)
        job = enqueue_analysis(session, record, idempotency_key)
        session.commit()
        if record.size_bytes <= configured.sync_analysis_bytes and job.status == "queued":
            background.add_task(_background_process, database, storage, configured, job.id)
        return JobResponse(**job_view(job))

    @app.post(
        "/v1/models/{model_id}/edits",
        response_model=JobResponse,
        status_code=202,
        responses=ERROR_RESPONSES,
        tags=["editing"],
    )
    def edit_model(
        model_id: str,
        payload: EditRequest,
        background: BackgroundTasks,
        principal: Principal = Depends(require_scope("models:write")),
        session: Session = Depends(session_dependency),
    ) -> JobResponse:
        record = ready_model(session, principal, model_id)
        operations = [item.model_dump() for item in payload.operations]
        job = enqueue_edit(session, record, operations)
        session.commit()
        background.add_task(_background_process, database, storage, configured, job.id)
        return JobResponse(**job_view(job))

    @app.get(
        "/v1/edits/{job_id}",
        response_model=JobResponse,
        responses=ERROR_RESPONSES,
        tags=["editing"],
    )
    def get_edit_job(
        job_id: str,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> JobResponse:
        job = session.get(Job, job_id)
        if job is None or job.owner_id != principal.account.id or job.kind != "edit":
            raise HTTPException(404, "edit job was not found")
        return JobResponse(**job_view(job))

    def ready_model(session: Session, principal: Principal, model_id: str) -> FileRecord:
        record = owned_file(session, principal, model_id)
        if record.status != "ready":
            raise HTTPException(409, "model is not ready; poll the file status and retry")
        return record

    @app.get("/v1/models/{model_id}/summary", responses=ERROR_RESPONSES, tags=["models"])
    def get_summary(
        model_id: str,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> dict[str, Any]:
        record = ready_model(session, principal, model_id)
        return json.loads(record.summary_json or "{}")

    @app.get("/v1/models/{model_id}/parts", responses=ERROR_RESPONSES, tags=["models"])
    def get_parts(
        model_id: str,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> list[dict[str, Any]]:
        record = ready_model(session, principal, model_id)
        return json.loads(record.parts_json or "[]")

    @app.get("/v1/models/{model_id}/preview", responses=ERROR_RESPONSES, tags=["models"])
    def preview(
        model_id: str,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> Response:
        """Return a generated GLB for WebGL display only, never as query evidence."""
        model = query_model(session, principal, model_id)
        with tempfile.TemporaryDirectory(prefix="reality-preview-") as directory:
            output = model.export(Path(directory) / "preview.glb")
            return Response(
                content=output.read_bytes(),
                media_type="model/gltf-binary",
                headers={"Cache-Control": "private, max-age=300"},
            )

    def query_model(session: Session, principal: Principal, model_id: str) -> Any:
        return load_model(ready_model(session, principal, model_id), storage, configured)

    @app.post(
        "/v1/models/{model_id}/measure",
        response_model=StructuredResult,
        responses=ERROR_RESPONSES,
        tags=["models"],
    )
    def measure(
        model_id: str,
        payload: MeasureRequest,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> dict[str, Any]:
        return result(query_model(session, principal, model_id).measure(payload.part))

    @app.post(
        "/v1/models/{model_id}/distance",
        response_model=StructuredResult,
        responses=ERROR_RESPONSES,
        tags=["models"],
    )
    def distance(
        model_id: str,
        payload: PartReference,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> dict[str, Any]:
        return result(
            query_model(session, principal, model_id).distance(payload.first, payload.second)
        )

    @app.post(
        "/v1/models/{model_id}/clearance",
        response_model=StructuredResult,
        responses=ERROR_RESPONSES,
        tags=["models"],
    )
    def clearance(
        model_id: str,
        payload: PartReference,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> dict[str, Any]:
        return result(
            query_model(session, principal, model_id).clearance(payload.first, payload.second)
        )

    @app.post(
        "/v1/models/{model_id}/intersections",
        response_model=list[StructuredResult],
        responses=ERROR_RESPONSES,
        tags=["models"],
    )
    def intersections(
        model_id: str,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> list[dict[str, Any]]:
        return [result(item) for item in query_model(session, principal, model_id).intersections()]

    @app.post("/v1/models/{model_id}/topology", responses=ERROR_RESPONSES, tags=["models"])
    def topology(
        model_id: str,
        payload: TopologyRequest,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> dict[str, Any]:
        return dict(query_model(session, principal, model_id).topology(payload.part))

    @app.get(
        "/v1/models/{model_id}/versions",
        response_model=list[FileResponse],
        responses=ERROR_RESPONSES,
        tags=["editing"],
    )
    def versions(
        model_id: str,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> list[FileResponse]:
        current = owned_file(session, principal, model_id)
        history = [current]
        while current.parent_file_id is not None:
            current = owned_file(session, principal, current.parent_file_id)
            history.append(current)
        return [FileResponse(**file_view(record)) for record in history]

    @app.post(
        "/v1/models/{model_id}/undo",
        response_model=FileResponse,
        responses=ERROR_RESPONSES,
        tags=["editing"],
    )
    def undo_edit(
        model_id: str,
        principal: Principal = Depends(require_scope("models:read")),
        session: Session = Depends(session_dependency),
    ) -> FileResponse:
        current = owned_file(session, principal, model_id)
        if current.parent_file_id is None:
            raise HTTPException(409, "model has no prior immutable version to undo to")
        previous = owned_file(session, principal, current.parent_file_id)
        return FileResponse(**file_view(previous))

    @app.post(
        "/v1/models/{model_id}/convert",
        response_model=FileResponse,
        status_code=202,
        responses=ERROR_RESPONSES,
        tags=["models"],
    )
    def convert(
        model_id: str,
        payload: ConvertRequest,
        background: BackgroundTasks,
        principal: Principal = Depends(require_scope("models:write")),
        session: Session = Depends(session_dependency),
    ) -> FileResponse:
        source = ready_model(session, principal, model_id)
        model = query_model(session, principal, model_id)
        with tempfile.TemporaryDirectory(prefix="reality-convert-") as directory:
            output = model.export(
                Path(directory) / f"{source.filename.rsplit('.', 1)[0]}.{payload.format}"
            )
            converted = save_upload(
                session,
                storage,
                configured,
                principal.account,
                output.name,
                "application/octet-stream",
                [output.read_bytes()],
                None,
            )
        job = enqueue_analysis(session, converted)
        session.commit()
        if converted.size_bytes <= configured.sync_analysis_bytes:
            background.add_task(_background_process, database, storage, configured, job.id)
        return FileResponse(**file_view(converted))

    @app.get("/v1/usage", response_model=UsageResponse, tags=["dashboard"])
    def get_usage(
        principal: Principal = Depends(account_dependency),
        session: Session = Depends(session_dependency),
    ) -> UsageResponse:
        return UsageResponse(**usage(session, principal.account))

    @app.get("/v1/requests", response_model=list[RequestHistory], tags=["dashboard"])
    def request_history(
        principal: Principal = Depends(account_dependency),
        session: Session = Depends(session_dependency),
    ) -> list[RequestHistory]:
        entries = session.scalars(
            select(RequestLog)
            .where(RequestLog.owner_id == principal.account.id)
            .order_by(RequestLog.created_at.desc())
            .limit(100)
        ).all()
        return [
            RequestHistory(
                request_id=item.request_id,
                method=item.method,
                path=item.path,
                status_code=item.status_code,
                created_at=item.created_at,
            )
            for item in entries
        ]

    return app


def _background_process(
    database: Database, storage: ObjectStorage, settings: Settings, job_id: str
) -> None:
    with database.sessions() as session:
        if claim_job(session, job_id):
            process_job(session, storage, settings, job_id)


app = create_app()
