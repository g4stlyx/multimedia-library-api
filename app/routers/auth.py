from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rate_limit import RedisRateLimiter, get_client_ip, get_rate_limiter, rate_limit
from app.core.request_context import request_id_context
from app.core.security import hash_auth_identifier, hash_user_agent
from app.database import get_db
from app.models.user import User
from app.core.permissions import get_current_active_user
from app.schemas.auth import (
    AuthTokensResponse,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    VerifyEmailRequest,
)
from app.services.auth_service import (
    AuthRequestContext,
    AuthResult,
    AuthService,
    GENERIC_RESET_MESSAGE,
    GENERIC_VERIFICATION_MESSAGE,
)
from app.services.email_service import EmailDeliveryError, EmailService

router = APIRouter(prefix="/auth", tags=["auth"])


def _context_from_request(request: Request, settings: Settings) -> AuthRequestContext:
    return AuthRequestContext(
        ip_address=get_client_ip(request, settings),
        user_agent_hash=hash_user_agent(request.headers.get("User-Agent"), settings),
        request_id=request_id_context.get(),
    )


def _refresh_cookie_secure(settings: Settings) -> bool:
    return settings.app_env not in {"local", "test"}


def _set_refresh_cookie(
    response: Response,
    *,
    refresh_token: str,
    refresh_expires_at: datetime,
    settings: Settings,
) -> None:
    now = datetime.now(timezone.utc)
    max_age = max(int((refresh_expires_at - now).total_seconds()), 0)
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=_refresh_cookie_secure(settings),
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=_refresh_cookie_secure(settings),
        samesite="lax",
    )


def _token_response(result: AuthResult) -> AuthTokensResponse:
    now = datetime.now(timezone.utc)
    return AuthTokensResponse(
        access_token=result.tokens.access_token,
        access_expires_at=result.tokens.access_expires_at,
        access_expires_in=max(int((result.tokens.access_expires_at - now).total_seconds()), 0),
        refresh_token=result.tokens.refresh_token,
        refresh_expires_at=result.tokens.refresh_expires_at,
        refresh_expires_in=max(int((result.tokens.refresh_expires_at - now).total_seconds()), 0),
        user=result.user,
        email_verification_token=result.email_verification_token,
    )


def _send_email_verification_if_needed(
    *,
    settings: Settings,
    to_email: str,
    token: str | None,
) -> None:
    if not token:
        return
    try:
        EmailService(settings).send_email_verification(to_email=to_email, token=token)
    except EmailDeliveryError:
        return


def _send_password_reset_if_needed(
    *,
    settings: Settings,
    to_email: str | None,
    token: str | None,
) -> None:
    if not to_email or not token:
        return
    try:
        EmailService(settings).send_password_reset(to_email=to_email, token=token)
    except EmailDeliveryError:
        return


def _extract_refresh_token(
    request: Request,
    payload: RefreshRequest | LogoutRequest | None,
    settings: Settings,
) -> str | None:
    if payload and payload.refresh_token:
        return payload.refresh_token
    return request.cookies.get(settings.refresh_cookie_name)


@router.post(
    "/register",
    response_model=AuthTokensResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("auth:register", limit=5, window_seconds=3600))],
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthTokensResponse:
    result = AuthService(db, settings).register(
        email=str(payload.email),
        username=payload.username,
        display_name=payload.display_name,
        password=payload.password,
        context=_context_from_request(request, settings),
    )
    _set_refresh_cookie(
        response,
        refresh_token=result.tokens.refresh_token,
        refresh_expires_at=result.tokens.refresh_expires_at,
        settings=settings,
    )
    _send_email_verification_if_needed(
        settings=settings,
        to_email=result.user.email,
        token=result.email_verification_token_to_send,
    )
    return _token_response(result)


@router.post(
    "/login",
    response_model=AuthTokensResponse,
    dependencies=[Depends(rate_limit("auth:login", limit=20, window_seconds=300))],
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limiter: RedisRateLimiter = Depends(get_rate_limiter),
) -> AuthTokensResponse:
    identifier_hash = hash_auth_identifier(payload.identifier, settings)
    limiter.enforce(
        key=f"rate:auth:login:identifier:{identifier_hash}",
        limit=8,
        window_seconds=900,
    )
    result = AuthService(db, settings).login(
        identifier=payload.identifier,
        password=payload.password,
        context=_context_from_request(request, settings),
    )
    _set_refresh_cookie(
        response,
        refresh_token=result.tokens.refresh_token,
        refresh_expires_at=result.tokens.refresh_expires_at,
        settings=settings,
    )
    return _token_response(result)


@router.post(
    "/refresh",
    response_model=AuthTokensResponse,
    dependencies=[Depends(rate_limit("auth:refresh", limit=60, window_seconds=300))],
)
def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthTokensResponse:
    raw_refresh_token = _extract_refresh_token(request, payload, settings)
    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    result = AuthService(db, settings).refresh(
        raw_refresh_token=raw_refresh_token,
        context=_context_from_request(request, settings),
    )
    _set_refresh_cookie(
        response,
        refresh_token=result.tokens.refresh_token,
        refresh_expires_at=result.tokens.refresh_expires_at,
        settings=settings,
    )
    return _token_response(result)


@router.post(
    "/logout",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth:logout", limit=60, window_seconds=300))],
)
def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    AuthService(db, settings).logout(
        raw_refresh_token=_extract_refresh_token(request, payload, settings),
        context=_context_from_request(request, settings),
    )
    _clear_refresh_cookie(response, settings)
    return MessageResponse(message="Logged out")


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth:logout_all", limit=20, window_seconds=300))],
)
def logout_all(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    AuthService(db, settings).logout_all(
        user=current_user,
        context=_context_from_request(request, settings),
    )
    _clear_refresh_cookie(response, settings)
    return MessageResponse(message="Logged out from all devices")


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth:verify_email", limit=20, window_seconds=300))],
)
def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    AuthService(db, settings).verify_email(
        token=payload.token,
        context=_context_from_request(request, settings),
    )
    return MessageResponse(message="Email verified")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth:resend_verification", limit=5, window_seconds=3600))],
)
def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    result = AuthService(db, settings).resend_verification(
        email=str(payload.email),
        context=_context_from_request(request, settings),
    )
    _send_email_verification_if_needed(
        settings=settings,
        to_email=result.email_to_send or str(payload.email),
        token=result.token_to_send,
    )
    return MessageResponse(message=GENERIC_VERIFICATION_MESSAGE, token=result.token)


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth:password_reset_request", limit=5, window_seconds=3600))],
)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limiter: RedisRateLimiter = Depends(get_rate_limiter),
) -> MessageResponse:
    identifier_hash = hash_auth_identifier(str(payload.email), settings)
    limiter.enforce(
        key=f"rate:auth:password_reset:identifier:{identifier_hash}",
        limit=3,
        window_seconds=3600,
    )
    result = AuthService(db, settings).request_password_reset(
        email=str(payload.email),
        context=_context_from_request(request, settings),
    )
    _send_password_reset_if_needed(
        settings=settings,
        to_email=result.email_to_send,
        token=result.token_to_send,
    )
    return MessageResponse(message=GENERIC_RESET_MESSAGE, token=result.token)


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("auth:password_reset_confirm", limit=20, window_seconds=300))],
)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    AuthService(db, settings).confirm_password_reset(
        token=payload.token,
        new_password=payload.new_password,
        context=_context_from_request(request, settings),
    )
    return MessageResponse(message="Password reset completed")
