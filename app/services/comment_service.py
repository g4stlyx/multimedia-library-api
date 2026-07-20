from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.social import Comment
from app.models.user import User
from app.repositories.comment_repository import CommentRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.list_repository import ListRepository
from app.repositories.media_repository import MediaRepository
from app.services.visibility_service import VisibilityService


class CommentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = CommentRepository(db)
        self.review_repo = ReviewRepository(db)
        self.list_repo = ListRepository(db)
        self.media_repo = MediaRepository(db)

    def _verify_target_exists(self, target_type: str, target_id: uuid.UUID) -> None:
        t_type = target_type.strip().lower()
        if t_type == "review":
            review = self.review_repo.get_by_id(target_id)
            if not review:
                raise ValueError("Review not found")
        elif t_type == "list":
            mlist = self.list_repo.get_by_id(target_id)
            if not mlist:
                raise ValueError("List not found")
        elif t_type == "media":
            media = self.media_repo.get_by_id(target_id)
            if not media:
                raise ValueError("Media not found")
        else:
            raise ValueError(f"Unsupported comment target type: {target_type}")

    def verify_target_access(self, target_type: str, target_id: uuid.UUID, viewer: User) -> None:
        t_type = target_type.strip().lower()
        self._verify_target_exists(t_type, target_id)
        target = None
        if t_type == "review":
            target = self.review_repo.get_by_id(target_id)
        elif t_type == "list":
            target = self.list_repo.get_by_id(target_id)
        if target is not None:
            VisibilityService(self.db).require_viewable(
                owner_user_id=target.user_id,
                visibility=target.visibility,
                viewer=viewer,
            )

    def add_comment(
        self,
        user: User,
        target_type: str,
        target_id: uuid.UUID,
        body: str,
        parent_comment_id: uuid.UUID | None = None
    ) -> Comment:
        self.verify_target_access(target_type, target_id, user)

        if parent_comment_id:
            parent = self.repo.get_by_id(parent_comment_id)
            if not parent:
                raise ValueError("Parent comment not found")
            if parent.target_id != target_id or parent.target_type != target_type.strip().lower():
                raise ValueError("Parent comment target mismatch")
            if parent.parent_comment_id is not None:
                raise ValueError("Only one level of comment replies is supported")

        comment = self.repo.create(
            user_id=user.id,
            target_type=target_type,
            target_id=target_id,
            body=body,
            parent_comment_id=parent_comment_id
        )

        # Update comment count on target if review
        if target_type.strip().lower() == "review":
            review = self.review_repo.get_by_id(target_id)
            if review:
                self.review_repo.update(review, comment_count=review.comment_count + 1)

        self.db.commit()
        return comment

    def update_comment(self, comment_id: uuid.UUID, user_id: uuid.UUID, body: str) -> Comment:
        comment = self.repo.get_by_id(comment_id)
        if not comment:
            raise ValueError("Comment not found")
        if comment.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        updated_comment = self.repo.update(comment, body=body)
        self.db.commit()
        return updated_comment

    def delete_comment(self, comment_id: uuid.UUID, user_id: uuid.UUID) -> None:
        comment = self.repo.get_by_id(comment_id)
        if not comment:
            raise ValueError("Comment not found")
        if comment.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        self.repo.soft_delete(comment)

        # Update comment count on target if review
        if comment.target_type == "review":
            review = self.review_repo.get_by_id(comment.target_id)
            if review:
                new_count = max(0, review.comment_count - 1)
                self.review_repo.update(review, comment_count=new_count)

        self.db.commit()
