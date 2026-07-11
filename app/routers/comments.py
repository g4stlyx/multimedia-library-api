from __future__ import annotations

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import get_current_active_user, assert_owner_or_admin
from app.database import get_db
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentUpdate, CommentPublic
from app.services.comment_service import CommentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/comments", tags=["comments"])


@router.post("", response_model=CommentPublic, status_code=status.HTTP_201_CREATED)
def create_comment(
    body: CommentCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> CommentPublic:
    service = CommentService(db)
    try:
        service.verify_target_access(body.target_type, body.target_id, current_user)
        return service.add_comment(
            user_id=current_user.id,
            target_type=body.target_type,
            target_id=body.target_id,
            body=body.body,
            parent_comment_id=body.parent_comment_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=list[CommentPublic])
def list_comments(
    target_type: str = Query(..., pattern="^(review|list|media)$"),
    target_id: uuid.UUID = Query(...),
    parent_comment_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> list[CommentPublic]:
    service = CommentService(db)
    offset = (page - 1) * limit
    try:
        service.verify_target_access(target_type, target_id, current_user)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return service.repo.list_comments_for_target(
        target_type=target_type,
        target_id=target_id,
        parent_comment_id=parent_comment_id,
        limit=limit,
        offset=offset
    )


@router.patch("/{comment_id}", response_model=CommentPublic)
def update_comment(
    comment_id: uuid.UUID,
    body: CommentUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> CommentPublic:
    service = CommentService(db)
    comment = service.repo.get_by_id(comment_id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    assert_owner_or_admin(resource_user_id=comment.user_id, current_user=current_user)
    
    try:
        return service.update_comment(comment_id=comment_id, user_id=comment.user_id, body=body.body)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Response:
    service = CommentService(db)
    comment = service.repo.get_by_id(comment_id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    assert_owner_or_admin(resource_user_id=comment.user_id, current_user=current_user)
    
    try:
        service.delete_comment(comment_id=comment_id, user_id=comment.user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
