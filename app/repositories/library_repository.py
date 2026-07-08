from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.library import UserMediaEntry
from app.models.media import LibraryStatus


class LibraryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, entry_id: uuid.UUID) -> UserMediaEntry | None:
        stmt = select(UserMediaEntry).where(
            UserMediaEntry.id == entry_id,
            UserMediaEntry.deleted_at.is_(None)
        )
        return self.db.scalar(stmt)

    def get_active_by_user_and_media(self, user_id: uuid.UUID, media_id: uuid.UUID) -> UserMediaEntry | None:
        stmt = select(UserMediaEntry).where(
            UserMediaEntry.user_id == user_id,
            UserMediaEntry.media_id == media_id,
            UserMediaEntry.deleted_at.is_(None)
        )
        return self.db.scalar(stmt)

    def get_any_by_user_and_media(self, user_id: uuid.UUID, media_id: uuid.UUID) -> UserMediaEntry | None:
        stmt = select(UserMediaEntry).where(
            UserMediaEntry.user_id == user_id,
            UserMediaEntry.media_id == media_id
        )
        return self.db.scalar(stmt)

    def list_by_user(
        self,
        user_id: uuid.UUID,
        status: LibraryStatus | None = None,
        limit: int = 20,
        offset: int = 0
    ) -> list[UserMediaEntry]:
        stmt = select(UserMediaEntry).where(
            UserMediaEntry.user_id == user_id,
            UserMediaEntry.deleted_at.is_(None)
        )
        if status:
            stmt = stmt.where(UserMediaEntry.status == status)
        stmt = stmt.order_by(UserMediaEntry.updated_at.desc()).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def create(
        self,
        user_id: uuid.UUID,
        media_id: uuid.UUID,
        status: LibraryStatus,
        rating_value: int | None = None,
        progress_value: int | None = None,
        progress_total: int | None = None,
        progress_unit: str | None = None,
        notes_private: str | None = None,
        is_favorite: bool = False,
        source: str | None = None
    ) -> UserMediaEntry:
        entry = UserMediaEntry(
            user_id=user_id,
            media_id=media_id,
            status=status,
            rating_value=rating_value,
            progress_value=progress_value,
            progress_total=progress_total,
            progress_unit=progress_unit,
            notes_private=notes_private,
            is_favorite=is_favorite,
            source=source
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def update(self, entry: UserMediaEntry, **kwargs) -> UserMediaEntry:
        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        entry.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return entry

    def soft_delete(self, entry: UserMediaEntry) -> None:
        entry.deleted_at = datetime.now(timezone.utc)
        self.db.flush()
