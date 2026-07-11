from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.media import MediaType
from app.models.seed import SeedItemStatus, SeedRun, SeedRunStatus
from app.providers.registry import ProviderRegistry
from app.repositories.media_repository import MediaRepository
from app.repositories.seed_repository import SeedRepository
from app.services.media_service import MediaService

logger = logging.getLogger(__name__)


class SeedService:
    """Processes one seed page at a time; queue/scheduler ownership lives outside the API process."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.seed_repo = SeedRepository(db)
        self.media_repo = MediaRepository(db)
        self.media_service = MediaService(db, settings)

    @staticmethod
    def _validate_seed(provider: str, media_type: MediaType) -> None:
        allowed = {
            "tmdb": {MediaType.MOVIE, MediaType.SERIES},
            "rawg": {MediaType.GAME},
            "google_books": {MediaType.BOOK},
            "open_library": {MediaType.BOOK},
        }
        if media_type not in allowed.get(provider, set()):
            if provider == "spotify":
                raise ValueError("Spotify is on-demand only and cannot be seeded")
            raise ValueError(f"{provider} does not support seeding {media_type.value}")

    async def process_page(
        self,
        *,
        provider: str,
        media_type: MediaType,
        seed_kind: str,
        cursor: str | None = None,
        limit: int = 20,
    ) -> SeedRun:
        provider = provider.strip().lower()
        self._validate_seed(provider, media_type)
        run = self.seed_repo.get_or_create_run(provider=provider, media_type=media_type, seed_kind=seed_kind, cursor=cursor)
        if run.status in {SeedRunStatus.COMPLETED, SeedRunStatus.RUNNING}:
            return run

        run.status = SeedRunStatus.RUNNING
        run.started_at = run.started_at or datetime.now(timezone.utc)
        self.db.commit()

        try:
            page = await ProviderRegistry(self.settings, self.db).get(provider).get_seed_page(
                seed_kind=seed_kind, media_type=media_type, cursor=cursor, limit=limit,
            )
            for result in page.results:
                item = self.seed_repo.get_or_create_item(
                    seed_run_id=run.id, provider=provider, external_id=result.external_id,
                    raw_payload=result.metadata_json, normalized_payload=result.model_dump(mode="json"),
                )
                if item.status == SeedItemStatus.COMPLETED:
                    continue
                run.total_seen += 1
                self.seed_repo.add_snapshot(seed_item_id=item.id, provider=provider, external_id=result.external_id, payload=result.metadata_json or {})
                exists_before = self.media_repo.get_by_external_id(self.media_service._get_db_provider(provider, media_type), result.external_id) is not None
                try:
                    await self.media_service.upsert_by_external_id(provider, result.external_id, media_type)
                    item.status = SeedItemStatus.COMPLETED
                    item.error = None
                    if exists_before:
                        run.total_updated += 1
                    else:
                        run.total_inserted += 1
                    self.db.commit()
                except Exception as error:
                    self.db.rollback()
                    item = self.seed_repo.get_or_create_item(seed_run_id=run.id, provider=provider, external_id=result.external_id, raw_payload=result.metadata_json, normalized_payload=result.model_dump(mode="json"))
                    item.status = SeedItemStatus.FAILED
                    item.error = str(error)[:2000]
                    run = self.db.get(SeedRun, run.id)
                    assert run is not None
                    run.total_failed += 1
                    self.db.commit()
                    logger.exception("seed_item_failed", extra={"provider": provider, "external_id": result.external_id})
            run = self.db.get(SeedRun, run.id)
            assert run is not None
            run.status = SeedRunStatus.COMPLETED
            run.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(run)
            return run
        except Exception:
            self.db.rollback()
            run = self.db.get(SeedRun, run.id)
            if run is not None:
                run.status = SeedRunStatus.FAILED
                run.finished_at = datetime.now(timezone.utc)
                self.db.commit()
            raise
