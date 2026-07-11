from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.media import MediaType
from app.models.seed import ProviderSnapshot, SeedItem, SeedItemStatus, SeedRun, SeedRunStatus


class SeedRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_run(self, *, provider: str, media_type: MediaType, seed_kind: str, cursor: str | None) -> SeedRun:
        cursor_key = cursor or "initial"
        statement = select(SeedRun).where(
            SeedRun.provider == provider,
            SeedRun.media_type == media_type,
            SeedRun.seed_kind == seed_kind,
            SeedRun.cursor == cursor_key,
        ).order_by(SeedRun.created_at.desc())
        run = self.db.scalar(statement)
        if run is not None:
            return run
        run = SeedRun(provider=provider, media_type=media_type, seed_kind=seed_kind, cursor=cursor_key, status=SeedRunStatus.PENDING)
        self.db.add(run)
        try:
            self.db.flush()
            return run
        except IntegrityError:
            # The unique run key is the concurrency guard for multiple worker processes.
            self.db.rollback()
            existing = self.db.scalar(statement)
            if existing is None:
                raise
            return existing

    def get_or_create_item(self, *, seed_run_id: uuid.UUID, provider: str, external_id: str, raw_payload: dict | None, normalized_payload: dict | None) -> SeedItem:
        statement = select(SeedItem).where(
            SeedItem.seed_run_id == seed_run_id,
            SeedItem.provider == provider,
            SeedItem.external_id == external_id,
        )
        item = self.db.scalar(statement)
        if item is not None:
            return item
        item = SeedItem(seed_run_id=seed_run_id, provider=provider, external_id=external_id, raw_payload_json=raw_payload, normalized_payload_json=normalized_payload, status=SeedItemStatus.PENDING)
        self.db.add(item)
        try:
            self.db.flush()
            return item
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(statement)
            if existing is None:
                raise
            return existing

    def add_snapshot(self, *, seed_item_id: uuid.UUID | None, provider: str, external_id: str, payload: dict) -> ProviderSnapshot:
        snapshot = ProviderSnapshot(seed_item_id=seed_item_id, provider=provider, external_id=external_id, payload_json=payload)
        self.db.add(snapshot)
        self.db.flush()
        return snapshot
