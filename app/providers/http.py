from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from typing import Any

import requests
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    pass


class ProviderRateLimitError(ProviderError):
    def __init__(self, provider: str, retry_after: int | None = None) -> None:
        self.provider = provider
        self.retry_after = retry_after
        super().__init__(f"Provider {provider} rate limited. Retry after {retry_after}s.")


class ProviderRateController:
    """Process-local request pacing. Distributed workers should additionally use Redis."""

    _lock = threading.Lock()
    _next_request_at: dict[str, float] = defaultdict(float)

    @classmethod
    def wait_for_turn(cls, provider: str, requests_per_second: float) -> None:
        interval = 1 / requests_per_second
        with cls._lock:
            now = time.monotonic()
            wait_seconds = max(cls._next_request_at[provider] - now, 0)
            cls._next_request_at[provider] = max(cls._next_request_at[provider], now) + interval
        if wait_seconds:
            time.sleep(wait_seconds)


class ProviderHttpClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        settings: Settings,
        requests_per_second: float,
        db: Session | None = None,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.settings = settings
        self.requests_per_second = requests_per_second
        self.db = db

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        endpoint = f"{self.base_url}{path}"
        params = params or {}
        headers = headers or {}
        last_error: Exception | None = None
        for attempt in range(self.settings.provider_max_retries + 1):
            ProviderRateController.wait_for_turn(self.provider, self.requests_per_second)
            start = time.perf_counter()
            response: requests.Response | None = None
            try:
                response = requests.request(
                    method, endpoint, params=params, headers=headers, json=json_body, data=form_data,
                    timeout=self.settings.provider_timeout_seconds,
                )
                elapsed = int((time.perf_counter() - start) * 1000)
                self._log_request(path, params, response.status_code, elapsed, response.status_code == 429)
                if response.status_code == 429:
                    retry_after = self._retry_after(response, attempt)
                    if attempt >= self.settings.provider_max_retries:
                        raise ProviderRateLimitError(self.provider, retry_after)
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ProviderError(f"{self.provider} returned an invalid JSON response")
                return payload
            except ProviderRateLimitError:
                raise
            except (requests.RequestException, ValueError) as error:
                elapsed = int((time.perf_counter() - start) * 1000)
                if response is None:
                    self._log_request(path, params, 0, elapsed, False)
                last_error = error
                if attempt >= self.settings.provider_max_retries:
                    break
                time.sleep(min(2**attempt, 4))
        raise ProviderError(f"{self.provider} request failed") from last_error

    @staticmethod
    def _retry_after(response: requests.Response, attempt: int) -> int:
        value = response.headers.get("Retry-After")
        if value and value.isdigit():
            return min(max(int(value), 1), 60)
        return min(2 ** (attempt + 1), 30)

    def _log_request(self, path: str, params: dict[str, Any], status_code: int, duration_ms: int, rate_limited: bool) -> None:
        if self.db is None or self.db.bind is None:
            return
        safe_params = {key: value for key, value in params.items() if not any(secret in key.lower() for secret in ("key", "token", "secret", "authorization"))}
        request_hash = hashlib.sha256(json.dumps({"provider": self.provider, "path": path, "params": safe_params}, sort_keys=True, default=str).encode()).hexdigest()
        try:
            from app.repositories.media_repository import MediaRepository
            log_session = sessionmaker(bind=self.db.bind)()
            try:
                MediaRepository(log_session).log_provider_request(self.provider, path, request_hash, status_code, duration_ms, rate_limited)
                log_session.commit()
            finally:
                log_session.close()
        except Exception:
            logger.exception("provider_request_log_failed", extra={"provider": self.provider, "endpoint": path})
