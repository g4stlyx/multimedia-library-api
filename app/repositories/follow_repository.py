from __future__ import annotations

import uuid

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.models.follow import UserFollow
from app.models.user import User


class FollowRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_following(self, *, follower_id: uuid.UUID, followed_id: uuid.UUID) -> bool:
        return self.db.scalar(
            select(
                exists().where(
                    UserFollow.follower_id == follower_id,
                    UserFollow.followed_id == followed_id,
                )
            )
        ) is True

    def create(self, *, follower_id: uuid.UUID, followed_id: uuid.UUID) -> UserFollow:
        follow = UserFollow(follower_id=follower_id, followed_id=followed_id)
        self.db.add(follow)
        self.db.flush()
        return follow

    def delete(self, *, follower_id: uuid.UUID, followed_id: uuid.UUID) -> bool:
        result = self.db.execute(
            delete(UserFollow).where(
                UserFollow.follower_id == follower_id,
                UserFollow.followed_id == followed_id,
            )
        )
        return result.rowcount > 0

    def list_followers(self, *, user_id: uuid.UUID, limit: int, offset: int) -> list[User]:
        stmt = (
            select(User)
            .join(UserFollow, User.id == UserFollow.follower_id)
            .where(
                UserFollow.followed_id == user_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                User.is_banned.is_(False),
            )
            .order_by(UserFollow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_following(self, *, user_id: uuid.UUID, limit: int, offset: int) -> list[User]:
        stmt = (
            select(User)
            .join(UserFollow, User.id == UserFollow.followed_id)
            .where(
                UserFollow.follower_id == user_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                User.is_banned.is_(False),
            )
            .order_by(UserFollow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())
