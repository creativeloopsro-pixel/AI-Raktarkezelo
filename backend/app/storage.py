from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from app.config import Settings, get_settings


class ObjectStorage(Protocol):
    def put_file(self, source: Path, object_key: str, content_type: str) -> None: ...

    def delete(self, object_key: str) -> None: ...

    def local_path(self, object_key: str) -> Path | None: ...

    def open_stream(self, object_key: str) -> Any | None: ...


class LocalObjectStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_key: str) -> Path:
        target = (self.root / object_key).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("Az objektumkulcs a tárolón kívülre mutat.")
        return target

    def put_file(self, source: Path, object_key: str, content_type: str) -> None:
        del content_type
        target = self._path(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def delete(self, object_key: str) -> None:
        target = self._path(object_key)
        if target.exists():
            target.unlink()

    def local_path(self, object_key: str) -> Path | None:
        target = self._path(object_key)
        return target if target.exists() else None

    def open_stream(self, object_key: str):
        target = self._path(object_key)
        return target.open("rb") if target.exists() else None


class S3ObjectStorage:
    def __init__(self, settings: Settings):
        self.bucket = settings.s3_bucket
        self.region = settings.s3_region
        self.client: BaseClient = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            create_args: dict = {"Bucket": self.bucket}
            if self.region != "us-east-1":
                create_args["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
            self.client.create_bucket(**create_args)
        self._bucket_ready = True

    def put_file(self, source: Path, object_key: str, content_type: str) -> None:
        self._ensure_bucket()
        self.client.upload_file(
            str(source),
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def local_path(self, object_key: str) -> Path | None:
        del object_key
        return None

    def open_stream(self, object_key: str):
        self._ensure_bucket()
        return self.client.get_object(Bucket=self.bucket, Key=object_key)["Body"]


@lru_cache
def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.object_store_backend.casefold() == "s3":
        return S3ObjectStorage(settings)
    return LocalObjectStorage(settings.object_store_local_path)
