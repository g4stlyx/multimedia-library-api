from __future__ import annotations

import uuid
from typing import Any
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, case
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import require_admin_level
from app.core.security import utcnow
from app.core.request_context import request_id_context
from app.database import get_db
from app.models.user import User, UserRole
from app.models.provider import ProviderRequest
from app.models.media import Media
from app.models.backup import BackupMetadata
from app.repositories.user_repository import UserRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.backup_repository import BackupRepository
from app.repositories.auth_repository import RefreshTokenRepository
from app.schemas.admin import (
    AuditLogListResponse,
    AuthErrorListResponse,
    BackupListResponse,
    BackupMetadataPublic,
    MediaAdminPublic,
    MediaMergeInput,
    UserListResponse,
    UserModerationInput,
    UserRoleUpdateInput,
)
from app.schemas.auth import UserPublic
from app.schemas.media import MediaPublic
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-logs", response_model=AuditLogListResponse)
def get_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    action: str | None = Query(None),
    actor_user_id: uuid.UUID | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(0)),
) -> Any:
    total, items = AuditRepository(db).get_audit_logs(
        limit=limit,
        offset=(page - 1) * limit,
        action=action,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    return {"total": total, "items": items}


@router.get("/auth-errors", response_model=AuthErrorListResponse)
def get_auth_error_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    error_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(0)),
) -> Any:
    total, items = AuditRepository(db).get_auth_error_logs(
        limit=limit,
        offset=(page - 1) * limit,
        error_type=error_type,
    )
    return {"total": total, "items": items}


@router.get("/users", response_model=UserListResponse)
def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
    role: UserRole | None = Query(None),
    is_banned: bool | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(1)),
) -> Any:
    total, items = UserRepository(db).list_users(
        limit=limit,
        offset=(page - 1) * limit,
        search_query=search,
        role=role,
        is_banned=is_banned,
    )
    return {"total": total, "items": items}


@router.post("/users/{user_id}/ban", response_model=UserPublic)
def ban_user(
    user_id: uuid.UUID,
    body: UserModerationInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(1)),
) -> Any:
    user_repo = UserRepository(db)
    target_user = user_repo.get_by_id(user_id)
    if not target_user or target_user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Security Guard: Admins cannot ban equal/higher level admins
    if target_user.role == UserRole.ADMIN and target_user.admin_level is not None:
        if current_user.admin_level is None or target_user.admin_level <= current_user.admin_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot ban an admin of equal or higher privilege level",
            )

    user_repo.ban_user(user=target_user, is_banned=body.banned)

    # Invalidate all active sessions if user is banned
    if body.banned:
        RefreshTokenRepository(db).revoke_all_for_user(user_id, utcnow())

    # Log action
    action = "user.banned" if body.banned else "user.unbanned"
    AuditRepository(db).create_audit_log(
        action=action,
        actor_user_id=current_user.id,
        resource_type="user",
        resource_id=str(user_id),
        created_at=datetime.now(timezone.utc),
        request_id=request_id_context.get(),
    )

    db.commit()
    return target_user


@router.patch("/users/{user_id}/role", response_model=UserPublic)
def update_user_role(
    user_id: uuid.UUID,
    body: UserRoleUpdateInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(0)),
) -> Any:
    user_repo = UserRepository(db)
    target_user = user_repo.get_by_id(user_id)
    if not target_user or target_user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role / admin level",
        )

    # Validate constraint
    if body.role == UserRole.ADMIN and body.admin_level not in (0, 1, 2):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin level must be 0, 1, or 2 for ADMIN role",
        )

    old_role = target_user.role
    old_level = target_user.admin_level

    user_repo.update_role_and_level(
        user=target_user,
        role=body.role,
        admin_level=body.admin_level,
    )

    # Log action
    AuditRepository(db).create_audit_log(
        action="user.role_updated",
        actor_user_id=current_user.id,
        resource_type="user",
        resource_id=str(user_id),
        metadata={
            "old_role": old_role,
            "new_role": body.role,
            "old_admin_level": old_level,
            "new_admin_level": body.admin_level,
        },
        created_at=datetime.now(timezone.utc),
        request_id=request_id_context.get(),
    )

    db.commit()
    return target_user


