"""Create a super admin user if no admin accounts exist.

Example: python -m scripts.create_admin
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import (
    PASSWORD_HASH_ALGORITHM,
    hash_password,
    password_hash_params,
    utcnow,
)
from app.database import SessionLocal
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        user_repo = UserRepository(db)
        
        # Check if any admin user exists
        stmt = select(User).where(User.role == UserRole.ADMIN)
        admin_exists = db.scalar(stmt) is not None

        if admin_exists:
            print("An admin user already exists in the database. No actions taken.")
            return

        print("No admin users found. Creating super administrator account...")
        
        admin_email = "admin@example.com"
        admin_username = "g4stly"
        admin_password = "12345678"

        # Create user record
        user = user_repo.create_user(
            email=admin_email,
            username=admin_username,
            display_name="Super Admin",
            role=UserRole.ADMIN,
            admin_level=0,  # Level 0 (Super Admin)
        )
        
        # Mark email as verified immediately
        now = utcnow()
        user.email_verified_at = now
        
        # Create credentials
        user_repo.create_credentials(
            user_id=user.id,
            password_hash=hash_password(admin_password, settings),
            password_hash_algorithm=PASSWORD_HASH_ALGORITHM,
            password_hash_params=password_hash_params(),
            password_changed_at=now,
        )
        
        db.commit()
        print(f"Super administrator account created successfully!")
        print(f"Username: {admin_username}")
        print(f"Email: {admin_email}")
        print(f"Password: {admin_password}")
        print(f"Role: {user.role.value} (Level {user.admin_level})")

    except Exception as err:
        db.rollback()
        print(f"Error creating admin account: {err}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
