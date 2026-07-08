from __future__ import annotations

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import get_current_active_user, assert_owner_or_admin
from app.database import get_db
from app.models.media import LibraryStatus
from app.models.user import User
from app.schemas.library import LibraryEntryCreate, LibraryEntryUpdate, LibraryEntryPublic
from app.services.library_service import LibraryService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/library", tags=["library"])


@router.post("", response_model=LibraryEntryPublic, status_code=status.HTTP_201_CREATED)
def add_to_library(
    body: LibraryEntryCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> LibraryEntryPublic:
    service = LibraryService(db)
    try:
        return service.add_to_library(
            user_id=current_user.id,
            media_id=body.media_id,
            status=body.status,
            rating_value=body.rating_value,
            progress_value=body.progress_value,
            progress_total=body.progress_total,
            progress_unit=body.progress_unit,
            notes_private=body.notes_private,
            is_favorite=body.is_favorite,
            source="manual"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=list[LibraryEntryPublic])
def list_library(
    status: LibraryStatus | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> list[LibraryEntryPublic]:
    service = LibraryService(db)
    offset = (page - 1) * limit
    return service.repo.list_by_user(user_id=current_user.id, status=status, limit=limit, offset=offset)


@router.get("/media/{media_id}", response_model=LibraryEntryPublic)
def get_library_by_media(
    media_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> LibraryEntryPublic:
    service = LibraryService(db)
    entry = service.repo.get_active_by_user_and_media(user_id=current_user.id, media_id=media_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library entry not found")
    return entry


@router.get("/{entry_id}", response_model=LibraryEntryPublic)
def get_library_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> LibraryEntryPublic:
    service = LibraryService(db)
    entry = service.repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library entry not found")
    # Verify owner or admin
    assert_owner_or_admin(resource_user_id=entry.user_id, current_user=current_user)
    return entry


@router.patch("/{entry_id}", response_model=LibraryEntryPublic)
def update_library_entry(
    entry_id: uuid.UUID,
    body: LibraryEntryUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> LibraryEntryPublic:
    service = LibraryService(db)
    entry = service.repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library entry not found")
    
    assert_owner_or_admin(resource_user_id=entry.user_id, current_user=current_user)
    
    try:
        update_data = body.model_dump(exclude_unset=True)
        return service.update_entry(entry_id=entry_id, user_id=entry.user_id, **update_data)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Response:
    service = LibraryService(db)
    entry = service.repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library entry not found")
    
    assert_owner_or_admin(resource_user_id=entry.user_id, current_user=current_user)
    
    try:
        service.remove_from_library(entry_id=entry_id, user_id=entry.user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
