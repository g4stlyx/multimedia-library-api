from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ImportSource(str, enum.Enum):
    LETTERBOXD = "LETTERBOXD"
    GENERIC = "GENERIC"
    STEAM = "STEAM"
    SPOTIFY = "SPOTIFY"


class ImportJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    AWAITING_RESOLUTION = "AWAITING_RESOLUTION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ImportItemStatus(str, enum.Enum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    CONFLICT = "CONFLICT"
    IMPORTED = "IMPORTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ImportJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        Index("ix_import_jobs_user_created_at", "user_id", "created_at"),
        Index("ix_import_jobs_user_source_sha256", "user_id", "source_platform", "file_sha256", unique=True),
        Index("ix_import_jobs_status_created_at", "status", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_platform: Mapped[ImportSource] = mapped_column(Enum(ImportSource, name="import_source"), nullable=False)
    status: Mapped[ImportJobStatus] = mapped_column(Enum(ImportJobStatus, name="import_job_status"), default=ImportJobStatus.PENDING, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_r2_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="import_jobs")
    items: Mapped[list["ImportItem"]] = relationship(back_populates="import_job", cascade="all, delete-orphan")


class ImportItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_items"
    __table_args__ = (
        Index("ix_import_items_job_row", "import_job_id", "row_number", unique=True),
        Index("ix_import_items_job_status", "import_job_id", "status"),
    )

    import_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    matched_media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_candidates_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resolution_action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[ImportItemStatus] = mapped_column(Enum(ImportItemStatus, name="import_item_status"), default=ImportItemStatus.PENDING, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    import_job: Mapped[ImportJob] = relationship(back_populates="items")
    matched_media: Mapped["Media | None"] = relationship("Media")
