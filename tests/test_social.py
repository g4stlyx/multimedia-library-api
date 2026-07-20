from __future__ import annotations

import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.media import Media, MediaType
from app.models.social import Review, Comment, MediaList, ListItem


@pytest.fixture
def test_media(db_session: Session) -> Media:
    media = Media(
        media_type=MediaType.MOVIE,
        canonical_title="Social Movie Test",
        normalized_title="social movie test",
        release_year=2024,
    )
    db_session.add(media)
    db_session.commit()
    return media


@pytest.fixture
def auth_headers_user_a(client: TestClient) -> dict[str, str]:
    payload = {
        "email": "social_a@example.com",
        "username": "sociala",
        "display_name": "Social A",
        "password": "securepassword123",
    }
    client.post("/api/v1/auth/register", json=payload)
    login_res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "sociala", "password": "securepassword123"},
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_b(client: TestClient) -> dict[str, str]:
    payload = {
        "email": "social_b@example.com",
        "username": "socialb",
        "display_name": "Social B",
        "password": "securepassword123",
    }
    client.post("/api/v1/auth/register", json=payload)
    login_res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "socialb", "password": "securepassword123"},
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_reviews_crud_and_rating_sync(
    client: TestClient,
    db_session: Session,
    test_media: Media,
    auth_headers_user_a: dict[str, str],
    auth_headers_user_b: dict[str, str],
):
    # 1. Create a library entry first to verify rating sync
    client.post(
        "/api/v1/library",
        json={"media_id": str(test_media.id), "status": "PLANNED", "rating_value": 50},
        headers=auth_headers_user_a
    )

    # 2. Create Review
    review_payload = {
        "media_id": str(test_media.id),
        "rating_value": 90,
        "body": "Absolute masterpiece!",
        "contains_spoilers": False,
        "visibility": "public",
    }
    res = client.post("/api/v1/reviews", json=review_payload, headers=auth_headers_user_a)
    assert res.status_code == 201
    review_data = res.json()
    assert review_data["rating_value"] == 90
    assert review_data["body"] == "Absolute masterpiece!"
    review_id = review_data["id"]

    # Verify rating synchronized with library entry
    res_lib = client.get(f"/api/v1/library/media/{test_media.id}", headers=auth_headers_user_a)
    assert res_lib.status_code == 200
    assert res_lib.json()["rating_value"] == 90

    # 3. Test active review constraint
    res_dup = client.post("/api/v1/reviews", json=review_payload, headers=auth_headers_user_a)
    assert res_dup.status_code == 400

    # 4. Cross-user update check
    res_update_b = client.patch(
        f"/api/v1/reviews/{review_id}",
        json={"body": "Hacked"},
        headers=auth_headers_user_b
    )
    assert res_update_b.status_code == 403

    # Owner update
    res_update_a = client.patch(
        f"/api/v1/reviews/{review_id}",
        json={"rating_value": 95},
        headers=auth_headers_user_a
    )
    assert res_update_a.status_code == 200
    assert res_update_a.json()["rating_value"] == 95

    # Verify library rating synced
    res_lib_sync = client.get(f"/api/v1/library/media/{test_media.id}", headers=auth_headers_user_a)
    assert res_lib_sync.json()["rating_value"] == 95

    # 5. Delete review
    res_delete_b = client.delete(f"/api/v1/reviews/{review_id}", headers=auth_headers_user_b)
    assert res_delete_b.status_code == 403

    res_delete_a = client.delete(f"/api/v1/reviews/{review_id}", headers=auth_headers_user_a)
    assert res_delete_a.status_code == 204

    # Verify soft-deleted review is gone
    res_get = client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers_user_a)
    assert res_get.status_code == 404


