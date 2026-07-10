from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.request_context import request_id_context
from app.database import get_db
from app.core.permissions import get_current_active_user
from app.models.user import User
from app.schemas.auth import UpdateProfileRequest, UserPublic
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
