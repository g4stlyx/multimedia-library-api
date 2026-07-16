from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import get_settings
from app.core.normalization import normalize_title
from app.models.media import Genre, Media, MediaExternalId, MediaType
from app.providers.tmdb import TMDBProviderAdapter
from app.repositories.media_repository import MediaRepository
from app.services.media_service import MediaService


def test_normalize_title():
    assert normalize_title("Inception") == "inception"
    assert normalize_title("  The Dark Knight (2008)  ") == "the dark knight 2008"
    assert normalize_title("Amélie") == "amelie"
    assert normalize_title("Spider-Man: Into the Spider-Verse") == "spiderman into the spiderverse"
    assert normalize_title("Léon: The Professional") == "leon the professional"


def test_media_repository_basics(db_session):
    repo = MediaRepository(db_session)

    # 1. Create Media
    media = repo.create_media(
        media_type=MediaType.MOVIE,
        canonical_title="The Matrix",
        description="Neo follows the white rabbit.",
        release_year=1999,
        popularity_score=95.0,
    )
    assert media.id
    assert media.normalized_title == "the matrix"

    # 2. Add Alternate Title
    title = repo.add_title(media.id, "Matrix", language="en")
    assert title.id
    assert title.normalized_title == "matrix"

    # 3. Add External ID
    ext = repo.add_external_id(
        media_id=media.id,
        provider="tmdb",
        external_id="603",
        provider_media_type="movie",
    )
    assert ext.id

    # 4. Add Image
    img = repo.add_image(
        media_id=media.id,
        image_type="poster",
        source="tmdb",
        external_url="http://image.com/matrix.jpg",
    )
    assert img.id

    # 5. Genre create and associate
    genre = repo.get_or_create_genre("Sci-Fi")
    assert genre.normalized_name == "scifi"
    repo.associate_genre(media, genre)
    assert genre in media.genres

    # 6. Retrieve by external ID
    fetched = repo.get_by_external_id("tmdb", "603")
    assert fetched
    assert fetched.id == media.id


def test_popular_media_is_public_and_sorted(db_session, client):
    repo = MediaRepository(db_session)
    lower = repo.create_media(media_type=MediaType.MOVIE, canonical_title="Lower", popularity_score=10)
    higher = repo.create_media(media_type=MediaType.MOVIE, canonical_title="Higher", popularity_score=100)
    db_session.commit()

    response = client.get("/api/v1/media/popular?type=MOVIE")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()[:2]] == [str(higher.id), str(lower.id)]


