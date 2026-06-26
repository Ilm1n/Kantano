from __future__ import annotations

from pathlib import Path
from typing import Annotated, Protocol
from urllib.parse import urlparse

from fastapi import Depends

from src.config import settings
from src.s3 import S3Client, get_s3_client


class AvatarStorageError(Exception):
    pass


class AvatarStorageGateway(Protocol):
    async def upload_file(
        self,
        *,
        file_data: bytes,
        object_name: str,
        content_type: str,
    ) -> str: ...

    async def delete_file(self, object_name: str) -> None: ...

    def object_key_from_url(self, url: str | None) -> str | None: ...


class S3AvatarStorageGateway:
    def __init__(self, s3_client: S3Client) -> None:
        self._s3_client = s3_client

    async def upload_file(
        self,
        *,
        file_data: bytes,
        object_name: str,
        content_type: str,
    ) -> str:
        try:
            return await self._s3_client.upload_file(
                file_data=file_data,
                object_name=object_name,
                content_type=content_type,
            )
        except Exception as exc:
            raise AvatarStorageError() from exc

    async def delete_file(self, object_name: str) -> None:
        await self._s3_client.delete_file(object_name)

    def object_key_from_url(self, url: str | None) -> str | None:
        if not url:
            return None

        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        if settings.s3.bucket_name not in path and settings.s3.bucket_name not in parsed.netloc:
            return None

        if path.startswith(settings.s3.bucket_name):
            return path.replace(f"{settings.s3.bucket_name}/", "", 1)

        return None


class LocalAvatarStorageGateway:
    def __init__(self, storage_dir: Path, public_base_url: str) -> None:
        self._storage_dir = storage_dir.resolve()
        self._public_base_url = public_base_url.rstrip("/")

    async def upload_file(
        self,
        *,
        file_data: bytes,
        object_name: str,
        content_type: str,
    ) -> str:
        try:
            object_path = self._object_path(object_name)
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.write_bytes(file_data)
            return f"{self._public_base_url}/{object_name}"
        except Exception as exc:
            raise AvatarStorageError() from exc

    async def delete_file(self, object_name: str) -> None:
        try:
            self._object_path(object_name).unlink(missing_ok=True)
        except Exception:
            return None

    def object_key_from_url(self, url: str | None) -> str | None:
        if not url:
            return None

        parsed_url = urlparse(url)
        parsed_base = urlparse(self._public_base_url)
        base_path = parsed_base.path.strip("/")
        path = parsed_url.path.lstrip("/")

        if parsed_base.netloc and parsed_url.netloc != parsed_base.netloc:
            return None

        if base_path and path.startswith(f"{base_path}/"):
            return path.replace(f"{base_path}/", "", 1)

        return None

    def _object_path(self, object_name: str) -> Path:
        object_path = (self._storage_dir / object_name).resolve()
        if not object_path.is_relative_to(self._storage_dir):
            raise AvatarStorageError()
        return object_path


def get_avatar_storage_gateway(
    s3_client: Annotated[S3Client, Depends(get_s3_client)],
) -> AvatarStorageGateway:
    if settings.s3.backend == "s3":
        return S3AvatarStorageGateway(s3_client)

    return LocalAvatarStorageGateway(
        storage_dir=settings.s3.local_storage_dir,
        public_base_url=settings.s3.local_public_url,
    )
