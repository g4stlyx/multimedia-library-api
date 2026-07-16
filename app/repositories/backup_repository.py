from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import select, desc
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
        self.db.flush()
        return backup

    def get_by_id(self, backup_id: uuid.UUID) -> BackupMetadata | None:
        return self.db.get(BackupMetadata, backup_id)

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
            .where(BackupMetadata.status.in_(["success", "pending"]))
        )
        return len(self.db.scalars(stmt).all()) > 0
