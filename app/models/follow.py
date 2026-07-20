from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserFollow(Base):
    """A directed relationship: follower_id follows followed_id."""

    __tablename__ = "user_follows"
    __table_args__ = (
        CheckConstraint("follower_id <> followed_id", name="ck_user_follows_not_self"),
        Index("ix_user_follows_followed_created", "followed_id", "created_at"),
    )

    follower_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    followed_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
