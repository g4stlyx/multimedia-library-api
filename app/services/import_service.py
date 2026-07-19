from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.normalization import normalize_title
from app.models.import_job import ImportItem, ImportItemStatus, ImportJob, ImportJobStatus, ImportSource
from app.models.library import UserMediaEntry
from app.models.media import LibraryStatus, Media, MediaType
from app.providers.base import ProviderSearchResult
from app.repositories.import_repository import ImportRepository
from app.repositories.library_repository import LibraryRepository
from app.repositories.media_repository import MediaRepository
from app.services.import_parser import ImportParseError, parse_csv_import
from app.services.media_service import MediaService

logger = logging.getLogger(__name__)
_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class ImportService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.repo = ImportRepository(db)
        self.library = LibraryRepository(db)
        self.media = MediaRepository(db)

    @staticmethod
    def sanitize_filename(filename: str | None) -> str | None:
        if not filename:
            return None
        safe = _FILENAME_SAFE.sub("_", filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]).strip("._")
        return safe[:255] or None

    def create_csv_job(
        self, *, user_id: uuid.UUID, source: ImportSource, filename: str | None, content: bytes,
        default_media_type: MediaType | None,
    ) -> tuple[ImportJob, bool]:
        if len(content) == 0:
            raise ImportParseError("The CSV file is empty")
        if len(content) > self.settings.import_max_file_bytes:
            raise ImportParseError("CSV file exceeds the maximum allowed size")
        content_hash = hashlib.sha256(content).hexdigest()
        existing = self.repo.get_idempotent_job(user_id=user_id, source=source, file_sha256=content_hash)
        if existing:
            return existing, False
        if self.repo.count_active_jobs(user_id) >= self.settings.import_max_concurrent_jobs_per_user:
            raise RuntimeError("You already have the maximum number of imports in progress")
        rows = parse_csv_import(content, source=source, default_media_type=default_media_type, max_rows=self.settings.import_max_rows)
        try:
            job = self.repo.create_job(
                user_id=user_id, source_platform=source, status=ImportJobStatus.PENDING,
                original_filename=self.sanitize_filename(filename), file_sha256=content_hash, total_rows=len(rows),
            )
            self.repo.create_items(job_id=job.id, rows=rows)
            self.db.commit()
            self.db.refresh(job)
            return job, True
        except IntegrityError:
            self.db.rollback()
            existing = self.repo.get_idempotent_job(user_id=user_id, source=source, file_sha256=content_hash)
            if existing:
                return existing, False
            raise

    async def process_job(self, job_id: uuid.UUID, *, worker_id: str) -> None:
        job = self.repo.claim_job(
            job_id=job_id,
            worker_id=worker_id,
            lease_seconds=self.settings.import_worker_lease_seconds,
        )
        if job is None:
            return
        self.db.commit()
        await self.process_claimed_job(job_id, worker_id=worker_id)

    async def process_claimed_job(self, job_id: uuid.UUID, *, worker_id: str) -> None:
        job = self.repo.get_job(job_id)
        if (
            job is None
            or job.status != ImportJobStatus.PROCESSING
            or job.worker_id != worker_id
        ):
            return
        try:
            for item in self.repo.pending_items(job.id):
                self.db.refresh(job)
                if job.status != ImportJobStatus.PROCESSING or job.worker_id != worker_id:
                    return
                await self._process_item(job, item)
                self._refresh_progress_and_finalize(job)
                self.repo.renew_lease(
                    job,
                    worker_id=worker_id,
                    now=datetime.now(timezone.utc),
                    lease_seconds=self.settings.import_worker_lease_seconds,
                )
                self.db.commit()
            self._refresh_progress_and_finalize(job)
            self.repo.release_claim(job, worker_id=worker_id)
            self.db.commit()
        except Exception:
            logger.exception("import_job_processing_failed", extra={"import_job_id": str(job_id)})
            self.db.rollback()
            job = self.repo.get_job(job_id)
            if job is not None and job.worker_id == worker_id:
                self.repo.set_job_status(job, ImportJobStatus.FAILED, datetime.now(timezone.utc), "The import worker stopped unexpectedly")
                self.db.commit()

    async def _process_item(self, job: ImportJob, item: ImportItem) -> None:
        media, confidence, candidates = await self._match_item(item)
        if media is None:
            if candidates:
                item.status = ImportItemStatus.CONFLICT
                item.match_candidates_json = candidates
                item.error_code = "AMBIGUOUS_MATCH"
                item.error_message = "Multiple local media records match this row"
            else:
                item.status = ImportItemStatus.FAILED
                item.error_code = "NO_MATCH"
                item.error_message = "No matching media record was found"
            return
        item.matched_media_id = media.id
        item.match_confidence = confidence
        item.match_candidates_json = []
        item.status = ImportItemStatus.MATCHED
        self._apply_item(job, item, overwrite=False)

    async def _match_item(self, item: ImportItem) -> tuple[Media | None, float | None, list[dict]]:
        payload = item.raw_payload_json
        media_type = MediaType(payload["media_type"])
        title = str(payload["title"])
        release_year = payload.get("release_year")
        provider = payload.get("external_provider")
        external_id = payload.get("external_id")
        if provider and external_id:
            db_provider = str(provider).strip().lower()
            if db_provider == "tmdb":
                db_provider = "tmdb_movie" if media_type == MediaType.MOVIE else "tmdb_tv" if media_type == MediaType.SERIES else db_provider
            exact_external = self.media.get_by_external_id(db_provider, str(external_id))
            if exact_external is not None:
                return exact_external, 1.0, []

        local_results = [candidate for candidate in self.media.search_local(title, media_type=media_type, limit=10) if candidate.deleted_at is None]
        normalized = normalize_title(title)
        exact_titles = [candidate for candidate in local_results if candidate.normalized_title == normalized]
        if release_year is not None:
            same_year = [candidate for candidate in exact_titles if candidate.release_year == release_year]
            if len(same_year) == 1:
                return same_year[0], 1.0, []
            if len(same_year) > 1:
                return None, None, self._candidate_payload(same_year)
        if len(exact_titles) == 1:
            return exact_titles[0], 0.95, []
        if len(exact_titles) > 1:
            return None, None, self._candidate_payload(exact_titles)

        provider_match = await self._match_provider(title=title, media_type=media_type, provider=provider, external_id=external_id)
        return provider_match, (0.9 if provider_match else None), []

    async def _match_provider(self, *, title: str, media_type: MediaType, provider: str | None, external_id: str | None) -> Media | None:
        media_service = MediaService(self.db, self.settings)
        if provider and external_id and provider.lower() in {"tmdb", "rawg", "google_books", "open_library", "spotify"}:
            try:
                return await media_service.upsert_by_external_id(provider, external_id, media_type)
            except (ValueError, KeyError):
                return None

        searches = [adapter.search(title, media_type, limit=5) for adapter in media_service._registry().providers_for_search(media_type)]
        if not searches:
            return None
        results = await asyncio.gather(*searches, return_exceptions=True)
        exact: list[ProviderSearchResult] = []
        title_normalized = normalize_title(title)
        for result in results:
            if isinstance(result, Exception):
                continue
            exact.extend(candidate for candidate in result if normalize_title(candidate.title) == title_normalized)
        if len(exact) != 1:
            return None
        candidate = exact[0]
        try:
            return await media_service.upsert_by_external_id(candidate.provider, candidate.external_id, media_type)
        except ValueError:
            return None

    @staticmethod
    def _candidate_payload(candidates: list[Media]) -> list[dict]:
        return [{"id": str(candidate.id), "title": candidate.canonical_title, "release_year": candidate.release_year, "media_type": candidate.media_type.value} for candidate in candidates]

    def _apply_item(self, job: ImportJob, item: ImportItem, *, overwrite: bool) -> None:
        if item.matched_media_id is None:
            raise ValueError("A media match is required before applying an import item")
        payload = item.raw_payload_json
        status = LibraryStatus(payload["status"])
        rating_value = payload.get("rating_value")
        existing = self.library.get_active_by_user_and_media(job.user_id, item.matched_media_id)
        if existing is not None:
            same_values = existing.status == status and existing.rating_value == rating_value
            if same_values:
                item.status = ImportItemStatus.SKIPPED
                item.resolution_action = "SKIP"
                return
            if not overwrite:
                item.status = ImportItemStatus.CONFLICT
                item.match_candidates_json = self._candidate_payload([existing.media]) if existing.media else []
                item.error_code = "LIBRARY_ENTRY_CONFLICT"
                item.error_message = "This title already exists in your library with different tracking data"
                return
            self.library.update(existing, status=status, rating_value=rating_value, source="import")
        else:
            entry = UserMediaEntry(
                user_id=job.user_id, media_id=item.matched_media_id, status=status, rating_value=rating_value,
                source="import", started_at=datetime.now(timezone.utc) if status == LibraryStatus.IN_PROGRESS else None,
                completed_at=datetime.now(timezone.utc) if status == LibraryStatus.COMPLETED else None,
            )
            self.db.add(entry)
            self.db.flush()
        item.status = ImportItemStatus.IMPORTED
        item.resolution_action = "IMPORT"
        item.error_code = None
        item.error_message = None

    def resolve_item(
        self, *, user_id: uuid.UUID, job_id: uuid.UUID, item_id: uuid.UUID, action: str,
        matched_media_id: uuid.UUID | None, status: LibraryStatus | None, rating_value: int | None,
    ) -> ImportJob:
        job = self.repo.get_job_owned(job_id=job_id, user_id=user_id, include_items=True)
        if job is None:
            raise LookupError("Import job not found")
        if job.status not in {ImportJobStatus.AWAITING_RESOLUTION, ImportJobStatus.PROCESSING}:
            raise ValueError("This import is not awaiting conflict resolution")
        item = next((candidate for candidate in job.items if candidate.id == item_id), None)
        if item is None or item.status != ImportItemStatus.CONFLICT:
            raise LookupError("Import conflict not found")
        if action == "SKIP":
            item.status = ImportItemStatus.SKIPPED
            item.resolution_action = "SKIP"
            item.error_code = None
            item.error_message = None
        else:
            if matched_media_id is None:
                raise ValueError("A media selection is required to import this row")
            media = self.media.get_by_id(matched_media_id)
            if media is None or media.deleted_at is not None:
                raise ValueError("Selected media was not found")
            if media.media_type != MediaType(item.raw_payload_json["media_type"]):
                raise ValueError("Selected media has a different media type than the imported row")
            item.matched_media_id = media.id
            if status is not None:
                item.raw_payload_json = {**item.raw_payload_json, "status": status.value}
            if rating_value is not None:
                item.raw_payload_json = {**item.raw_payload_json, "rating_value": rating_value}
            self._apply_item(job, item, overwrite=True)
        self._refresh_progress_and_finalize(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def cancel_job(self, *, user_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob:
        job = self.repo.get_job_owned(job_id=job_id, user_id=user_id)
        if job is None:
            raise LookupError("Import job not found")
        if job.status not in {ImportJobStatus.PENDING, ImportJobStatus.PROCESSING, ImportJobStatus.AWAITING_RESOLUTION}:
            raise ValueError("Only active imports can be cancelled")
        self.repo.set_job_status(job, ImportJobStatus.CANCELLED, datetime.now(timezone.utc))
        self.db.commit()
        return job

    def _refresh_progress_and_finalize(self, job: ImportJob) -> None:
        self.db.refresh(job, attribute_names=["items"])
        self.repo.update_progress(job)
        unresolved = any(item.status == ImportItemStatus.CONFLICT for item in job.items)
        remaining = any(item.status in {ImportItemStatus.PENDING, ImportItemStatus.MATCHED} for item in job.items)
        if unresolved and not remaining:
            job.status = ImportJobStatus.AWAITING_RESOLUTION
        elif not remaining:
            self.repo.set_job_status(job, ImportJobStatus.COMPLETED, datetime.now(timezone.utc))
