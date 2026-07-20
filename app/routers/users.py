from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.request_context import request_id_context
from app.database import get_db
from app.core.permissions import get_current_active_user
from app.models.user import User
from app.schemas.auth import UpdateProfileRequest, UserPublic
from app.schemas.follow import FollowUserPublic
from app.services.follow_service import FollowService
from app.services.user_service import UserService

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_active_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserPublic)
def update_me(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> User:
    return UserService(db).update_profile(
        user=current_user,
        display_name=payload.display_name,
        request_id=request_id_context.get(),
    )


@router.put("/users/{user_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
def follow_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        FollowService(db).follow(follower=current_user, followed_id=user_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/users/{user_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Response:
    FollowService(db).unfollow(follower=current_user, followed_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/{user_id}/followers", response_model=list[FollowUserPublic])
def list_followers(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[FollowUserPublic]:
    return FollowService(db).follows.list_followers(
        user_id=user_id, limit=limit, offset=(page - 1) * limit
    )


@router.get("/users/{user_id}/following", response_model=list[FollowUserPublic])
def list_following(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[FollowUserPublic]:
    return FollowService(db).follows.list_following(
        user_id=user_id, limit=limit, offset=(page - 1) * limit
    )
