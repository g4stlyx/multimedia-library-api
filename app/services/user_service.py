from __future__ import annotations

from app.models.user import User
from app.repositories.audit_repository import AuditRepository
from app.repositories.user_repository import UserRepository
from app.core.security import utcnow


class UserService:
    def __init__(self, db):
        self.db = db
        self.users = UserRepository(db)
        self.audit = AuditRepository(db)

    def update_profile(
        self,
        *,
        user: User,
        display_name: str | None,
        request_id: str | None,
    ) -> User:
        updated_user = self.users.update_display_name(user=user, display_name=display_name)
        self.audit.create_audit_log(
            action="user.profile_updated",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            created_at=utcnow(),
            request_id=request_id,
        )
        self.db.commit()
        self.db.refresh(updated_user)
        return updated_user
