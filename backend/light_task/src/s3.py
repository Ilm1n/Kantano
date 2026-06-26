from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException, status

from src.config import settings
from src.errors import ErrorCode
from src.logger import s3_logger


class S3Client:
    def __init__(self) -> None:
        self.config = settings.s3
        self.session = aioboto3.Session()

    @asynccontextmanager
    async def get_client(self) -> AsyncGenerator:
        s3_config = Config(
            region_name=self.config.region_name,
            signature_version="s3v4",
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            s3={
                "addressing_style": "path",
                "payload_signing_enabled": True,
            },
        )

        async with self.session.client(
            service_name="s3",
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
            config=s3_config,
        ) as client:
            yield client

    async def upload_file(
        self,
        file_data: bytes,
        object_name: str,
        content_type: str,
    ) -> str:
        async with self.get_client() as client:
            try:
                await client.put_object(
                    Bucket=self.config.bucket_name,
                    Key=object_name,
                    Body=file_data,
                    ContentType=content_type,
                )
                return f"{self.config.endpoint_url}/{self.config.bucket_name}/{object_name}"
            except ClientError:
                s3_logger.exception(f"S3 Upload Error for {object_name}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=ErrorCode.FILE_UPLOAD_FAILED,
                )

    async def delete_file(self, object_name: str) -> None:
        async with self.get_client() as client:
            try:
                await client.delete_object(
                    Bucket=self.config.bucket_name,
                    Key=object_name,
                )
            except ClientError:
                s3_logger.exception(f"S3 Delete Error for {object_name}")


s3_client_instance = S3Client()


def get_s3_client() -> S3Client:
    return s3_client_instance
