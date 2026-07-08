from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.social import Comment


class CommentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, comment_id: uuid.UUID) -> Comment | None:
        stmt = select(Comment).where(
            Comment.id == comment_id,
            Comment.deleted_at.is_(None)
        )
        return self.db.scalar(stmt)

    def list_comments_for_target(
        self,
        target_type: str,
        target_id: uuid.UUID,
        parent_comment_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0
    ) -> list[Comment]:
        stmt = select(Comment).where(
            Comment.target_type == target_type.strip().lower(),
            Comment.target_id == target_id,
            Comment.deleted_at.is_(None)
        )
        if parent_comment_id:
            stmt = stmt.where(Comment.parent_comment_id == parent_comment_id)
        else:
            stmt = stmt.where(Comment.parent_comment_id.is_(None))
        stmt = stmt.order_by(Comment.created_at.asc()).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def create(
        self,
        user_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        body: str,
        parent_comment_id: uuid.UUID | None = None
    ) -> Comment:
        comment = Comment(
            user_id=user_id,
            target_type=target_type.strip().lower(),
            target_id=target_id,
            body=body.strip(),
            parent_comment_id=parent_comment_id
        )
        self.db.add(comment)
        self.db.flush()
        return comment

    def update(self, comment: Comment, body: str) -> Comment:
        comment.body = body.strip()
        comment.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return comment

    def soft_delete(self, comment: Comment) -> None:
        comment.deleted_at = datetime.now(timezone.utc)
        self.db.flush()
