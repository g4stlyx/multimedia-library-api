from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.permissions import get_current_active_user
from app.models.user import User
from app.schemas.auth import UserPublic

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_active_user)) -> User:
    return current_user
