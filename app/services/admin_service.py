from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.media import Media, LibraryStatus
from app.models.library import UserMediaEntry
from app.models.social import Review, Comment, ListItem
from app.models.user import User
from app.repositories.audit_repository import AuditRepository


class AdminService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditRepository(db)

    def get_duplicate_candidates(self) -> list[Media]:
        """Fetch all media items flagged with potential duplicates."""
        # Query Media records where duplicate_candidates list is present in metadata_json
        stmt = select(Media).where(Media.metadata_json["duplicate_candidates"] != None)
        return list(self.db.scalars(stmt).all())

    def merge_media(
        self,
        *,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        actor_user: User,
        request_id: str | None = None,
    ) -> Media:
        """Merge a duplicate source media into a canonical target media."""
        if source_id == target_id:
            raise ValueError("Cannot merge a media item into itself")

        source = self.db.get(Media, source_id)
        target = self.db.get(Media, target_id)

        if source is None or source.deleted_at is not None:
            raise LookupError("Source media not found or already deleted")
        if target is None or target.deleted_at is not None:
            raise LookupError("Target media not found or deleted")

        # 1. Migrate user_media_entries (Library entries)
        source_entries = self.db.scalars(
            select(UserMediaEntry).where(UserMediaEntry.media_id == source_id)
        ).all()
        for s_entry in source_entries:
            t_entry = self.db.scalar(
                select(UserMediaEntry).where(
                    UserMediaEntry.media_id == target_id,
                    UserMediaEntry.user_id == s_entry.user_id,
                )
            )
            if t_entry:
                # Merge logic: preserve target or merge higher progress/status
                if t_entry.status == LibraryStatus.PLANNED and s_entry.status != LibraryStatus.PLANNED:
                    t_entry.status = s_entry.status
                    t_entry.started_at = s_entry.started_at
                    t_entry.completed_at = s_entry.completed_at
                if not t_entry.rating_value and s_entry.rating_value:
                    t_entry.rating_value = s_entry.rating_value
                if not t_entry.notes_private and s_entry.notes_private:
                    t_entry.notes_private = s_entry.notes_private
                if s_entry.is_favorite:
                    t_entry.is_favorite = True
                self.db.delete(s_entry)
            else:
                s_entry.media_id = target_id

        # 2. Migrate reviews
        source_reviews = self.db.scalars(
            select(Review).where(Review.media_id == source_id, Review.deleted_at == None)
        ).all()
        for s_rev in source_reviews:
            t_rev = self.db.scalar(
                select(Review).where(
                    Review.media_id == target_id,
                    Review.user_id == s_rev.user_id,
                    Review.deleted_at == None,
                )
            )
            if t_rev:
                # Migrate comments of the source review to the target review
                comments = self.db.scalars(
                    select(Comment).where(
                        Comment.target_type == "review",
                        Comment.target_id == s_rev.id,
                    )
                ).all()
                for comment in comments:
                    comment.target_id = t_rev.id
                
                # Delete source review
                s_rev.deleted_at = datetime.now(timezone.utc)
            else:
                s_rev.media_id = target_id

        # 3. Migrate comments on media itself
        media_comments = self.db.scalars(
            select(Comment).where(
                Comment.target_type == "media",
                Comment.target_id == source_id,
            )
        ).all()
        for comment in media_comments:
            comment.target_id = target_id

        # 4. Migrate list items
        source_list_items = self.db.scalars(
            select(ListItem).where(ListItem.media_id == source_id)
        ).all()
        for s_li in source_list_items:
            t_li = self.db.scalar(
                select(ListItem).where(
                    ListItem.list_id == s_li.list_id,
                    ListItem.media_id == target_id,
                )
            )
            if t_li:
                self.db.delete(s_li)
            else:
                s_li.media_id = target_id

        # 5. Migrate external provider IDs
        for s_ext in list(source.external_ids):
            # Check if target already has an external ID for this provider
            t_ext = next((x for x in target.external_ids if x.provider == s_ext.provider), None)
            if t_ext:
                self.db.delete(s_ext)
            else:
                s_ext.media_id = target_id

        # 6. Migrate images
        for img in list(source.images):
            img.media_id = target_id

        # 7. Migrate titles
        for title in list(source.titles):
            # Avoid adding exact duplicate titles to target
            exists = any(
                x.normalized_title == title.normalized_title and x.language == title.language
                for x in target.titles
            )
            if exists:
                self.db.delete(title)
            else:
                title.media_id = target_id

        # 8. Migrate genres
        for genre in source.genres:
            if genre not in target.genres:
                target.genres.append(genre)

        # 9. Clean up duplicate candidates metadata on target if source is in it
        if target.metadata_json and "duplicate_candidates" in target.metadata_json:
            candidates = target.metadata_json["duplicate_candidates"]
            if str(source_id) in candidates:
                candidates.remove(str(source_id))
            target.metadata_json["duplicate_candidates"] = candidates

        # 10. Soft delete source media
        source.deleted_at = datetime.now(timezone.utc)

        # 11. Create audit log
        self.audit.create_audit_log(
            action="media.merged",
            actor_user_id=actor_user.id,
            resource_type="media",
            resource_id=str(target_id),
            metadata={
                "source_media_id": str(source_id),
                "source_title": source.canonical_title,
                "target_title": target.canonical_title,
            },
            created_at=datetime.now(timezone.utc),
            request_id=request_id,
        )

        self.db.flush()
        return target
