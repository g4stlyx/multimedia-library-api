from __future__ import annotations

import uuid

from sqlalchemy import and_, exists, or_, select, true
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.permissions import is_admin_at_level
from app.models.follow import UserFollow
from app.models.user import User
from app.repositories.follow_repository import FollowRepository


class VisibilityService:
    """Centralizes owner, follower, and administrator access to social content."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def can_view(self, *, owner_user_id: uuid.UUID, visibility: str, viewer: User) -> bool:
        if owner_user_id == viewer.id or is_admin_at_level(viewer, 1):
            return True
        if visibility == "public":
            return True
        return visibility == "followers" and FollowRepository(self.db).is_following(
            follower_id=viewer.id, followed_id=owner_user_id
        )

    def readable_by(
        self,
        *,
        owner_column: ColumnElement[uuid.UUID],
        visibility_column: ColumnElement[str],
        viewer: User,
    ) -> ColumnElement[bool]:
        if is_admin_at_level(viewer, 1):
            return true()
        follows_owner = exists(
            select(UserFollow.follower_id).where(
                UserFollow.follower_id == viewer.id,
                UserFollow.followed_id == owner_column,
            )
        )
        return or_(
            visibility_column == "public",
            owner_column == viewer.id,
            and_(visibility_column == "followers", follows_owner),
        )

    def require_viewable(self, *, owner_user_id: uuid.UUID, visibility: str, viewer: User) -> None:
        if not self.can_view(owner_user_id=owner_user_id, visibility=visibility, viewer=viewer):
            raise PermissionError("This content is not available to you")
