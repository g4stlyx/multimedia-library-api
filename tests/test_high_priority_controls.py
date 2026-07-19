from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import get_settings
from app.models.backup import BackupMetadata
from app.repositories.backup_repository import BackupRepository


def _register(client, *, email: str, username: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "display_name": username,
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_oversized_request_is_rejected_before_route_parsing(client):
    settings = get_settings()
    response = client.post(
        "/api/v1/auth/register",
        content=b"x" * (settings.max_request_body_bytes + 1),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_unverified_user_cannot_call_provider_backed_search(client):
    registered = _register(client, email="unverified@example.com", username="unverified")

    response = client.get(
        "/api/v1/media/search?q=Arrival",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Email verification is required for this action"


def test_backup_claim_transitions_a_single_persisted_record(db_session):
    repo = BackupRepository(db_session)
    backup = repo.create_backup_metadata(started_at=datetime.now(timezone.utc))
    db_session.commit()

    claimed = repo.claim_next_backup(worker_id="test-backup-worker", lease_seconds=60)
    assert claimed is not None
    assert claimed.id == backup.id
    assert claimed.status == "processing"
    assert claimed.worker_id == "test-backup-worker"
    assert claimed.lease_expires_at is not None

    db_session.commit()
    repo.update_backup_failed(backup=claimed, error_message="test completion")
    db_session.commit()

    db_session.refresh(claimed)
    assert claimed.status == "failed"
    assert claimed.worker_id is None
    assert claimed.lease_expires_at is None
