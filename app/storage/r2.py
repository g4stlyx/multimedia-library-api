from __future__ import annotations

from typing import Protocol

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings


class ObjectStorageError(RuntimeError):
    pass


class ObjectStorage(Protocol):
    def put_image(self, *, object_key: str, content: bytes, content_type: str) -> None: ...
    def get_object(self, *, object_key: str) -> tuple[bytes, str]: ...
    def delete_object(self, *, object_key: str) -> None: ...


class CloudflareR2Storage:
    def __init__(self, settings: Settings) -> None:
        required = {
            "CLOUDFLARE_R2_ACCOUNT_ID": settings.cloudflare_r2_account_id,
            "CLOUDFLARE_R2_ACCESS_KEY_ID": settings.cloudflare_r2_access_key_id,
            "CLOUDFLARE_R2_SECRET_ACCESS_KEY": settings.cloudflare_r2_secret_access_key,
            "CLOUDFLARE_R2_BUCKET": settings.cloudflare_r2_bucket,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ObjectStorageError("Cloudflare R2 is not configured")

        import boto3

        self.bucket = settings.cloudflare_r2_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.cloudflare_r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.cloudflare_r2_access_key_id,
            aws_secret_access_key=settings.cloudflare_r2_secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )

    def put_image(self, *, object_key: str, content: bytes, content_type: str) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=object_key, Body=content, ContentType=content_type,
                CacheControl="private, max-age=31536000, immutable",
            )
        except (BotoCoreError, ClientError) as error:
            raise ObjectStorageError("Could not store image") from error

    def get_object(self, *, object_key: str) -> tuple[bytes, str]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
            return response["Body"].read(), response.get("ContentType") or "application/octet-stream"
        except (BotoCoreError, ClientError) as error:
            raise ObjectStorageError("Could not retrieve image") from error

    def delete_object(self, *, object_key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
        except (BotoCoreError, ClientError) as error:
            raise ObjectStorageError("Could not delete image") from error
