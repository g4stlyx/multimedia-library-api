from __future__ import annotations

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import get_current_active_user, assert_owner_or_admin
from app.database import get_db
from app.models.user import User
from app.schemas.list import ListCreate, ListUpdate, ListPublic, ListItemAdd, ListItemReorder, ListItemPublic, ListItemUpdate
from app.services.list_service import ListService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lists", tags=["lists"])


@router.post("", response_model=ListPublic, status_code=status.HTTP_201_CREATED)
def create_list(
    body: ListCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ListPublic:
    service = ListService(db)
    items_data = [item.model_dump() for item in body.items]
    try:
        return service.create_list(
            user_id=current_user.id,
            title=body.title,
            description=body.description,
            visibility=body.visibility,
            items_data=items_data
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=list[ListPublic])
def list_lists(
    user_id: uuid.UUID | None = Query(None),
    visibility: str | None = Query(None, pattern="^(public|followers|private)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> list[ListPublic]:
    service = ListService(db)
    offset = (page - 1) * limit
    return service.repo.list_lists(
        user_id=user_id,
        visibility=visibility,
        viewer_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


@router.get("/{list_id}", response_model=ListPublic)
def get_list(
    list_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ListPublic:
    service = ListService(db)
    mlist = service.repo.get_by_id(list_id)
    if not mlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    if mlist.visibility != "public" and mlist.user_id != current_user.id:
        assert_owner_or_admin(resource_user_id=mlist.user_id, current_user=current_user)
    return mlist


@router.patch("/{list_id}", response_model=ListPublic)
def update_list(
    list_id: uuid.UUID,
    body: ListUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ListPublic:
    service = ListService(db)
    mlist = service.repo.get_by_id(list_id)
    if not mlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    
    assert_owner_or_admin(resource_user_id=mlist.user_id, current_user=current_user)
    
    try:
        update_data = body.model_dump(exclude_unset=True)
        return service.update_list(list_id=list_id, user_id=mlist.user_id, **update_data)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(
    list_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Response:
    service = ListService(db)
    mlist = service.repo.get_by_id(list_id)
    if not mlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    
    assert_owner_or_admin(resource_user_id=mlist.user_id, current_user=current_user)
    
    try:
        service.delete_list(list_id=list_id, user_id=mlist.user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{list_id}/items", response_model=ListItemPublic, status_code=status.HTTP_201_CREATED)
def add_item_to_list(
    list_id: uuid.UUID,
    body: ListItemAdd,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ListItemPublic:
    service = ListService(db)
    try:
        return service.add_item_to_list(
            list_id=list_id,
            user_id=current_user.id,
            media_id=body.media_id,
            note=body.note
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{list_id}/items/{media_id}", response_model=ListItemPublic)
def update_list_item(
    list_id: uuid.UUID,
    media_id: uuid.UUID,
    body: ListItemUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ListItemPublic:
    service = ListService(db)
    try:
        return service.update_item_note(
            list_id=list_id,
            user_id=current_user.id,
            media_id=media_id,
            note=body.note,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{list_id}/items/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_item_from_list(
    list_id: uuid.UUID,
    media_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Response:
    service = ListService(db)
    try:
        service.remove_item_from_list(
            list_id=list_id,
            user_id=current_user.id,
            media_id=media_id
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{list_id}/items/reorder", response_model=ListPublic)
def reorder_list_items(
    list_id: uuid.UUID,
    body: ListItemReorder,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ListPublic:
    service = ListService(db)
    try:
        return service.reorder_list_items(
            list_id=list_id,
            user_id=current_user.id,
            media_ids=body.media_ids
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
