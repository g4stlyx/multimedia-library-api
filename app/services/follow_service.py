from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.follow_repository import FollowRepository
from app.repositories.user_repository import UserRepository


class FollowService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.follows = FollowRepository(db)
        self.users = UserRepository(db)

    def follow(self, *, follower: User, followed_id: uuid.UUID) -> None:
        if follower.id == followed_id:
            raise ValueError("You cannot follow yourself")
        followed = self.users.get_by_id(followed_id)
        if followed is None or followed.deleted_at is not None or not followed.is_active or followed.is_banned:
            raise LookupError("User not found")
        if self.follows.is_following(follower_id=follower.id, followed_id=followed_id):
            return
        try:
            self.follows.create(follower_id=follower.id, followed_id=followed_id)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def unfollow(self, *, follower: User, followed_id: uuid.UUID) -> bool:
        removed = self.follows.delete(follower_id=follower.id, followed_id=followed_id)
        if removed:
            self.db.commit()
        return removed
