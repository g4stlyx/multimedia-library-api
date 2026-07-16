from __future__ import annotations

import uuid
import gzip
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token, utcnow
from app.models.user import User, UserRole, UserCredential
from app.models.media import Media, MediaType, LibraryStatus
from app.models.library import UserMediaEntry
from app.models.social import Review, Comment, ListItem
from app.repositories.user_repository import UserRepository
from app.repositories.audit_repository import AuditRepository
from app.services.admin_service import AdminService
from app.services.backup_service import BackupService


@pytest.fixture
def test_users(db_session: Session, client: TestClient) -> dict[str, User]:
    user_repo = UserRepository(db_session)
    
    # Create Super Admin (Level 0)
    super_admin = user_repo.create_user(
        email="superadmin@example.com",
        username="superadmin",
        display_name="Super Admin",
        role=UserRole.ADMIN,
        admin_level=0,
    )
    
    # Create Admin (Level 1)
    admin_user = user_repo.create_user(
        email="admin@example.com",
        username="admin",
        display_name="Admin L1",
        role=UserRole.ADMIN,
        admin_level=1,
    )
    
    # Create Regular User
    regular_user = user_repo.create_user(
        email="user@example.com",
        username="user1",
        display_name="Regular User",
        role=UserRole.USER,
        admin_level=None,
    )
    
    db_session.commit()
    
    return {
        "super_admin": super_admin,
        "admin": admin_user,
        "user": regular_user,
    }


def get_auth_headers(user: User, settings: Settings) -> dict[str, str]:
    token, _, _ = create_access_token(
        user_id=user.id,
        role=user.role.value,
        admin_level=user.admin_level,
        settings=settings,
    )
    return {"Authorization": f"Bearer {token}"}


def test_admin_route_protection(client: TestClient, test_users: dict[str, User], db_session: Session):
    settings = client.app.dependency_overrides.get(Settings) or Settings()
    
    super_headers = get_auth_headers(test_users["super_admin"], settings)
    admin_headers = get_auth_headers(test_users["admin"], settings)
    user_headers = get_auth_headers(test_users["user"], settings)

    # 1. Level 0 only endpoints: GET /admin/audit-logs
    r = client.get("/api/v1/admin/audit-logs", headers=user_headers)
    assert r.status_code == 403
    
    r = client.get("/api/v1/admin/audit-logs", headers=admin_headers)
    assert r.status_code == 403
    
    r = client.get("/api/v1/admin/audit-logs", headers=super_headers)
    assert r.status_code == 200
    assert "total" in r.json()

    # 2. Level 0 or 1 endpoints: GET /admin/users
    r = client.get("/api/v1/admin/users", headers=user_headers)
    assert r.status_code == 403
    
    r = client.get("/api/v1/admin/users", headers=admin_headers)
    assert r.status_code == 200
    
    r = client.get("/api/v1/admin/users", headers=super_headers)
    assert r.status_code == 200


