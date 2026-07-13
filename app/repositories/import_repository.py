from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.import_job import ImportItem, ImportItemStatus, ImportJob, ImportJobStatus, ImportSource


class ImportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_job_owned(self, *, job_id: uuid.UUID, user_id: uuid.UUID, include_items: bool = False) -> ImportJob | None:
        statement = select(ImportJob).where(ImportJob.id == job_id, ImportJob.user_id == user_id)
        if include_items:
            statement = statement.options(selectinload(ImportJob.items).selectinload(ImportItem.matched_media))
        return self.db.scalar(statement)

    def get_job(self, job_id: uuid.UUID) -> ImportJob | None:
        return self.db.get(ImportJob, job_id)

    def list_owned(self, *, user_id: uuid.UUID, limit: int, offset: int) -> list[ImportJob]:
        statement = select(ImportJob).where(ImportJob.user_id == user_id).order_by(ImportJob.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.scalars(statement).all())

    def get_idempotent_job(self, *, user_id: uuid.UUID, source: ImportSource, file_sha256: str) -> ImportJob | None:
        return self.db.scalar(select(ImportJob).where(ImportJob.user_id == user_id, ImportJob.source_platform == source, ImportJob.file_sha256 == file_sha256))

    def count_active_jobs(self, user_id: uuid.UUID) -> int:
        return int(self.db.scalar(select(func.count(ImportJob.id)).where(ImportJob.user_id == user_id, ImportJob.status.in_([ImportJobStatus.PENDING, ImportJobStatus.PROCESSING]))) or 0)

    def create_job(self, **values) -> ImportJob:
        job = ImportJob(**values)
        self.db.add(job)
        self.db.flush()
        return job

    def create_items(self, *, job_id: uuid.UUID, rows: list[dict]) -> list[ImportItem]:
        items = [ImportItem(import_job_id=job_id, row_number=row["row_number"], raw_payload_json=row) for row in rows]
        self.db.add_all(items)
        self.db.flush()
        return items

    def pending_items(self, job_id: uuid.UUID) -> list[ImportItem]:
        statement = select(ImportItem).where(ImportItem.import_job_id == job_id, ImportItem.status == ImportItemStatus.PENDING).order_by(ImportItem.row_number)
        return list(self.db.scalars(statement).all())

    def get_item_owned(self, *, item_id: uuid.UUID, job_id: uuid.UUID, user_id: uuid.UUID) -> ImportItem | None:
        statement = select(ImportItem).join(ImportJob).where(ImportItem.id == item_id, ImportItem.import_job_id == job_id, ImportJob.user_id == user_id)
        return self.db.scalar(statement)

    @staticmethod
    def set_job_status(job: ImportJob, status: ImportJobStatus, now: datetime, error_message: str | None = None) -> None:
        job.status = status
        if status == ImportJobStatus.PROCESSING and job.started_at is None:
            job.started_at = now
        if status in {ImportJobStatus.COMPLETED, ImportJobStatus.FAILED, ImportJobStatus.CANCELLED}:
            job.finished_at = now
        if error_message is not None:
            job.error_message = error_message

    @staticmethod
    def update_progress(job: ImportJob) -> None:
        statuses = [item.status for item in job.items]
        job.processed_rows = sum(status in {ImportItemStatus.IMPORTED, ImportItemStatus.SKIPPED, ImportItemStatus.FAILED, ImportItemStatus.CONFLICT} for status in statuses)
        job.successful_rows = sum(status in {ImportItemStatus.IMPORTED, ImportItemStatus.SKIPPED} for status in statuses)
        job.failed_rows = sum(status == ImportItemStatus.FAILED for status in statuses)
