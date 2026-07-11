from __future__ import annotations

from io import BytesIO
import uuid

from PIL import Image

from app.core.config import get_settings
from app.models.upload import Upload, UploadStatus
from app.routers.uploads import get_object_storage


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.deleted_keys: list[str] = []

    def put_image(self, *, object_key: str, content: bytes, content_type: str) -> None:
        self.objects[object_key] = (content, content_type)

    def get_object(self, *, object_key: str) -> tuple[bytes, str]:
        return self.objects[object_key]

    def delete_object(self, *, object_key: str) -> None:
        self.deleted_keys.append(object_key)
        self.objects.pop(object_key, None)


def _register(client, *, email: str, username: str) -> str:
    response = client.post("/api/v1/auth/register", json={
        "email": email, "username": username, "display_name": username,
        "password": "correct horse battery staple",
    })
    assert response.status_code == 201
    return response.json()["access_token"]


def _png_bytes(width: int = 32, height: int = 32) -> bytes:
    content = BytesIO()
    Image.new("RGBA", (width, height), color=(15, 20, 25, 255)).save(content, format="PNG")
    return content.getvalue()


def _upload(client, token: str, content: bytes, filename: str = "avatar.png"):
    return client.post(
        "/api/v1/uploads/profile-image",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, content, "image/png")},
    )


def test_profile_upload_reencodes_and_is_private(client, db_session):
    storage = FakeObjectStorage()
    client.app.dependency_overrides[get_object_storage] = lambda: storage
    owner_token = _register(client, email="owner@example.com", username="owner")
    other_token = _register(client, email="other@example.com", username="other")

    response = _upload(client, owner_token, _png_bytes(), "../../avatar.png")
    assert response.status_code == 201
    upload_id = response.json()["id"]
    assert response.json()["content_type"] == "image/webp"

    upload = db_session.get(Upload, uuid.UUID(upload_id))
    assert upload is not None
    assert upload.original_filename_sanitized == "avatar.png"
    assert upload.r2_object_key.startswith("profile-images/")
    assert b"owner" not in upload.r2_object_key.encode()
    stored_content, stored_type = storage.objects[upload.r2_object_key]
    assert stored_type == "image/webp"
    assert stored_content.startswith(b"RIFF") and stored_content[8:12] == b"WEBP"

    owner_content = client.get(f"/api/v1/uploads/{upload_id}/content", headers={"Authorization": f"Bearer {owner_token}"})
    assert owner_content.status_code == 200
    assert owner_content.headers["content-type"].startswith("image/webp")

    forbidden_content = client.get(f"/api/v1/uploads/{upload_id}/content", headers={"Authorization": f"Bearer {other_token}"})
    assert forbidden_content.status_code == 404


def test_profile_upload_rejects_invalid_or_oversized_input(client):
    storage = FakeObjectStorage()
    client.app.dependency_overrides[get_object_storage] = lambda: storage
    token = _register(client, email="image@example.com", username="imageuser")

    invalid = _upload(client, token, b"<svg onload=alert(1)></svg>", "avatar.svg")
    assert invalid.status_code == 422
    assert storage.objects == {}

    oversized = _upload(
        client, token, b"\x89PNG\r\n\x1a\n" + b"x" * get_settings().profile_image_max_bytes,
        "large.png",
    )
    assert oversized.status_code == 422
    assert storage.objects == {}


def test_replacing_and_deleting_profile_image_cleans_up_owned_object(client, db_session):
    storage = FakeObjectStorage()
    client.app.dependency_overrides[get_object_storage] = lambda: storage
    token = _register(client, email="replace@example.com", username="replaceuser")

    first_response = _upload(client, token, _png_bytes())
    assert first_response.status_code == 201
    first = db_session.get(Upload, uuid.UUID(first_response.json()["id"]))
    assert first is not None
    first_key = first.r2_object_key

    second_response = _upload(client, token, _png_bytes(48, 48))
    assert second_response.status_code == 201
    assert first_key in storage.deleted_keys
    db_session.refresh(first)
    assert first.status == UploadStatus.DELETED

    second_id = second_response.json()["id"]
    deleted = client.delete(f"/api/v1/uploads/{second_id}", headers={"Authorization": f"Bearer {token}"})
    assert deleted.status_code == 204
    second = db_session.get(Upload, uuid.UUID(second_id))
    db_session.refresh(second)
    assert second.status == UploadStatus.DELETED
