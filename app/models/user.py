from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role = 'ADMIN' AND admin_level IN (0, 1, 2)) "
            "OR (role = 'USER' AND admin_level IS NULL)",
            name="ck_users_role_admin_level",
        ),
        Index("ix_users_email_normalized", "email_normalized", unique=True),
        Index("ix_users_username_normalized", "username_normalized", unique=True),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        default=UserRole.USER,
        nullable=False,
    )
    admin_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    profile_image_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("uploads.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    credentials: Mapped[UserCredential | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user")
    email_verification_tokens: Mapped[list[EmailVerificationToken]] = relationship(back_populates="user")
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(back_populates="user")
    media_entries: Mapped[list[UserMediaEntry]] = relationship(
        "UserMediaEntry",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[list[Review]] = relationship(
        "Review",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list[Comment]] = relationship(
        "Comment",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    lists: Mapped[list[MediaList]] = relationship(
        "MediaList",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    uploads: Mapped[list[Upload]] = relationship(
        "Upload", back_populates="user", foreign_keys="Upload.user_id", cascade="all, delete-orphan"
    )
    profile_image: Mapped[Upload | None] = relationship(
        "Upload", foreign_keys=[profile_image_upload_id], post_update=True
    )
    import_jobs: Mapped[list[ImportJob]] = relationship(
        "ImportJob", back_populates="user", cascade="all, delete-orphan"
    )


class UserCredential(TimestampMixin, Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    password_hash_algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash_params: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="credentials")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_token_hash", "token_hash", unique=True),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_token_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    reuse_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
    replaced_by_token: Mapped[RefreshToken | None] = relationship(remote_side=[id])


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        Index("ix_email_verification_tokens_token_hash", "token_hash", unique=True),
        Index("ix_email_verification_tokens_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="email_verification_tokens")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("ix_password_reset_tokens_token_hash", "token_hash", unique=True),
        Index("ix_password_reset_tokens_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="password_reset_tokens")
