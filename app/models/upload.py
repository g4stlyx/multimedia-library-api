from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class UploadStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REPLACED = "REPLACED"
    DELETED = "DELETED"


class Upload(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "uploads"
    __table_args__ = (
        Index("ix_uploads_user_created_at", "user_id", "created_at"),
        Index("ix_uploads_r2_object_key", "r2_object_key", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    upload_type: Mapped[str] = mapped_column(String(50), nullable=False)
    r2_object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename_sanitized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[UploadStatus] = mapped_column(Enum(UploadStatus, name="upload_status"), nullable=False, default=UploadStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="uploads", foreign_keys=[user_id])