def test_comments_flow(
    client: TestClient,
    db_session: Session,
    test_media: Media,
    auth_headers_user_a: dict[str, str],
    auth_headers_user_b: dict[str, str],
):
    # 1. Create a review to comment on
    res_rev = client.post(
        "/api/v1/reviews",
        json={"media_id": str(test_media.id), "body": "Great media"},
        headers=auth_headers_user_a
    )
    review_id = res_rev.json()["id"]

    # 2. Add Comment
    comment_payload = {
        "target_type": "review",
        "target_id": review_id,
        "body": "I agree with you!",
    }
    res_com = client.post("/api/v1/comments", json=comment_payload, headers=auth_headers_user_b)
    assert res_com.status_code == 201
    comment_id = res_com.json()["id"]

    # Verify review comment count is 1
    res_rev_get = client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers_user_a)
    assert res_rev_get.json()["comment_count"] == 1

    # 3. Add Reply
    reply_payload = {
        "target_type": "review",
        "target_id": review_id,
        "parent_comment_id": comment_id,
        "body": "Thank you!",
    }
    res_rep = client.post("/api/v1/comments", json=reply_payload, headers=auth_headers_user_a)
    assert res_rep.status_code == 201
    reply_id = res_rep.json()["id"]

    nested_reply = client.post(
        "/api/v1/comments",
        json={
            "target_type": "review",
            "target_id": review_id,
            "parent_comment_id": reply_id,
            "body": "A third level should not be accepted",
        },
        headers=auth_headers_user_b,
    )
    assert nested_reply.status_code == 400

    # Verify review comment count is now 2
    assert client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers_user_a).json()["comment_count"] == 2

    # 4. Update comment security
    res_upd_b = client.patch(
        f"/api/v1/comments/{reply_id}",
        json={"body": "Thanks a lot"},
        headers=auth_headers_user_b
    )
    assert res_upd_b.status_code == 403

    res_upd_a = client.patch(
        f"/api/v1/comments/{reply_id}",
        json={"body": "Thanks a lot"},
        headers=auth_headers_user_a
    )
    assert res_upd_a.status_code == 200

    # 5. Delete comments
    res_del_b = client.delete(f"/api/v1/comments/{reply_id}", headers=auth_headers_user_b)
    assert res_del_b.status_code == 403

    res_del_a = client.delete(f"/api/v1/comments/{reply_id}", headers=auth_headers_user_a)
    assert res_del_a.status_code == 204

    # Verify comment count decremented
    assert client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers_user_a).json()["comment_count"] == 1


def test_lists_and_items_reorder(
    client: TestClient,
    db_session: Session,
    test_media: Media,
    auth_headers_user_a: dict[str, str],
    auth_headers_user_b: dict[str, str],
):
    # Setup second media for list
    media2 = Media(
        media_type=MediaType.MOVIE,
        canonical_title="Another Movie",
        normalized_title="another movie",
        release_year=2025,
    )
    db_session.add(media2)
    db_session.commit()

    # 1. Create list
    list_payload = {
        "title": "My Favorite Movies",
        "description": "A curated list of masterpieces.",
        "visibility": "public",
        "items": [
            {"media_id": str(test_media.id), "position": 0, "note": "Amazing acting"}
        ]
    }
    res = client.post("/api/v1/lists", json=list_payload, headers=auth_headers_user_a)
    assert res.status_code == 201
    list_data = res.json()
    list_id = list_data["id"]
    assert len(list_data["items"]) == 1

    # 2. Add second item
    res_add = client.post(
        f"/api/v1/lists/{list_id}/items",
        json={"media_id": str(media2.id), "note": "Great cinematography"},
        headers=auth_headers_user_a
    )
    assert res_add.status_code == 201
    assert res_add.json()["position"] == 1

    item_note_b = client.patch(
        f"/api/v1/lists/{list_id}/items/{media2.id}",
        json={"note": "Not yours"},
        headers=auth_headers_user_b,
    )
    assert item_note_b.status_code == 403

    item_note_a = client.patch(
        f"/api/v1/lists/{list_id}/items/{media2.id}",
        json={"note": "Updated item note"},
        headers=auth_headers_user_a,
    )
    assert item_note_a.status_code == 200
    assert item_note_a.json()["note"] == "Updated item note"

    # Cross-user add check
    res_add_b = client.post(
        f"/api/v1/lists/{list_id}/items",
        json={"media_id": str(media2.id)},
        headers=auth_headers_user_b
    )
    assert res_add_b.status_code == 403

    # Get list details
    res_get = client.get(f"/api/v1/lists/{list_id}", headers=auth_headers_user_a)
    assert len(res_get.json()["items"]) == 2

    # 3. Reorder list items (swap positions)
    res_reorder_b = client.put(
        f"/api/v1/lists/{list_id}/items/reorder",
        json={"media_ids": [str(media2.id), str(test_media.id)]},
        headers=auth_headers_user_b
    )
    assert res_reorder_b.status_code == 403

    res_reorder_a = client.put(
        f"/api/v1/lists/{list_id}/items/reorder",
        json={"media_ids": [str(media2.id), str(test_media.id)]},
        headers=auth_headers_user_a
    )
    assert res_reorder_a.status_code == 200
    items = res_reorder_a.json()["items"]
    # Verify new ordering
    assert items[0]["media_id"] == str(media2.id)
    assert items[0]["position"] == 0
    assert items[1]["media_id"] == str(test_media.id)
    assert items[1]["position"] == 1

    # 4. Remove item
    res_rem_b = client.delete(
        f"/api/v1/lists/{list_id}/items/{media2.id}",
        headers=auth_headers_user_b
    )
    assert res_rem_b.status_code == 403

    res_rem_a = client.delete(
        f"/api/v1/lists/{list_id}/items/{media2.id}",
        headers=auth_headers_user_a
    )
    assert res_rem_a.status_code == 204

    # Verify positions normalized (remaining item should be shifted to position 0)
    res_get_norm = client.get(f"/api/v1/lists/{list_id}", headers=auth_headers_user_a)
    items_norm = res_get_norm.json()["items"]
    assert len(items_norm) == 1
    assert items_norm[0]["media_id"] == str(test_media.id)
    assert items_norm[0]["position"] == 0

    # 5. Delete list
    res_del_b = client.delete(f"/api/v1/lists/{list_id}", headers=auth_headers_user_b)
    assert res_del_b.status_code == 403

    res_del_a = client.delete(f"/api/v1/lists/{list_id}", headers=auth_headers_user_a)
    assert res_del_a.status_code == 204

    # Verify deleted
    assert client.get(f"/api/v1/lists/{list_id}", headers=auth_headers_user_a).status_code == 404


