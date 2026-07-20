from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.social import Review
from app.models.media import Media
from app.models.user import User
from app.services.visibility_service import VisibilityService


class ReviewRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, review_id: uuid.UUID) -> Review | None:
        stmt = select(Review).join(Media).where(
            Review.id == review_id,
            Review.deleted_at.is_(None),
            Media.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def get_active_by_user_and_media(self, user_id: uuid.UUID, media_id: uuid.UUID) -> Review | None:
        stmt = select(Review).join(Media).where(
            Review.user_id == user_id,
            Review.media_id == media_id,
            Review.deleted_at.is_(None),
            Media.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def get_any_by_user_and_media(self, user_id: uuid.UUID, media_id: uuid.UUID) -> Review | None:
        stmt = select(Review).where(
            Review.user_id == user_id,
            Review.media_id == media_id
        )
        return self.db.scalar(stmt)

    def list_reviews(
        self,
        *,
        viewer: User,
        media_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0
    ) -> list[Review]:
        stmt = select(Review).join(Media).where(
            Review.deleted_at.is_(None),
            Media.deleted_at.is_(None),
        )
        if media_id:
            stmt = stmt.where(Review.media_id == media_id)
        if user_id:
            stmt = stmt.where(Review.user_id == user_id)
        stmt = stmt.where(
            VisibilityService(self.db).readable_by(
                owner_column=Review.user_id,
                visibility_column=Review.visibility,
                viewer=viewer,
            )
        )
        stmt = stmt.order_by(Review.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def create(
        self,
        user_id: uuid.UUID,
        media_id: uuid.UUID,
        rating_value: int | None = None,
        body: str | None = None,
        contains_spoilers: bool = False,
        visibility: str = "public"
    ) -> Review:
        review = Review(
            user_id=user_id,
            media_id=media_id,
            rating_value=rating_value,
            body=body,
            contains_spoilers=contains_spoilers,
            visibility=visibility
        )
        self.db.add(review)
        self.db.flush()
        return review

    def update(self, review: Review, **kwargs) -> Review:
        for key, value in kwargs.items():
            if hasattr(review, key):
                setattr(review, key, value)
        review.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return review

    def soft_delete(self, review: Review) -> None:
        review.deleted_at = datetime.now(timezone.utc)
        self.db.flush()
