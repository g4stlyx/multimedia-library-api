from __future__ import annotations

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import get_current_active_user, assert_owner_or_admin
from app.database import get_db
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewUpdate, ReviewPublic
from app.services.review_service import ReviewService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewPublic, status_code=status.HTTP_201_CREATED)
def create_review(
    body: ReviewCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ReviewPublic:
    service = ReviewService(db)
    try:
        return service.create_review(
            user_id=current_user.id,
            media_id=body.media_id,
            rating_value=body.rating_value,
            body=body.body,
            contains_spoilers=body.contains_spoilers,
            visibility=body.visibility
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=list[ReviewPublic])
def list_reviews(
    media_id: uuid.UUID | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> list[ReviewPublic]:
    service = ReviewService(db)
    offset = (page - 1) * limit
    return service.repo.list_reviews(
        media_id=media_id,
        user_id=user_id,
        viewer_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


@router.get("/{review_id}", response_model=ReviewPublic)
def get_review(
    review_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ReviewPublic:
    service = ReviewService(db)
    review = service.repo.get_by_id(review_id)
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    if review.visibility != "public" and review.user_id != current_user.id:
        assert_owner_or_admin(resource_user_id=review.user_id, current_user=current_user)
    return review


@router.patch("/{review_id}", response_model=ReviewPublic)
def update_review(
    review_id: uuid.UUID,
    body: ReviewUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ReviewPublic:
    service = ReviewService(db)
    review = service.repo.get_by_id(review_id)
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    
    assert_owner_or_admin(resource_user_id=review.user_id, current_user=current_user)
    
    try:
        update_data = body.model_dump(exclude_unset=True)
        return service.update_review(review_id=review_id, user_id=review.user_id, **update_data)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Response:
    service = ReviewService(db)
    review = service.repo.get_by_id(review_id)
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    
    assert_owner_or_admin(resource_user_id=review.user_id, current_user=current_user)
    
    try:
        service.delete_review(review_id=review_id, user_id=review.user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