def test_non_public_reviews_lists_and_comments_are_not_discoverable(
    client: TestClient,
    test_media: Media,
    auth_headers_user_a: dict[str, str],
    auth_headers_user_b: dict[str, str],
):
    review_response = client.post(
        "/api/v1/reviews",
        json={"media_id": str(test_media.id), "body": "Private review", "visibility": "private"},
        headers=auth_headers_user_a,
    )
    assert review_response.status_code == 201
    review_id = review_response.json()["id"]

    other_reviews = client.get(
        f"/api/v1/reviews?media_id={test_media.id}",
        headers=auth_headers_user_b,
    )
    assert other_reviews.status_code == 200
    assert other_reviews.json() == []
    assert client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers_user_b).status_code == 403
    assert client.post(
        "/api/v1/comments",
        json={"target_type": "review", "target_id": review_id, "body": "Not allowed"},
        headers=auth_headers_user_b,
    ).status_code == 403

    list_response = client.post(
        "/api/v1/lists",
        json={"title": "Private list", "visibility": "private"},
        headers=auth_headers_user_a,
    )
    assert list_response.status_code == 201
    list_id = list_response.json()["id"]
    assert client.get(f"/api/v1/lists/{list_id}", headers=auth_headers_user_b).status_code == 403
    other_lists = client.get("/api/v1/lists", headers=auth_headers_user_b)
    assert all(item["id"] != list_id for item in other_lists.json())


def test_follower_visibility_allows_followers_but_not_unrelated_users(
    client: TestClient,
    test_media: Media,
):
    def register(username: str) -> tuple[dict[str, str], str]:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"{username}@example.com",
                "username": username,
                "password": "securepassword123",
            },
        )
        assert response.status_code == 201
        payload = response.json()
        return {"Authorization": f"Bearer {payload['access_token']}"}, payload["user"]["id"]

    owner_headers, owner_id = register("followowner")
    follower_headers, _ = register("actualfollower")
    outsider_headers, _ = register("notafollower")

    review = client.post(
        "/api/v1/reviews",
        json={"media_id": str(test_media.id), "body": "Followers can read this", "visibility": "followers"},
        headers=owner_headers,
    )
    assert review.status_code == 201
    review_id = review.json()["id"]

    assert client.get(f"/api/v1/reviews/{review_id}", headers=outsider_headers).status_code == 403
    assert client.get(f"/api/v1/reviews?media_id={test_media.id}", headers=outsider_headers).json() == []
    assert client.post(
        "/api/v1/comments",
        json={"target_type": "review", "target_id": review_id, "body": "Trying to bypass visibility"},
        headers=outsider_headers,
    ).status_code == 403

    assert client.put(f"/api/v1/users/{owner_id}/follow", headers=follower_headers).status_code == 204
    follower_reviews = client.get(f"/api/v1/reviews?media_id={test_media.id}", headers=follower_headers)
    assert follower_reviews.status_code == 200
    assert [item["id"] for item in follower_reviews.json()] == [review_id]
    assert client.post(
        "/api/v1/comments",
        json={"target_type": "review", "target_id": review_id, "body": "Now I can comment"},
        headers=follower_headers,
    ).status_code == 201

    private_list = client.post(
        "/api/v1/lists",
        json={"title": "Owner only", "visibility": "private"},
        headers=owner_headers,
    )
    assert private_list.status_code == 201
    assert client.get(f"/api/v1/lists/{private_list.json()['id']}", headers=follower_headers).status_code == 403


def test_content_bounds_and_plain_text_validation(
    client: TestClient,
    test_media: Media,
    auth_headers_user_a: dict[str, str],
):
    assert client.post(
        "/api/v1/reviews",
        json={"media_id": str(test_media.id), "body": "x" * 5001},
        headers=auth_headers_user_a,
    ).status_code == 422
    assert client.post(
        "/api/v1/comments",
        json={"target_type": "media", "target_id": str(test_media.id), "body": "<script>alert(1)</script>"},
        headers=auth_headers_user_a,
    ).status_code == 422
    assert client.post(
        "/api/v1/lists",
        json={"title": "Bounded", "description": "x" * 5001},
        headers=auth_headers_user_a,
    ).status_code == 422
    assert client.post(
        "/api/v1/library",
        json={"media_id": str(test_media.id), "notes_private": "x" * 5001},
        headers=auth_headers_user_a,
    ).status_code == 422