@router.get("/provider-health")
def get_provider_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(1)),
) -> Any:
    # Aggregated metrics per provider
    stmt = select(
        ProviderRequest.provider,
        func.count(ProviderRequest.id).label("total_requests"),
        func.avg(ProviderRequest.duration_ms).label("avg_duration_ms"),
        func.count(case((ProviderRequest.rate_limited == True, 1))).label("rate_limited_count"),
        func.count(case((ProviderRequest.status_code >= 200) & (ProviderRequest.status_code < 300, 1))).label("success_requests"),
    ).group_by(ProviderRequest.provider)
    
    rows = db.execute(stmt).all()
    health_data = []
    
    for row in rows:
        success_rate = (row.success_requests / row.total_requests) * 100 if row.total_requests > 0 else 100.0
        
        # Endpoint-specific details
        ep_stmt = select(
            ProviderRequest.endpoint,
            func.count(ProviderRequest.id).label("total_requests"),
            func.avg(ProviderRequest.duration_ms).label("avg_duration_ms"),
            func.count(case((ProviderRequest.rate_limited == True, 1))).label("rate_limited_count"),
            func.count(case((ProviderRequest.status_code >= 200) & (ProviderRequest.status_code < 300, 1))).label("success_requests"),
        ).where(ProviderRequest.provider == row.provider).group_by(ProviderRequest.endpoint)
        
        ep_rows = db.execute(ep_stmt).all()
        endpoints = []
        for ep in ep_rows:
            ep_success = (ep.success_requests / ep.total_requests) * 100 if ep.total_requests > 0 else 100.0
            endpoints.append({
                "endpoint": ep.endpoint,
                "total_requests": ep.total_requests,
                "success_rate": round(ep_success, 2),
                "avg_duration_ms": round(float(ep.avg_duration_ms), 2) if ep.avg_duration_ms else 0,
                "rate_limited_count": ep.rate_limited_count,
            })

        health_data.append({
            "provider": row.provider,
            "total_requests": row.total_requests,
            "success_rate": round(success_rate, 2),
            "avg_duration_ms": round(float(row.avg_duration_ms), 2) if row.avg_duration_ms else 0,
            "rate_limited_count": row.rate_limited_count,
            "endpoints": endpoints,
        })
        
    return health_data


@router.get("/duplicate-candidates", response_model=list[MediaPublic])
def get_duplicate_candidates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(1)),
) -> Any:
    return AdminService(db).get_duplicate_candidates()


@router.get("/media/{media_id}", response_model=MediaAdminPublic)
def get_media_for_admin(
    media_id: uuid.UUID,
    include_deleted: bool = Query(False, description="Include soft-deleted media"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(1)),
) -> MediaAdminPublic:
    media = AdminService(db).get_media(media_id=media_id, include_deleted=include_deleted)
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    return media


@router.post("/media/merge", response_model=MediaPublic)
def merge_media(
    body: MediaMergeInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(1)),
) -> Any:
    try:
        merged_media = AdminService(db).merge_media(
            source_id=body.source_id,
            target_id=body.target_id,
            actor_user=current_user,
            request_id=request_id_context.get(),
        )
        db.commit()
        return merged_media
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err)) from None
    except LookupError as lookup_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(lookup_err)) from None


@router.get("/backups", response_model=BackupListResponse)
def list_backups(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_level(0)),
) -> Any:
    repo = BackupRepository(db)
    items = repo.list_backups(limit=limit, offset=(page - 1) * limit)
    # Count total
    total = db.scalar(select(func.count(BackupMetadata.id))) or 0
    return {"total": total, "items": items}


@router.post("/backups/trigger", response_model=BackupMetadataPublic)
def trigger_backup(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(require_admin_level(0)),
) -> Any:
    repo = BackupRepository(db)
    now = datetime.now(timezone.utc)
    active_backup = repo.get_active_backup()
    if active_backup:
        started_at = active_backup.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        lease_expires_at = active_backup.lease_expires_at
        if lease_expires_at and lease_expires_at.tzinfo is None:
            lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)
        is_healthy_processing = (
            active_backup.status == "processing"
            and lease_expires_at is not None
            and lease_expires_at > now
        )
        is_recent_pending = (
            active_backup.status == "pending"
            and started_at > now - timedelta(minutes=settings.backup_max_runtime_minutes)
        )
        if is_healthy_processing or is_recent_pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A database backup is already running in the background",
            )
        repo.update_backup_failed(
            backup=active_backup,
            error_message="Marked failed after exceeding the configured backup runtime",
        )
        db.commit()

    try:
        backup_record = repo.create_backup_metadata(started_at=now)
        db.commit()
    except Exception:
        db.rollback()
        # The partial unique index serializes concurrent trigger requests.
        if repo.get_active_backup() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A database backup is already running in the background",
            ) from None
        raise

    return backup_record