@pytest.mark.anyio
async def test_search_local_first_and_fallback(db_session, client):
    settings = get_settings()
    repo = MediaRepository(db_session)

    # Pre-populate local DB with one item
    media = repo.create_media(
        media_type=MediaType.MOVIE,
        canonical_title="Inception",
        release_year=2010,
        popularity_score=90.0,
    )
    repo.add_external_id(media.id, "tmdb", "27205")

    # Log in test user
    payload = {
        "email": "media_test@example.com",
        "username": "mediatest",
        "display_name": "Media Test User",
        "password": "supersecurepassword123",
    }
    client.post("/api/v1/auth/register", json=payload)
    login_res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "mediatest", "password": "supersecurepassword123"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Case A: Local exact match -> returns local item and does not query external provider
    with patch("app.providers.tmdb.TMDBProviderAdapter.search") as mock_search:
        res = client.get("/api/v1/media/search?q=Inception", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["is_persisted"] is True
        assert data[0]["id"] == str(media.id)
        mock_search.assert_not_called()

    # Case B: Local sparse results -> falls back to external provider
    mock_provider_result = [
        MagicMock(
            provider="tmdb",
            external_id="9999",
            media_type=MediaType.MOVIE,
            title="External Movie",
            original_title="External Movie Orig",
            description="External desc",
            release_date=None,
            release_year=2024,
            runtime_minutes=120,
            primary_language="en",
            country_code="US",
            poster_url=None,
            backdrop_url=None,
            popularity_score=80.0,
            metadata_json={},
            external_url=None,
            attribution_text=None,
            attribution_url=None,
        )
    ]

    with patch("app.providers.tmdb.TMDBProviderAdapter.search", return_value=mock_provider_result):
        # We query for something else which misses the local exact match
        res = client.get("/api/v1/media/search?q=External", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) > 0
        assert data[0]["is_persisted"] is False
        assert data[0]["canonical_title"] == "External Movie"
        assert data[0]["provider"] == "tmdb"
        assert data[0]["external_id"] == "999" or data[0]["external_id"] == "9999"


@pytest.mark.anyio
async def test_upsert_by_external_id_and_deduplication(db_session):
    settings = get_settings()
    repo = MediaRepository(db_session)
    service = MediaService(db_session, settings)

    # 1. Create a dummy existing movie
    existing = repo.create_media(
        media_type=MediaType.MOVIE,
        canonical_title="Gladiator",
        release_year=2000,
        popularity_score=85.0,
    )
    repo.add_external_id(existing.id, "imdb", "tt0172495")

    # Mock details return payload for upsert
    mock_details = MagicMock(
        provider="tmdb",
        external_id="9876",
        media_type=MediaType.MOVIE,
        title="Gladiator",
        original_title="Gladiator",
        description="A hero who became a slave.",
        release_date=None,
        release_year=2000,
        runtime_minutes=155,
        primary_language="en",
        country_code="US",
        poster_url="http://poster.jpg",
        backdrop_url="http://backdrop.jpg",
        popularity_score=88.0,
        imdb_id="tt0172495",  # Match by IMDb ID!
        genres=["Action", "Drama"],
        alternate_titles=[],
        images=[],
        metadata_json={},
        external_url=None,
        attribution_text=None,
        attribution_url=None,
    )

    with patch("app.providers.tmdb.TMDBProviderAdapter.get_details", return_value=mock_details):
        # Upserting a new TMDB ID that shares the same IMDb ID should bind to existing Gladiator
        result = await service.upsert_by_external_id("tmdb", "9876", MediaType.MOVIE)
        assert result.id == existing.id
        
        # Verify it successfully added the TMDB external ID association
        ext_ids = db_session.query(MediaExternalId).filter_by(media_id=existing.id).all()
        providers = [e.provider for e in ext_ids]
        assert "tmdb_movie" in providers
        assert "imdb" in providers


@pytest.mark.anyio
async def test_refresh_media_updates_linked_tmdb_record(db_session):
    settings = get_settings()
    repo = MediaRepository(db_session)
    service = MediaService(db_session, settings)
    media = repo.create_media(media_type=MediaType.MOVIE, canonical_title="Old title")
    repo.add_external_id(media.id, "tmdb_movie", "603", provider_media_type="movie")
    db_session.commit()
    details = MagicMock(
        title="The Matrix",
        original_title="The Matrix",
        description="Updated metadata.",
        release_date=None,
        release_year=1999,
        runtime_minutes=136,
        primary_language="en",
        country_code="US",
        poster_url="https://image.tmdb.org/t/p/w500/matrix.jpg",
        backdrop_url="https://image.tmdb.org/t/p/original/matrix.jpg",
        popularity_score=95.0,
        metadata_json={"id": 603},
        genres=["Science Fiction"],
    )

    with patch("app.providers.tmdb.TMDBProviderAdapter.get_details", return_value=details):
        refreshed = await service.refresh_media(media.id, actor_user_id=uuid.uuid4(), request_id="test-request")

    assert refreshed.canonical_title == "The Matrix"
    assert refreshed.last_synced_at is not None
    assert refreshed.genres[0].name == "Science Fiction"


@pytest.mark.anyio
async def test_duplicate_candidates_handling(db_session):
    settings = get_settings()
    repo = MediaRepository(db_session)
    service = MediaService(db_session, settings)

    # Populate a movie with same name but slightly different release year (+1 year)
    repo.create_media(
        media_type=MediaType.MOVIE,
        canonical_title="Interstellar",
        release_year=2014,
        popularity_score=95.0,
    )

    # Upsert details for Interstellar but year 2015 (low-confidence fuzzy candidate)
    mock_details = MagicMock(
        provider="tmdb",
        external_id="157336",
        media_type=MediaType.MOVIE,
        title="Interstellar",
        original_title="Interstellar",
        description="Fuzzy duplicate test.",
        release_date=None,
        release_year=2015,
        runtime_minutes=169,
        primary_language="en",
        country_code="US",
        poster_url=None,
        backdrop_url=None,
        popularity_score=99.0,
        imdb_id=None,
        genres=[],
        alternate_titles=[],
        images=[],
        metadata_json={},
        external_url=None,
        attribution_text=None,
        attribution_url=None,
    )

    with patch("app.providers.tmdb.TMDBProviderAdapter.get_details", return_value=mock_details):
        # Should create a new record since year is different (+1), but flag as duplicate candidate
        result = await service.upsert_by_external_id("tmdb", "157336", MediaType.MOVIE)
        assert result.id is not None
        assert "duplicate_candidates" in result.metadata_json
        assert len(result.metadata_json["duplicate_candidates"]) > 0


@pytest.mark.anyio
async def test_provider_request_logging(db_session):
    settings = get_settings()
    adapter = TMDBProviderAdapter(api_key="mock_key", db=db_session)

    # Stub out the HTTP execution to trigger a request log
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"results": []}

    with patch("app.providers.tmdb.requests.request", return_value=mock_res):
        await adapter.search("Alien", MediaType.MOVIE)

        
        # Verify db log was created
        from app.models.provider import ProviderRequest
        log_entry = db_session.query(ProviderRequest).first()
        assert log_entry
        assert log_entry.provider == "tmdb"
        assert log_entry.endpoint == "/search/movie"
        assert log_entry.status_code == 200
