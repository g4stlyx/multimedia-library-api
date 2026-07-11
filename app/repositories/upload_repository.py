from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.upload import Upload, UploadStatus
from app.models.user import User


class UploadRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_profile_image(
        self, *, user_id: uuid.UUID, object_key: str, original_filename: str | None,
        byte_size: int, sha256: str, width: int, height: int,
    ) -> Upload:
        upload = Upload(
            user_id=user_id, upload_type="profile_image", r2_object_key=object_key,
            original_filename_sanitized=original_filename, content_type="image/webp",
            byte_size=byte_size, sha256=sha256, width=width, height=height,
        )
        self.db.add(upload)
        self.db.flush()
        return upload

    def get_owned(self, *, upload_id: uuid.UUID, user_id: uuid.UUID) -> Upload | None:
        return self.db.scalar(select(Upload).where(Upload.id == upload_id, Upload.user_id == user_id))

    def set_profile_image(self, *, user: User, upload: Upload) -> Upload | None:
        previous = user.profile_image
        user.profile_image_upload_id = upload.id
        self.db.flush()
        return previous

    def mark_replaced(self, upload: Upload) -> None:
        upload.status = UploadStatus.REPLACED
        self.db.flush()

    def mark_deleted(self, upload: Upload, deleted_at: datetime) -> None:
        upload.status = UploadStatus.DELETED
        upload.deleted_at = deleted_at
        self.db.flush()
