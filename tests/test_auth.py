from __future__ import annotations

from sqlalchemy import select

from app.models.user import RefreshToken, User


def _register_payload(email: str = "user@example.com", username: str = "user_one") -> dict[str, str]:
    return {
        "email": email,
        "username": username,
        "display_name": "User One",
        "password": "correct horse battery staple",
    }


def test_register_login_and_me(client):
    register_response = client.post("/api/v1/auth/register", json=_register_payload())

    assert register_response.status_code == 201
    body = register_response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["email_verification_token"]
    assert body["user"]["email"] == "user@example.com"
    assert body["user"]["role"] == "USER"
    assert body["user"]["admin_level"] is None

    login_response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "user_one", "password": "correct horse battery staple"},
    )

    assert login_response.status_code == 200
    login_body = login_response.json()
    me_response = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {login_body['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "user_one"


def test_refresh_rotates_token_and_reuse_revokes_family(client, db_session):
    register_response = client.post("/api/v1/auth/register", json=_register_payload())
    old_refresh_token = register_response.json()["refresh_token"]

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert refresh_response.status_code == 200
    new_refresh_token = refresh_response.json()["refresh_token"]
    assert new_refresh_token != old_refresh_token

    reuse_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert reuse_response.status_code == 401

    user = db_session.scalar(select(User).where(User.email_normalized == "user@example.com"))
    active_tokens = db_session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
    ).all()
    assert active_tokens == []


def test_email_verification_consumes_token(client):
    register_response = client.post("/api/v1/auth/register", json=_register_payload())
    verification_token = register_response.json()["email_verification_token"]

    verify_response = client.post(
        "/api/v1/auth/verify-email",
        json={"token": verification_token},
    )
    assert verify_response.status_code == 200

    reused_response = client.post(
        "/api/v1/auth/verify-email",
        json={"token": verification_token},
    )
    assert reused_response.status_code == 400


def test_password_reset_revokes_refresh_tokens(client, db_session):
    register_response = client.post("/api/v1/auth/register", json=_register_payload())
    refresh_token = register_response.json()["refresh_token"]

    request_response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "user@example.com"},
    )
    assert request_response.status_code == 200
    reset_token = request_response.json()["token"]
    assert reset_token

    confirm_response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": reset_token,
            "new_password": "new correct horse battery staple",
        },
    )
    assert confirm_response.status_code == 200

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 401

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "user@example.com",
            "password": "new correct horse battery staple",
        },
    )
    assert login_response.status_code == 200
