from __future__ import annotations

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import rate_limit, rate_limit_user
from app.core.request_context import request_id_context
from app.core.permissions import get_current_active_user, get_current_verified_user
from app.database import get_db
from app.models.media import MediaType
from app.models.user import User
from app.schemas.media import MediaDetailPublic, MediaExternalAddRequest, MediaPublic, MediaSearchResponse
from app.services.media_service import MediaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/popular", response_model=list[MediaPublic])
def list_popular_media(
    type: MediaType | None = Query(None, description="Optional media type filter"),
    limit: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[MediaPublic]:
    return MediaService(db, get_settings()).list_popular(media_type=type, limit=limit)


@router.get("/search", response_model=list[MediaSearchResponse])
async def search_media(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    type: MediaType | None = Query(None, description="Optional media type filter"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Max results per page"),
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("media:search", limit=60, window_seconds=300)),
    __: None = Depends(rate_limit_user("media:search", limit=120, window_seconds=300)),
) -> list[MediaSearchResponse]:
    settings = get_settings()
    service = MediaService(db, settings)
    return await service.search_media(
        query=q,
        media_type=type,
        page=page,
        limit=limit,
    )


@router.get("/{media_id}", response_model=MediaDetailPublic)
def get_media_details(
    media_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> MediaDetailPublic:
    settings = get_settings()
    service = MediaService(db, settings)
    media = service.get_media_details(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )
    return media


@router.post(
    "/{media_id}/refresh",
    response_model=MediaPublic,
    dependencies=[
        Depends(rate_limit("media:refresh", limit=20, window_seconds=300)),
        Depends(rate_limit_user("media:refresh", limit=20, window_seconds=300)),
    ],
)
async def refresh_media(
    media_id: uuid.UUID,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> MediaPublic:
    try:
        return await MediaService(db, get_settings()).refresh_media(
            media_id,
            actor_user_id=current_user.id,
            request_id=request_id_context.get(),
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from None
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None


@router.post(
    "/external/add",
    response_model=MediaPublic,
    dependencies=[
        Depends(rate_limit("media:external-add", limit=20, window_seconds=300)),
        Depends(rate_limit_user("media:external-add", limit=30, window_seconds=300)),
    ],
)
async def add_external_media(
    body: MediaExternalAddRequest,
    current_user: User = Depends(get_current_verified_user),
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
