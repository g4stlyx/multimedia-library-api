from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BackupMetadata(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "backup_metadata"
    __table_args__ = (
        Index(
            "uq_backup_metadata_active",
            "status",
            unique=True,
            postgresql_where=text("status IN ('pending', 'processing')"),
            sqlite_where=text("status IN ('pending', 'processing')"),
        ),
    )

    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
