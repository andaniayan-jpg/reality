"""Object storage adapters. Database rows keep only stable storage keys."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from .config import Settings


class ObjectStorage(Protocol):
    def put_file(self, key: str, source: Path) -> None: ...

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]: ...

    def delete(self, key: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root not in candidate.parents:
            raise ValueError("storage key escapes configured storage root")
        return candidate

    def put_file(self, key: str, source: Path) -> None:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]:
        yield self._path(key)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3ObjectStorage:
    """S3-compatible adapter; credentials are supplied by the deployment environment."""

    def __init__(self, bucket: str, endpoint_url: str | None) -> None:
        try:
            import boto3
        except ImportError as error:  # pragma: no cover - deployment dependency
            raise RuntimeError("S3 storage requires boto3") from error
        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url)

    def put_file(self, key: str, source: Path) -> None:
        self.client.upload_file(str(source), self.bucket, key)

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix="reality-object-") as directory:
            path = Path(directory) / "input"
            self.client.download_file(self.bucket, key, str(path))
            yield path

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def storage_from_settings(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "local":
        return LocalObjectStorage(settings.storage_root)
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("REALITY_S3_BUCKET is required when REALITY_STORAGE_BACKEND=s3")
        return S3ObjectStorage(settings.s3_bucket, settings.s3_endpoint_url)
    raise RuntimeError(f"Unsupported REALITY_STORAGE_BACKEND: {settings.storage_backend!r}")
