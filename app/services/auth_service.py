from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.normalization import normalize_email
from app.core.security import (
    PASSWORD_HASH_ALGORITHM,
    create_access_token,
    generate_opaque_token,
    generate_uuid,
    hash_auth_identifier,
    hash_password,
    hash_token,
    password_hash_params,
    password_needs_rehash,
    utcnow,
    verify_password,
)
from app.models.user import User
from app.repositories.audit_repository import AuditRepository
from app.repositories.auth_repository import (
    EmailVerificationTokenRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
)
from app.repositories.user_repository import UserRepository

logger = logging.getLogger("app.auth")

GENERIC_AUTH_ERROR = "Invalid email, username, or password"
GENERIC_RESET_MESSAGE = "If the account exists, a password reset email will be sent"
GENERIC_VERIFICATION_MESSAGE = "If the account exists, a verification email will be sent"


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_after(left: datetime, right: datetime) -> bool:
    return _as_aware_utc(left) > _as_aware_utc(right)


def _is_expired(value: datetime, now: datetime) -> bool:
    return _as_aware_utc(value) <= _as_aware_utc(now)


@dataclass(frozen=True)
class AuthRequestContext:
    ip_address: str | None
    user_agent_hash: str | None
    request_id: str | None


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    access_expires_at: datetime
    access_jti: str
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True)
class AuthResult:
    user: User
    tokens: TokenPair
    email_verification_token: str | None = None
    email_verification_token_to_send: str | None = None


@dataclass(frozen=True)
class IssuedTokenResult:
    message: str
    token: str | None = None
    token_to_send: str | None = None
    email_to_send: str | None = None


class AuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.users = UserRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)
        self.email_tokens = EmailVerificationTokenRepository(db)
        self.password_tokens = PasswordResetTokenRepository(db)
        self.audit = AuditRepository(db)

    def register(
        self,
        *,
        email: str,
        username: str,
        display_name: str | None,
        password: str,
        context: AuthRequestContext,
    ) -> AuthResult:
        now = utcnow()
        if self.users.email_or_username_exists(email=email, username=username):
            self._log_auth_error(
                "register_identifier_unavailable",
                now=now,
                context=context,
                identifier=email,
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username is unavailable",
            )

        try:
            user = self.users.create_user(
                email=email,
                username=username,
                display_name=display_name,
            )
            self.users.create_credentials(
                user_id=user.id,
                password_hash=hash_password(password, self.settings),
                password_hash_algorithm=PASSWORD_HASH_ALGORITHM,
                password_hash_params=password_hash_params(),
                password_changed_at=now,
            )
            verification_token = self._create_email_verification_token(
                user=user,
                now=now,
            )
            tokens = self._issue_token_pair(user=user, now=now, context=context)
            self.audit.create_audit_log(
                action="auth.register",
                actor_user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                created_at=now,
                ip_address=context.ip_address,
                user_agent_hash=context.user_agent_hash,
                request_id=context.request_id,
            )
            self.db.commit()
            return AuthResult(
                user=user,
                tokens=tokens,
                email_verification_token=self._maybe_expose_dev_token(verification_token),
                email_verification_token_to_send=verification_token,
            )
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username is unavailable",
            ) from None

    def login(
        self,
        *,
        identifier: str,
        password: str,
        context: AuthRequestContext,
    ) -> AuthResult:
        now = utcnow()
        user = self.users.get_by_identifier(identifier)
        identifier_hash = hash_auth_identifier(identifier, self.settings)

        if user is None or user.credentials is None or user.deleted_at is not None:
            self._log_auth_error(
                "failed_login",
                now=now,
                context=context,
                identifier_hash=identifier_hash,
            )
            self.db.commit()
            raise self._invalid_login_error()

        credentials = user.credentials
        if credentials.locked_until and _is_after(credentials.locked_until, now):
            self._log_auth_error(
                "locked_account_login_attempt",
                now=now,
                context=context,
                identifier_hash=identifier_hash,
                user_id=user.id,
            )
            self.db.commit()
            raise self._invalid_login_error()

        if not user.is_active or user.is_banned:
            self._log_auth_error(
                "inactive_or_banned_login_attempt",
                now=now,
                context=context,
                identifier_hash=identifier_hash,
                user_id=user.id,
            )
            self.db.commit()
            raise self._invalid_login_error()

        if not verify_password(password, credentials.password_hash, self.settings):
            credentials.failed_login_count += 1
            if credentials.failed_login_count >= 5:
                credentials.locked_until = now + timedelta(minutes=15)
            self._log_auth_error(
                "failed_login",
                now=now,
                context=context,
                identifier_hash=identifier_hash,
                user_id=user.id,
            )
            self.db.commit()
            raise self._invalid_login_error()

        if password_needs_rehash(credentials.password_hash):
            credentials.password_hash = hash_password(password, self.settings)
            credentials.password_hash_params = password_hash_params()

        credentials.failed_login_count = 0
        credentials.locked_until = None
        tokens = self._issue_token_pair(user=user, now=now, context=context)
        self.audit.create_audit_log(
            action="auth.login",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            created_at=now,
            ip_address=context.ip_address,
            user_agent_hash=context.user_agent_hash,
            request_id=context.request_id,
        )
        self.db.commit()
        return AuthResult(user=user, tokens=tokens)

    def refresh(
        self,
        *,
        raw_refresh_token: str,
        context: AuthRequestContext,
    ) -> AuthResult:
        now = utcnow()
        refresh_token = self.refresh_tokens.get_by_hash(
            hash_token(raw_refresh_token, self.settings)
        )
        if refresh_token is None:
            self._log_auth_error(
                "invalid_refresh_token",
                now=now,
                context=context,
            )
            self.db.commit()
            raise self._invalid_refresh_error()

        if refresh_token.revoked_at is not None:
            refresh_token.reuse_detected_at = refresh_token.reuse_detected_at or now
            self.refresh_tokens.revoke_family(refresh_token.family_id, now)
            self._log_auth_error(
                "refresh_token_reuse",
                now=now,
                context=context,
                user_id=refresh_token.user_id,
            )
            self.audit.create_audit_log(
                action="auth.refresh_token_reuse_detected",
                actor_user_id=refresh_token.user_id,
                resource_type="refresh_token_family",
                resource_id=str(refresh_token.family_id),
                created_at=now,
                ip_address=context.ip_address,
                user_agent_hash=context.user_agent_hash,
                request_id=context.request_id,
            )
            self.db.commit()
            raise self._invalid_refresh_error()

        if _is_expired(refresh_token.expires_at, now):
            self.refresh_tokens.revoke(refresh_token, now)
            self._log_auth_error(
                "expired_refresh_token",
                now=now,
                context=context,
                user_id=refresh_token.user_id,
            )
            self.db.commit()
            raise self._invalid_refresh_error()

        user = refresh_token.user
        if (
            user is None
            or not user.is_active
            or user.is_banned
            or user.deleted_at is not None
        ):
            self.refresh_tokens.revoke_family(refresh_token.family_id, now)
            self._log_auth_error(
                "refresh_for_inactive_or_banned_account",
                now=now,
                context=context,
                user_id=refresh_token.user_id,
            )
            self.db.commit()
            raise self._invalid_refresh_error()

        new_raw_refresh = generate_opaque_token()
        new_expires_at = now + timedelta(days=self.settings.jwt_refresh_ttl_days)
        new_refresh = self.refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_token(new_raw_refresh, self.settings),
            family_id=refresh_token.family_id,
            expires_at=new_expires_at,
            created_at=now,
            ip_address=context.ip_address,
            user_agent_hash=context.user_agent_hash,
        )
        refresh_token.revoked_at = now
        refresh_token.replaced_by_token_id = new_refresh.id

        access_token, access_expires_at, access_jti = create_access_token(
            user_id=user.id,
            role=user.role.value,
            admin_level=user.admin_level,
            settings=self.settings,
        )
        self.db.commit()
        return AuthResult(
            user=user,
            tokens=TokenPair(
                access_token=access_token,
                access_expires_at=access_expires_at,
                access_jti=access_jti,
                refresh_token=new_raw_refresh,
                refresh_expires_at=new_expires_at,
            ),
        )

    def logout(
        self,
        *,
        raw_refresh_token: str | None,
        context: AuthRequestContext,
    ) -> None:
        now = utcnow()
        if raw_refresh_token:
            refresh_token = self.refresh_tokens.get_by_hash(
                hash_token(raw_refresh_token, self.settings)
            )
            if refresh_token and refresh_token.revoked_at is None:
                self.refresh_tokens.revoke(refresh_token, now)
                self.audit.create_audit_log(
                    action="auth.logout",
                    actor_user_id=refresh_token.user_id,
                    resource_type="refresh_token",
                    resource_id=str(refresh_token.id),
                    created_at=now,
                    ip_address=context.ip_address,
                    user_agent_hash=context.user_agent_hash,
                    request_id=context.request_id,
                )
        self.db.commit()

    def logout_all(self, *, user: User, context: AuthRequestContext) -> None:
        now = utcnow()
        self.refresh_tokens.revoke_all_for_user(user.id, now)
        self.audit.create_audit_log(
            action="auth.logout_all",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            created_at=now,
            ip_address=context.ip_address,
            user_agent_hash=context.user_agent_hash,
            request_id=context.request_id,
        )
        self.db.commit()

    def verify_email(self, *, token: str, context: AuthRequestContext) -> None:
        now = utcnow()
        stored_token = self.email_tokens.get_by_hash(hash_token(token, self.settings))
        if (
            stored_token is None
            or stored_token.consumed_at is not None
            or _is_expired(stored_token.expires_at, now)
        ):
            self._log_auth_error(
                "invalid_verification_token",
                now=now,
                context=context,
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token",
            )

        if stored_token.user.email_verified_at is None:
            stored_token.user.email_verified_at = now
        self.email_tokens.consume_all_for_user(stored_token.user_id, now)
        self.audit.create_audit_log(
            action="auth.email_verified",
            actor_user_id=stored_token.user_id,
            resource_type="user",
            resource_id=str(stored_token.user_id),
            created_at=now,
            ip_address=context.ip_address,
            user_agent_hash=context.user_agent_hash,
            request_id=context.request_id,
        )
        self.db.commit()

    def resend_verification(
        self,
        *,
        email: str,
        context: AuthRequestContext,
    ) -> IssuedTokenResult:
        now = utcnow()
        user = self.users.get_by_email_normalized(normalize_email(email))
        raw_token = None
        if (
            user is not None
            and user.is_active
            and not user.is_banned
            and user.email_verified_at is None
            and user.deleted_at is None
        ):
            raw_token = self._create_email_verification_token(user=user, now=now)
        self.db.commit()
        return IssuedTokenResult(
            message=GENERIC_VERIFICATION_MESSAGE,
            token=self._maybe_expose_dev_token(raw_token),
            token_to_send=raw_token,
            email_to_send=user.email if raw_token and user else None,
        )

    def request_password_reset(
        self,
        *,
        email: str,
        context: AuthRequestContext,
    ) -> IssuedTokenResult:
        now = utcnow()
        user = self.users.get_by_email_normalized(normalize_email(email))
        raw_token = None
        if user is not None and user.is_active and not user.is_banned and user.deleted_at is None:
            raw_token = self._create_password_reset_token(user=user, now=now)
            self.audit.create_audit_log(
                action="auth.password_reset_requested",
                actor_user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                created_at=now,
                ip_address=context.ip_address,
                user_agent_hash=context.user_agent_hash,
                request_id=context.request_id,
            )
        self.db.commit()
        return IssuedTokenResult(
            message=GENERIC_RESET_MESSAGE,
            token=self._maybe_expose_dev_token(raw_token),
            token_to_send=raw_token,
            email_to_send=user.email if raw_token and user else None,
        )

    def confirm_password_reset(
        self,
        *,
        token: str,
        new_password: str,
        context: AuthRequestContext,
    ) -> None:
        now = utcnow()
        stored_token = self.password_tokens.get_by_hash(hash_token(token, self.settings))
        if (
            stored_token is None
            or stored_token.consumed_at is not None
            or _is_expired(stored_token.expires_at, now)
        ):
            self._log_auth_error(
                "invalid_password_reset_token",
                now=now,
                context=context,
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired password reset token",
            )

        user = stored_token.user
        if user.credentials is None:
            self._log_auth_error(
                "password_reset_without_credentials",
                now=now,
                context=context,
                user_id=user.id,
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired password reset token",
            )

        user.credentials.password_hash = hash_password(new_password, self.settings)
        user.credentials.password_hash_params = password_hash_params()
        user.credentials.password_changed_at = now
        user.credentials.failed_login_count = 0
        user.credentials.locked_until = None
        self.password_tokens.consume_all_for_user(user.id, now)
        self.refresh_tokens.revoke_all_for_user(user.id, now)
        self.audit.create_audit_log(
            action="auth.password_reset_completed",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            created_at=now,
            ip_address=context.ip_address,
            user_agent_hash=context.user_agent_hash,
            request_id=context.request_id,
        )
        self.db.commit()

    def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
        context: AuthRequestContext,
    ) -> None:
        now = utcnow()
        if user.credentials is None or not verify_password(
            current_password, user.credentials.password_hash, self.settings
        ):
            self._log_auth_error(
                "invalid_password_change_attempt",
                now=now,
                context=context,
                user_id=user.id,
            )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        user.credentials.password_hash = hash_password(new_password, self.settings)
        user.credentials.password_hash_params = password_hash_params()
        user.credentials.password_changed_at = now
        user.credentials.failed_login_count = 0
        user.credentials.locked_until = None
        self.refresh_tokens.revoke_all_for_user(user.id, now)
        self.audit.create_audit_log(
            action="auth.password_changed",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            created_at=now,
            ip_address=context.ip_address,
            user_agent_hash=context.user_agent_hash,
            request_id=context.request_id,
        )
        self.db.commit()

    def _issue_token_pair(
        self,
        *,
        user: User,
        now: datetime,
        context: AuthRequestContext,
        family_id: uuid.UUID | None = None,
    ) -> TokenPair:
        access_token, access_expires_at, access_jti = create_access_token(
            user_id=user.id,
            role=user.role.value,
            admin_level=user.admin_level,
            settings=self.settings,
        )
        raw_refresh_token = generate_opaque_token()
        refresh_expires_at = now + timedelta(days=self.settings.jwt_refresh_ttl_days)
        self.refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_token(raw_refresh_token, self.settings),
            family_id=family_id or generate_uuid(),
            expires_at=refresh_expires_at,
            created_at=now,
            ip_address=context.ip_address,
            user_agent_hash=context.user_agent_hash,
        )
        return TokenPair(
            access_token=access_token,
            access_expires_at=access_expires_at,
            access_jti=access_jti,
            refresh_token=raw_refresh_token,
            refresh_expires_at=refresh_expires_at,
        )

    def _create_email_verification_token(self, *, user: User, now: datetime) -> str:
        raw_token = generate_opaque_token()
        self.email_tokens.create(
            user_id=user.id,
            token_hash=hash_token(raw_token, self.settings),
            expires_at=now + timedelta(hours=self.settings.email_verification_ttl_hours),
            created_at=now,
        )
        return raw_token

    def _create_password_reset_token(self, *, user: User, now: datetime) -> str:
        raw_token = generate_opaque_token()
        self.password_tokens.create(
            user_id=user.id,
            token_hash=hash_token(raw_token, self.settings),
            expires_at=now + timedelta(minutes=self.settings.password_reset_ttl_minutes),
            created_at=now,
        )
        return raw_token

    def _log_auth_error(
        self,
        error_type: str,
        *,
        now: datetime,
        context: AuthRequestContext,
        identifier: str | None = None,
        identifier_hash: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> None:
        email_or_username_hash = identifier_hash
        if identifier and identifier_hash is None:
            email_or_username_hash = hash_auth_identifier(identifier, self.settings)
        self.audit.create_auth_error_log(
            error_type=error_type,
            email_or_username_hash=email_or_username_hash,
            user_id=user_id,
            ip_address=context.ip_address,
            user_agent_hash=context.user_agent_hash,
            request_id=context.request_id,
            created_at=now,
        )
        logger.warning(
            "auth_error",
            extra={
                "request_id": context.request_id,
                "error_type": error_type,
                "user_id": str(user_id) if user_id else None,
            },
        )

    def _maybe_expose_dev_token(self, token: str | None) -> str | None:
        if self.settings.app_env in {"local", "test"}:
            return token
        return None

    def _invalid_login_error(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_AUTH_ERROR,
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _invalid_refresh_error(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
