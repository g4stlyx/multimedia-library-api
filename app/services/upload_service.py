from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.upload import Upload, UploadStatus
from app.models.user import User
from app.repositories.audit_repository import AuditRepository
from app.repositories.upload_repository import UploadRepository
from app.services.image_service import ImageService, ImageValidationError
from app.storage.r2 import ObjectStorage, ObjectStorageError

logger = logging.getLogger(__name__)
_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class UploadService:
    def __init__(self, db: Session, settings: Settings, storage: ObjectStorage) -> None:
        self.db = db
        self.settings = settings
        self.storage = storage
        self.uploads = UploadRepository(db)
        self.audit = AuditRepository(db)
        self.images = ImageService(settings)

    @staticmethod
    def _sanitize_filename(filename: str | None) -> str | None:
        if not filename:
            return None
        sanitized = _FILENAME_SAFE.sub("_", filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]).strip("._")
        return sanitized[:255] or None

    @staticmethod
    def _object_key(user_id: uuid.UUID) -> str:
        return f"profile-images/{user_id}/{uuid.uuid4().hex}.webp"

    def upload_profile_image(
        self, *, user: User, file_content: bytes, filename: str | None, request_id: str | None,
    ) -> Upload:
        image = self.images.process_profile_image(file_content)
        object_key = self._object_key(user.id)
        self.storage.put_image(object_key=object_key, content=image.content, content_type=image.content_type)
        try:
            upload = self.uploads.create_profile_image(
                user_id=user.id, object_key=object_key, original_filename=self._sanitize_filename(filename),
                byte_size=len(image.content), sha256=image.sha256, width=image.width, height=image.height,
            )
            previous = self.uploads.set_profile_image(user=user, upload=upload)
            if previous and previous.id != upload.id and previous.status == UploadStatus.ACTIVE:
                self.uploads.mark_replaced(previous)
            self.audit.create_audit_log(
                action="user.profile_image_uploaded", actor_user_id=user.id, resource_type="upload",
                resource_id=str(upload.id), metadata={"content_type": image.content_type, "byte_size": len(image.content)},
                created_at=datetime.now(timezone.utc), request_id=request_id,
            )
            self.db.commit()
            self.db.refresh(upload)
        except Exception:
            self.db.rollback()
            try:
                self.storage.delete_object(object_key=object_key)
            except ObjectStorageError:
                logger.exception("profile_image_rollback_cleanup_failed", extra={"user_id": str(user.id)})
            raise

        if previous and previous.id != upload.id and previous.status == UploadStatus.REPLACED:
            try:
                self.storage.delete_object(object_key=previous.r2_object_key)
                self.uploads.mark_deleted(previous, datetime.now(timezone.utc))
                self.db.commit()
            except ObjectStorageError:
                self.db.rollback()
                logger.exception("replaced_profile_image_cleanup_failed", extra={"upload_id": str(previous.id)})
        return upload

    def get_owned_upload(self, *, user: User, upload_id: uuid.UUID) -> Upload:
        upload = self.uploads.get_owned(upload_id=upload_id, user_id=user.id)
        if upload is None or upload.status == UploadStatus.DELETED:
            raise LookupError("Upload not found")
        return upload

    def read_owned_upload(self, *, user: User, upload_id: uuid.UUID) -> tuple[Upload, bytes, str]:
        upload = self.get_owned_upload(user=user, upload_id=upload_id)
        content, content_type = self.storage.get_object(object_key=upload.r2_object_key)
        if content_type != upload.content_type:
            raise ObjectStorageError("Stored content type does not match upload metadata")
        return upload, content, content_type

    def delete_owned_upload(self, *, user: User, upload_id: uuid.UUID, request_id: str | None) -> None:
        upload = self.get_owned_upload(user=user, upload_id=upload_id)
        if user.profile_image_upload_id == upload.id:
            user.profile_image_upload_id = None
        self.uploads.mark_replaced(upload)
        self.audit.create_audit_log(
            action="user.upload_deleted", actor_user_id=user.id, resource_type="upload", resource_id=str(upload.id),
            created_at=datetime.now(timezone.utc), request_id=request_id,
        )
        self.db.commit()
        try:
            self.storage.delete_object(object_key=upload.r2_object_key)
            self.uploads.mark_deleted(upload, datetime.now(timezone.utc))
            self.db.commit()
        except ObjectStorageError:
            self.db.rollback()
            logger.exception("upload_cleanup_failed", extra={"upload_id": str(upload.id)})
