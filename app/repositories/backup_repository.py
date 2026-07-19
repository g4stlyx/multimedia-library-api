from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session

from app.models.backup import BackupMetadata


class BackupRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_backup_metadata(self, *, started_at: datetime) -> BackupMetadata:
        backup = BackupMetadata(
            status="pending",
            started_at=started_at,
        )
        self.db.add(backup)
        self.db.flush()
        return backup

    def update_backup_success(
        self,
        *,
        backup: BackupMetadata,
        size_bytes: int,
        sha256: str,
        storage_key: str,
    ) -> BackupMetadata:
        backup.status = "success"
        backup.finished_at = datetime.now(timezone.utc)
        backup.size_bytes = size_bytes
        backup.sha256 = sha256
        backup.storage_key = storage_key
        backup.worker_id = None
        backup.lease_expires_at = None
        self.db.flush()
        return backup

    def update_backup_failed(
        self,
        *,
        backup: BackupMetadata,
        error_message: str,
    ) -> BackupMetadata:
        backup.status = "failed"
        backup.finished_at = datetime.now(timezone.utc)
        backup.error_message = error_message
        backup.worker_id = None
        backup.lease_expires_at = None
        self.db.flush()
        return backup

    def get_by_id(self, backup_id: uuid.UUID) -> BackupMetadata | None:
        return self.db.get(BackupMetadata, backup_id)

    def get_active_backup(self) -> BackupMetadata | None:
        return self.db.scalar(
            select(BackupMetadata)
            .where(BackupMetadata.status.in_(["pending", "processing"]))
            .order_by(BackupMetadata.started_at.asc())
        )

    def claim_next_backup(self, *, worker_id: str, lease_seconds: int) -> BackupMetadata | None:
        now = datetime.now(timezone.utc)
        backup = self.db.scalar(
            select(BackupMetadata)
            .where(
                or_(
                    BackupMetadata.status == "pending",
                    and_(
                        BackupMetadata.status == "processing",
                        BackupMetadata.lease_expires_at.is_not(None),
                        BackupMetadata.lease_expires_at < now,
                    ),
                )
            )
            .order_by(BackupMetadata.started_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if backup is None:
            return None
        backup.status = "processing"
        backup.worker_id = worker_id
        backup.lease_expires_at = now + timedelta(seconds=lease_seconds)
        backup.attempt_count += 1
        self.db.flush()
        return backup

    def list_backups(self, *, limit: int = 50, offset: int = 0) -> list[BackupMetadata]:
        stmt = (
            select(BackupMetadata)
            .order_by(desc(BackupMetadata.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_latest_backup(self) -> BackupMetadata | None:
        stmt = (
            select(BackupMetadata)
            .order_by(desc(BackupMetadata.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

    def has_recent_backup(self, *, hours: int = 20) -> bool:
        """Check if any backup was started in the last N hours."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(BackupMetadata)
            .where(BackupMetadata.started_at >= cutoff)
            .where(BackupMetadata.status.in_(["success", "pending", "processing"]))
        )
        return len(self.db.scalars(stmt).all()) > 0
