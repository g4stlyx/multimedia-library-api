from __future__ import annotations

import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.media import Media, MediaType, LibraryStatus
from app.models.library import UserMediaEntry


@pytest.fixture
def test_media(db_session: Session) -> Media:
    media = Media(
        media_type=MediaType.MOVIE,
        canonical_title="Test Movie",
        normalized_title="test movie",
        release_year=2024,
    )
    db_session.add(media)
    db_session.commit()
    return media


@pytest.fixture
def auth_headers_user_a(client: TestClient) -> dict[str, str]:
    payload = {
        "email": "user_a@example.com",
        "username": "usera",
        "display_name": "User A",
        "password": "securepassword123",
    }
    client.post("/api/v1/auth/register", json=payload)
    login_res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "usera", "password": "securepassword123"},
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_b(client: TestClient) -> dict[str, str]:
    payload = {
        "email": "user_b@example.com",
        "username": "userb",
        "display_name": "User B",
        "password": "securepassword123",
    }
    client.post("/api/v1/auth/register", json=payload)
    login_res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "userb", "password": "securepassword123"},
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_library_crud_and_security(
    client: TestClient,
    db_session: Session,
    test_media: Media,
    auth_headers_user_a: dict[str, str],
    auth_headers_user_b: dict[str, str],
):
    # 1. Add entry
    create_payload = {
        "media_id": str(test_media.id),
        "status": "PLANNED",
        "rating_value": 85,
        "notes_private": "Looks cool",
    }
    res = client.post("/api/v1/library", json=create_payload, headers=auth_headers_user_a)
    assert res.status_code == 201
    entry_data = res.json()
    assert entry_data["status"] == "PLANNED"
    assert entry_data["rating_value"] == 85
    assert entry_data["notes_private"] == "Looks cool"
    entry_id = entry_data["id"]

    # 2. Test unique active constraint
    res_duplicate = client.post("/api/v1/library", json=create_payload, headers=auth_headers_user_a)
    assert res_duplicate.status_code == 400
    assert "already exists" in res_duplicate.json()["detail"]

    # 3. Test list and separation
    res_list_a = client.get("/api/v1/library", headers=auth_headers_user_a)
    assert len(res_list_a.json()) == 1
    assert res_list_a.json()[0]["id"] == entry_id

    res_list_b = client.get("/api/v1/library", headers=auth_headers_user_b)
    assert len(res_list_b.json()) == 0

    # 4. Test Cross-user ownership on GET details
    res_get_b = client.get(f"/api/v1/library/{entry_id}", headers=auth_headers_user_b)
    assert res_get_b.status_code == 403

    # 5. Test Update and auto started/completed dates
    update_payload = {"status": "IN_PROGRESS"}
    res_update_b = client.patch(
        f"/api/v1/library/{entry_id}",
        json=update_payload,
        headers=auth_headers_user_b
    )
    assert res_update_b.status_code == 403

    res_update_a = client.patch(
        f"/api/v1/library/{entry_id}",
        json=update_payload,
        headers=auth_headers_user_a
    )
    assert res_update_a.status_code == 200
    assert res_update_a.json()["status"] == "IN_PROGRESS"
    assert res_update_a.json()["started_at"] is not None
    assert res_update_a.json()["completed_at"] is None

    # Update to COMPLETED
    res_completed = client.patch(
        f"/api/v1/library/{entry_id}",
        json={"status": "COMPLETED"},
        headers=auth_headers_user_a
    )
    assert res_completed.status_code == 200
    assert res_completed.json()["status"] == "COMPLETED"
    assert res_completed.json()["completed_at"] is not None

    # 6. Test Delete security and soft delete behavior
    res_delete_b = client.delete(f"/api/v1/library/{entry_id}", headers=auth_headers_user_b)
    assert res_delete_b.status_code == 403

    res_delete_a = client.delete(f"/api/v1/library/{entry_id}", headers=auth_headers_user_a)
    assert res_delete_a.status_code == 204

    # Verify soft-deleted item is excluded from lists and details
    res_get_after = client.get(f"/api/v1/library/{entry_id}", headers=auth_headers_user_a)
    assert res_get_after.status_code == 404

    res_list_after = client.get("/api/v1/library", headers=auth_headers_user_a)
    assert len(res_list_after.json()) == 0

    # 7. Add again after soft delete (should restore/upsert successfully)
    res_readd = client.post(
        "/api/v1/library",
        json={"media_id": str(test_media.id), "status": "PLANNED", "rating_value": 90},
        headers=auth_headers_user_a
    )
    assert res_readd.status_code == 201 or res_readd.status_code == 200
    readd_data = res_readd.json()
    assert readd_data["rating_value"] == 90
    assert readd_data["id"] == entry_id  # Restored existing row!


def test_soft_deleted_media_cannot_be_added_to_a_library(
    client: TestClient,
    db_session: Session,
    test_media: Media,
    auth_headers_user_a: dict[str, str],
):
    created = client.post(
        "/api/v1/library",
        json={"media_id": str(test_media.id), "status": "PLANNED"},
        headers=auth_headers_user_a,
    )
    assert created.status_code == 201

    test_media.deleted_at = datetime.now(timezone.utc)
    db_session.commit()

    assert client.get("/api/v1/library", headers=auth_headers_user_a).json() == []
    assert client.get(f"/api/v1/library/{created.json()['id']}", headers=auth_headers_user_a).status_code == 404

    response = client.post(
        "/api/v1/library",
        json={"media_id": str(test_media.id), "status": "PLANNED"},
        headers=auth_headers_user_a,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Media not found"
