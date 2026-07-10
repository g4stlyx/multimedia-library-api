from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.normalization import normalize_email, normalize_username
from app.models.user import User, UserCredential, UserRole


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email_normalized(self, email_normalized: str) -> User | None:
        return self.db.scalar(
            select(User).where(User.email_normalized == email_normalized)
        )

    def get_by_username_normalized(self, username_normalized: str) -> User | None:
        return self.db.scalar(
            select(User).where(User.username_normalized == username_normalized)
        )

    def get_by_identifier(self, identifier: str) -> User | None:
        value = identifier.strip()
        if "@" in value:
            return self.get_by_email_normalized(normalize_email(value))
        return self.get_by_username_normalized(normalize_username(value))

    def email_or_username_exists(self, *, email: str, username: str) -> bool:
        email_normalized = normalize_email(email)
        username_normalized = normalize_username(username)
        return (
            self.db.scalar(
                select(User.id).where(
                    (User.email_normalized == email_normalized)
                    | (User.username_normalized == username_normalized)
                )
            )
            is not None
        )

    def create_user(
        self,
        *,
        email: str,
        username: str,
        display_name: str | None,
        role: UserRole = UserRole.USER,
        admin_level: int | None = None,
    ) -> User:
        user = User(
            email=email.strip(),
            email_normalized=normalize_email(email),
            username=username.strip(),
            username_normalized=normalize_username(username),
            display_name=display_name.strip() if display_name else None,
            role=role,
            admin_level=admin_level,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def create_credentials(
        self,
        *,
        user_id: uuid.UUID,
        password_hash: str,
        password_hash_algorithm: str,
        password_hash_params: dict,
        password_changed_at: datetime,
    ) -> UserCredential:
        credentials = UserCredential(
            user_id=user_id,
            password_hash=password_hash,
            password_hash_algorithm=password_hash_algorithm,
            password_hash_params=password_hash_params,
            password_changed_at=password_changed_at,
        )
        self.db.add(credentials)
        self.db.flush()
        return credentials

    def update_display_name(self, *, user: User, display_name: str | None) -> User:
        user.display_name = display_name.strip() if display_name else None
        self.db.flush()
        return user
