from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.media import MediaType


class SeedRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SeedItemStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SeedRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "seed_runs"
    __table_args__ = (
        Index("ix_seed_runs_provider_type_kind_cursor", "provider", "media_type", "seed_kind", "cursor", unique=True),
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type"), nullable=False)
    seed_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    cursor: Mapped[str] = mapped_column(String(255), nullable=False, default="initial")
    status: Mapped[SeedRunStatus] = mapped_column(Enum(SeedRunStatus, name="seed_run_status"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class SeedItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "seed_items"
    __table_args__ = (
        Index("ix_seed_items_run_provider_external", "seed_run_id", "provider", "external_id", unique=True),
        Index("ix_seed_items_run_status", "seed_run_id", "status"),
    )

    seed_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seed_runs.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[SeedItemStatus] = mapped_column(Enum(SeedItemStatus, name="seed_item_status"), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class ProviderSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "provider_snapshots"
    __table_args__ = (Index("ix_provider_snapshots_provider_external_created", "provider", "external_id", "created_at"),)

    seed_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("seed_items.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
