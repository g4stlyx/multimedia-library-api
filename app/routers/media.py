from __future__ import annotations

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import get_current_active_user
from app.database import get_db
from app.models.media import MediaType
from app.models.user import User
from app.schemas.media import MediaExternalAddRequest, MediaPublic, MediaSearchResponse
from app.services.media_service import MediaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/search", response_model=list[MediaSearchResponse])
async def search_media(
    q: str = Query(..., min_length=1, description="Search query"),
    type: MediaType | None = Query(None, description="Optional media type filter"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Max results per page"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[MediaSearchResponse]:
    settings = get_settings()
    service = MediaService(db, settings)
    return await service.search_media(
        query=q,
        media_type=type,
        page=page,
        limit=limit,
    )


@router.get("/{media_id}", response_model=MediaPublic)
def get_media_details(
    media_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> MediaPublic:
    settings = get_settings()
    service = MediaService(db, settings)
    media = service.repo.get_by_id(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )
    return media


@router.post("/external/add", response_model=MediaPublic)
async def add_external_media(
    body: MediaExternalAddRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> MediaPublic:
    settings = get_settings()
    service = MediaService(db, settings)
    try:
        media = await service.upsert_by_external_id(
            provider=body.provider,
            external_id=body.external_id,
            media_type=body.media_type,
        )
        return media
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Failed to upsert external media: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while importing external media details",
        )
