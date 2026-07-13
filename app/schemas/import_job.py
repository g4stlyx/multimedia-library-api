from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.import_job import ImportItemStatus, ImportJobStatus, ImportSource
from app.models.media import LibraryStatus, MediaType
from app.schemas.media import MediaPublic


class ImportItemPublic(BaseModel):
    id: uuid.UUID
    row_number: int
    raw_payload_json: dict
    matched_media_id: uuid.UUID | None
    match_confidence: float | None
    match_candidates_json: list[dict] = Field(default_factory=list)
    resolution_action: str | None
    status: ImportItemStatus
    error_code: str | None
    error_message: str | None
    matched_media: MediaPublic | None = None

    model_config = ConfigDict(from_attributes=True)


class ImportJobPublic(BaseModel):
    id: uuid.UUID
    source_platform: ImportSource
    status: ImportJobStatus
    original_filename: str | None
    total_rows: int
    processed_rows: int
    successful_rows: int
    failed_rows: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    items: list[ImportItemPublic] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ImportConflictResolution(BaseModel):
    matched_media_id: uuid.UUID | None = None
    action: str = Field(pattern="^(IMPORT|SKIP)$")
    status: LibraryStatus | None = None
    rating_value: int | None = Field(None, ge=1, le=100)
    media_type: MediaType | None = None
