from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.library import UserMediaEntry
from app.models.media import LibraryStatus
from app.repositories.library_repository import LibraryRepository
from app.repositories.media_repository import MediaRepository


class LibraryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = LibraryRepository(db)
        self.media_repo = MediaRepository(db)

    def add_to_library(
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
        # Check media exists
        media = self.media_repo.get_by_id(media_id)
        if not media:
            raise ValueError("Media not found")

        # Check if active entry exists
        active_entry = self.repo.get_active_by_user_and_media(user_id, media_id)
        if active_entry:
            raise ValueError("Library entry already exists for this media")

        # Check if soft-deleted entry exists
        deleted_entry = self.repo.get_any_by_user_and_media(user_id, media_id)
        if deleted_entry:
            # Restore it
            updates = {
                "status": status,
                "rating_value": rating_value,
                "progress_value": progress_value,
                "progress_total": progress_total,
                "progress_unit": progress_unit,
                "notes_private": notes_private,
                "is_favorite": is_favorite,
                "source": source,
                "deleted_at": None,
            }
            if status == LibraryStatus.COMPLETED and not deleted_entry.completed_at:
                updates["completed_at"] = datetime.now(timezone.utc)
            elif status == LibraryStatus.IN_PROGRESS and not deleted_entry.started_at:
                updates["started_at"] = datetime.now(timezone.utc)
            
            entry = self.repo.update(deleted_entry, **updates)
            self.db.commit()
            return entry

        # Create new
        started_at = datetime.now(timezone.utc) if status == LibraryStatus.IN_PROGRESS else None
        completed_at = datetime.now(timezone.utc) if status == LibraryStatus.COMPLETED else None
        
        entry = self.repo.create(
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
        if started_at:
            entry.started_at = started_at
        if completed_at:
            entry.completed_at = completed_at
        self.db.commit()
        return entry

    def update_entry(
        self,
        entry_id: uuid.UUID,
        user_id: uuid.UUID,
        **kwargs
    ) -> UserMediaEntry:
        entry = self.repo.get_by_id(entry_id)
        if not entry:
            raise ValueError("Library entry not found")
        if entry.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        # Automatically update started_at / completed_at on status changes
        if "status" in kwargs and kwargs["status"] != entry.status:
            new_status = kwargs["status"]
            if new_status == LibraryStatus.IN_PROGRESS and not entry.started_at:
                kwargs["started_at"] = datetime.now(timezone.utc)
            elif new_status == LibraryStatus.COMPLETED:
                if not entry.started_at:
                    kwargs["started_at"] = datetime.now(timezone.utc)
                if not entry.completed_at:
                    kwargs["completed_at"] = datetime.now(timezone.utc)

        updated_entry = self.repo.update(entry, **kwargs)
        self.db.commit()
        return updated_entry

    def remove_from_library(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> None:
        entry = self.repo.get_by_id(entry_id)
        if not entry:
            raise ValueError("Library entry not found")
        if entry.user_id != user_id:
            raise PermissionError("Insufficient permissions")
        
        self.repo.soft_delete(entry)
        self.db.commit()
