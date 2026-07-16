from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog, AuthErrorLog


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_audit_log(
        self,
        *,
        action: str,
        created_at: datetime,
        actor_user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent_hash: str | None = None,
        request_id: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=metadata,
            ip_address=ip_address,
            user_agent_hash=user_agent_hash,
            request_id=request_id,
            created_at=created_at,
        )
        self.db.add(log)
        self.db.flush()
        return log

    def create_auth_error_log(
        self,
        *,
        error_type: str,
        created_at: datetime,
        email_or_username_hash: str | None = None,
        user_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent_hash: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuthErrorLog:
        log = AuthErrorLog(
            error_type=error_type,
            email_or_username_hash=email_or_username_hash,
            user_id=user_id,
            ip_address=ip_address,
            user_agent_hash=user_agent_hash,
            request_id=request_id,
            metadata_json=metadata,
            created_at=created_at,
        )
        self.db.add(log)
        self.db.flush()
        return log

    def get_audit_logs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        action: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> tuple[int, list[AuditLog]]:
        from sqlalchemy import select, func
        stmt = select(AuditLog)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if actor_user_id:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if resource_id:
            stmt = stmt.where(AuditLog.resource_id == resource_id)

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        items = self.db.scalars(stmt).all()
        return total, list(items)

    def get_auth_error_logs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        error_type: str | None = None,
    ) -> tuple[int, list[AuthErrorLog]]:
        from sqlalchemy import select, func
        stmt = select(AuthErrorLog)
        if error_type:
            stmt = stmt.where(AuthErrorLog.error_type == error_type)

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        
        stmt = stmt.order_by(AuthErrorLog.created_at.desc()).offset(offset).limit(limit)
        items = self.db.scalars(stmt).all()
        return total, list(items)

