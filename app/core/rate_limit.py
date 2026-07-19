from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.permissions import get_current_active_user
from app.models.user import User

logger = logging.getLogger("app.rate_limit")


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int | None = None


class RedisRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def _get_client(self):
        if not self.settings.redis_url:
            return None

        if self._client is None:
            from redis import Redis

            self._client = Redis.from_url(
                self.settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        return self._client

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        client = self._get_client()
        if client is None:
            return RateLimitResult(allowed=True, remaining=limit)

        try:
            current = client.incr(key)
            if current == 1:
                client.expire(key, window_seconds)
            ttl = client.ttl(key)
        except Exception:
            if self.settings.app_env in {"production", "staging"}:
                logger.exception("redis_rate_limit_unavailable")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Rate limiter unavailable",
                )
            logger.warning("redis_rate_limit_bypassed")
            return RateLimitResult(allowed=True, remaining=limit)

        remaining = max(limit - int(current), 0)
        if current > limit:
            retry_after = ttl if ttl and ttl > 0 else window_seconds
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=retry_after,
            )
        return RateLimitResult(allowed=True, remaining=remaining)

    def enforce(self, key: str, limit: int, window_seconds: int) -> None:
        result = self.check(key, limit, window_seconds)
        if result.allowed:
            return
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(result.retry_after_seconds or window_seconds)},
        )


def get_client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_cloudflare_headers:
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def get_rate_limiter(settings: Settings = Depends(get_settings)) -> RedisRateLimiter:
    return RedisRateLimiter(settings)


def rate_limit(
    group: str,
    *,
    limit: int,
    window_seconds: int,
):
    def dependency(
        request: Request,
        settings: Settings = Depends(get_settings),
        limiter: RedisRateLimiter = Depends(get_rate_limiter),
    ) -> None:
        client_ip = get_client_ip(request, settings)
        limiter.enforce(
            key=f"rate:{group}:ip:{client_ip}",
            limit=limit,
            window_seconds=window_seconds,
        )

    return dependency


def rate_limit_user(
    group: str,
    *,
    limit: int,
    window_seconds: int,
):
    def dependency(
        current_user: User = Depends(get_current_active_user),
        limiter: RedisRateLimiter = Depends(get_rate_limiter),
    ) -> None:
        limiter.enforce(
            key=f"rate:{group}:user:{current_user.id}",
            limit=limit,
            window_seconds=window_seconds,
        )

    return dependency
