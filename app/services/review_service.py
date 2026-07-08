from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.social import Review
from app.repositories.review_repository import ReviewRepository
from app.repositories.media_repository import MediaRepository
from app.repositories.library_repository import LibraryRepository


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ReviewRepository(db)
        self.media_repo = MediaRepository(db)
        self.library_repo = LibraryRepository(db)

    def create_review(
        self,
        user_id: uuid.UUID,
        media_id: uuid.UUID,
        rating_value: int | None = None,
        body: str | None = None,
        contains_spoilers: bool = False,
        visibility: str = "public"
    ) -> Review:
        # Check media exists
        media = self.media_repo.get_by_id(media_id)
        if not media:
            raise ValueError("Media not found")

        # Check if active review exists
        active_review = self.repo.get_active_by_user_and_media(user_id, media_id)
        if active_review:
            raise ValueError("Review already exists for this media")

        # Sync with library entry if exists
        library_entry = self.library_repo.get_active_by_user_and_media(user_id, media_id)
        if library_entry and rating_value is not None:
            self.library_repo.update(library_entry, rating_value=rating_value)

        # Check if soft-deleted review exists
        deleted_review = self.repo.get_any_by_user_and_media(user_id, media_id)
        if deleted_review:
            # Restore it
            updates = {
                "rating_value": rating_value,
                "body": body,
                "contains_spoilers": contains_spoilers,
                "visibility": visibility,
                "deleted_at": None,
            }
            review = self.repo.update(deleted_review, **updates)
            self.db.commit()
            return review

        # Create new
        review = self.repo.create(
            user_id=user_id,
            media_id=media_id,
            rating_value=rating_value,
            body=body,
            contains_spoilers=contains_spoilers,
            visibility=visibility
        )
        self.db.commit()
        return review

    def update_review(
        self,
        review_id: uuid.UUID,
        user_id: uuid.UUID,
        **kwargs
    ) -> Review:
        review = self.repo.get_by_id(review_id)
        if not review:
            raise ValueError("Review not found")
        if review.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        # Sync with library entry if rating_value changes
        if "rating_value" in kwargs and kwargs["rating_value"] is not None:
            library_entry = self.library_repo.get_active_by_user_and_media(user_id, review.media_id)
            if library_entry:
                self.library_repo.update(library_entry, rating_value=kwargs["rating_value"])

        updated_review = self.repo.update(review, **kwargs)
        self.db.commit()
        return updated_review

    def delete_review(self, review_id: uuid.UUID, user_id: uuid.UUID) -> None:
        review = self.repo.get_by_id(review_id)
        if not review:
            raise ValueError("Review not found")
        if review.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        self.repo.soft_delete(review)
        self.db.commit()
