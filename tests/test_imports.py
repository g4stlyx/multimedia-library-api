from __future__ import annotations

import uuid
import asyncio

from app.core.config import get_settings
from app.models.import_job import ImportJob, ImportJobStatus, ImportSource
from app.models.media import Media, MediaType
from app.services.import_service import ImportService


def _register(client, email: str, username: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/register", json={
        "email": email, "username": username, "display_name": username,
        "password": "correct horse battery staple",
    })
    assert response.status_code == 201
    verification_token = response.json()["email_verification_token"]
    assert verification_token
    assert client.post("/api/v1/auth/verify-email", json={"token": verification_token}).status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _letterboxd_file() -> tuple[str, bytes, str]:
    return ("ratings.csv", b"Name,Year,Rating,Watched Date,Letterboxd URI\nArrival,2016,4.5,2026-01-01,https://letterboxd.com/film/arrival/\n", "text/csv")


def test_import_is_idempotent_and_applies_exact_local_match(client, db_session):
    db_session.add(Media(media_type=MediaType.MOVIE, canonical_title="Arrival", normalized_title="arrival", release_year=2016))
    db_session.commit()
    headers = _register(client, "imports@example.com", "importer")

    created = client.post("/api/v1/imports", headers=headers, data={"source": "LETTERBOXD"}, files={"file": _letterboxd_file()})
    assert created.status_code == 201
    job_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"

    asyncio.run(
        ImportService(db_session, get_settings()).process_job(
            uuid.UUID(job_id),
            worker_id="test-import-worker",
        )
    )

    job = client.get(f"/api/v1/imports/{job_id}", headers=headers)
    assert job.status_code == 200
    assert job.json()["status"] == "COMPLETED"
    assert job.json()["total_rows"] == 1
    assert job.json()["successful_rows"] == 1
    assert job.json()["items"][0]["status"] == "IMPORTED"

    duplicate = client.post("/api/v1/imports", headers=headers, data={"source": "LETTERBOXD"}, files={"file": _letterboxd_file()})
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == job_id
    library = client.get("/api/v1/library", headers=headers)
    assert library.status_code == 200
    assert len(library.json()) == 1
    assert library.json()[0]["rating_value"] == 90


def test_import_jobs_are_not_visible_or_mutable_by_other_users(client, db_session):
    owner_headers = _register(client, "owner-import@example.com", "importowner")
    other_headers = _register(client, "other-import@example.com", "importother")
    job = ImportJob(
        user_id=uuid.UUID(client.get("/api/v1/me", headers=owner_headers).json()["id"]),
        source_platform=ImportSource.GENERIC, status=ImportJobStatus.AWAITING_RESOLUTION,
        file_sha256="a" * 64, total_rows=1,
    )
    db_session.add(job)
    db_session.commit()

    assert client.get(f"/api/v1/imports/{job.id}", headers=other_headers).status_code == 404
    assert client.post(f"/api/v1/imports/{job.id}/cancel", headers=other_headers).status_code == 404
