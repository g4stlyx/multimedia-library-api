from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import get_settings
from app.models.media import MediaExternalId, MediaType
from app.models.seed import ProviderSnapshot, SeedItem, SeedRun, SeedRunStatus
from app.providers.base import ProviderMediaDetails, ProviderSearchResult, ProviderSeedPage
from app.providers.http import ProviderHttpClient
from app.services.media_service import MediaService
from app.services.provider_presentation_service import ProviderPresentationService
from app.services.seed_service import SeedService


@pytest.mark.anyio
async def test_rawg_upsert_stores_provider_attribution_and_is_idempotent(db_session):
    service = MediaService(db_session, get_settings())
    details = ProviderMediaDetails(
        provider="rawg", external_id="3498", media_type=MediaType.GAME, title="Grand Theft Auto V",
        release_year=2013, external_url="https://rawg.io/games/grand-theft-auto-v",
        attribution_text="Data provided by RAWG", attribution_url="https://rawg.io/",
        metadata_json={"id": 3498},
    )
    with patch("app.providers.rawg.RAWGProviderAdapter.get_details", new=AsyncMock(return_value=details)):
        created = await service.upsert_by_external_id("rawg", "3498", MediaType.GAME)
        repeated = await service.upsert_by_external_id("rawg", "3498", MediaType.GAME)

    assert created.id == repeated.id
    external_id = db_session.query(MediaExternalId).filter_by(media_id=created.id, provider="rawg").one()
    assert external_id.attribution_text == "Data provided by RAWG"
    assert external_id.attribution_url == "https://rawg.io/"


def test_provider_presentation_whitelists_game_metadata(db_session):
    service = MediaService(db_session, get_settings())
    media = service.repo.create_media(
        media_type=MediaType.GAME,
        canonical_title="Example Game",
        metadata_json={
            "publishers": [{"name": "Example Studios"}],
            "platforms": [{"platform": {"name": "PC"}}, {"platform": {"name": "PlayStation 5"}}],
            "metacritic": 92,
            "unrelated_provider_payload": {"secret": "not public"},
        },
    )
    service.repo.add_external_id(
        media_id=media.id,
        provider="rawg",
        external_id="example-game",
        external_url="https://rawg.io/games/example-game",
        attribution_text="Data provided by RAWG",
        attribution_url="https://rawg.io/",
    )

    presentation = ProviderPresentationService.build(media)

    assert len(presentation) == 1
    assert presentation[0].publisher == "Example Studios"
    assert presentation[0].platforms == ["PC", "PlayStation 5"]
    assert presentation[0].metacritic_score == 92
    assert "unrelated_provider_payload" not in presentation[0].model_dump()


@pytest.mark.anyio
async def test_seed_page_is_idempotent_and_keeps_snapshot(db_session):
    result = ProviderSearchResult(
        provider="rawg", external_id="42", media_type=MediaType.GAME, title="Seeded game", metadata_json={"id": 42},
    )
    page = ProviderSeedPage(provider="rawg", media_type=MediaType.GAME, seed_kind="popular", cursor="1", next_cursor="2", results=[result])
    provider = MagicMock()
    provider.get_seed_page = AsyncMock(return_value=page)
    service = SeedService(db_session, get_settings())
    service.media_service.upsert_by_external_id = AsyncMock()

    with patch("app.services.seed_service.ProviderRegistry") as registry:
        registry.return_value.get.return_value = provider
        first = await service.process_page(provider="rawg", media_type=MediaType.GAME, seed_kind="popular", cursor="1")
        second = await service.process_page(provider="rawg", media_type=MediaType.GAME, seed_kind="popular", cursor="1")

    assert first.id == second.id
    assert second.status == SeedRunStatus.COMPLETED
    assert db_session.query(SeedRun).count() == 1
    assert db_session.query(SeedItem).count() == 1
    assert db_session.query(ProviderSnapshot).count() == 1
    service.media_service.upsert_by_external_id.assert_awaited_once_with("rawg", "42", MediaType.GAME)


def test_provider_http_client_retries_429_without_logging_secrets():
    settings = get_settings().model_copy(update={"provider_max_retries": 1})
    client = ProviderHttpClient(provider="example", base_url="https://example.test", settings=settings, requests_per_second=1000)
    rate_limited = MagicMock(status_code=429, headers={"Retry-After": "0"})
    successful = MagicMock(status_code=200, headers={})
    successful.raise_for_status.return_value = None
    successful.json.return_value = {"ok": True}

    with patch("app.providers.http.requests.request", side_effect=[rate_limited, successful]) as request, patch("app.providers.http.time.sleep"):
        assert client.request("GET", "/catalog", params={"key": "secret"}) == {"ok": True}

    assert request.call_count == 2