def test_user_ban_endpoint(client: TestClient, test_users: dict[str, User], db_session: Session):
    settings = client.app.dependency_overrides.get(Settings) or Settings()
    admin_headers = get_auth_headers(test_users["admin"], settings)
    target_user = test_users["user"]

    # Ban user
    r = client.post(
        f"/api/v1/admin/users/{target_user.id}/ban",
        json={"banned": True},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["is_banned"] is True

    # Re-fetch from DB and verify banned
    db_session.expire_all()
    user = db_session.get(User, target_user.id)
    assert user.is_banned is True

    # Unban user
    r = client.post(
        f"/api/v1/admin/users/{target_user.id}/ban",
        json={"banned": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["is_banned"] is False


def test_admin_banning_guards(client: TestClient, test_users: dict[str, User], db_session: Session):
    settings = client.app.dependency_overrides.get(Settings) or Settings()
    admin_headers = get_auth_headers(test_users["admin"], settings)
    super_admin = test_users["super_admin"]

    # Admin level 1 tries to ban Super Admin level 0
    r = client.post(
        f"/api/v1/admin/users/{super_admin.id}/ban",
        json={"banned": True},
        headers=admin_headers,
    )
    assert r.status_code == 403


def test_role_update_endpoint(client: TestClient, test_users: dict[str, User], db_session: Session):
    settings = client.app.dependency_overrides.get(Settings) or Settings()
    super_headers = get_auth_headers(test_users["super_admin"], settings)
    target_user = test_users["user"]

    # Upgrade regular user to ADMIN Level 2
    r = client.patch(
        f"/api/v1/admin/users/{target_user.id}/role",
        json={"role": "ADMIN", "admin_level": 2},
        headers=super_headers,
    )
    assert r.status_code == 200
    assert r.json()["role"] == "ADMIN"
    assert r.json()["admin_level"] == 2

    # Downgrade back to USER
    r = client.patch(
        f"/api/v1/admin/users/{target_user.id}/role",
        json={"role": "USER"},
        headers=super_headers,
    )
    assert r.status_code == 200
    assert r.json()["role"] == "USER"
    assert r.json()["admin_level"] is None


def test_media_merge_service(db_session: Session):
    # Setup source and target media
    source = Media(
        media_type=MediaType.MOVIE,
        canonical_title="Original Movie",
        normalized_title="original_movie",
        release_year=2024,
    )
    target = Media(
        media_type=MediaType.MOVIE,
        canonical_title="Original Movie Canonical",
        normalized_title="original_movie_canonical",
        release_year=2024,
        metadata_json={"duplicate_candidates": [str(uuid.uuid4())]}, # dummy
    )
    db_session.add(source)
    db_session.add(target)
    db_session.commit()

    # Create dummy user
    user = User(
        email="tester@example.com",
        email_normalized="tester@example.com",
        username="tester",
        username_normalized="tester",
        role=UserRole.USER,
    )
    db_session.add(user)
    db_session.commit()

    # Create entries referencing source
    entry = UserMediaEntry(
        user_id=user.id,
        media_id=source.id,
        status=LibraryStatus.COMPLETED,
    )
    db_session.add(entry)
    
    review = Review(
        user_id=user.id,
        media_id=source.id,
        rating_value=85,
        body="This was a great movie",
    )
    db_session.add(review)
    db_session.commit()

    # Run merge
    service = AdminService(db_session)
    service.merge_media(
        source_id=source.id,
        target_id=target.id,
        actor_user=user,
    )
    db_session.commit()

    # Assertions
    db_session.expire_all()
    assert source.deleted_at is not None
    assert target.deleted_at is None

    # Check migrated entry
    stmt = select(UserMediaEntry).where(UserMediaEntry.user_id == user.id)
    entries = db_session.scalars(stmt).all()
    assert len(entries) == 1
    assert entries[0].media_id == target.id
    assert entries[0].status == LibraryStatus.COMPLETED

    # Check migrated review
    stmt = select(Review).where(Review.user_id == user.id, Review.deleted_at == None)
    reviews = db_session.scalars(stmt).all()
    assert len(reviews) == 1
    assert reviews[0].media_id == target.id


@patch("app.storage.r2.CloudflareR2Storage")
def test_backup_restore_pipeline(mock_r2_class, db_session: Session):
    # Mock R2 Client and put_object
    mock_r2_instance = MagicMock()
    mock_r2_class.return_value = mock_r2_instance

    settings = Settings(
        backup_encryption_key="test_backup_key",
        jwt_secret_key="fallback_secret_key",
    )

    service = BackupService(db_session, settings)
    
    # Test encryption and decryption manually on test bytes
    test_content = b"CREATE TABLE users (id UUID PRIMARY KEY);"
    fernet = service._get_fernet()
    
    encrypted = fernet.encrypt(gzip.compress(test_content))
    restored = service.restore_backup(encrypted_bytes=encrypted)
    
    assert restored == test_content
