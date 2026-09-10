"""Admin authorization, replay protection and rate limiting.

Deliberately small: the product has one privileged role (the operator that
registers sources, attests finality and records citations). No user accounts,
no sessions, no OAuth.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from typing import Dict, Optional, Tuple

from fastapi import Header, HTTPException, Request, status

from ..lib.genlayer.config import GenLayerConfig


class AdminDisabled(RuntimeError):
    pass


def require_admin(config: GenLayerConfig, token: Optional[str]) -> None:
    """Fail closed: with no token configured, nothing is writable."""
    if not config.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin writes are disabled: HOLDING_ADMIN_TOKEN is not configured",
        )
    if not token or not hmac.compare_digest(str(token), config.admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin authorization required",
        )


class IdempotencyStore:
    """Replay protection for writes. Keys are hashed; nothing sensitive is kept."""

    def __init__(self, ttl_seconds: int = 900) -> None:
        self.ttl = ttl_seconds
        self._entries: Dict[str, Tuple[float, object]] = {}
        self._lock = threading.Lock()

    def _key(self, scope: str, raw: str) -> str:
        return hashlib.sha256(f"{scope}:{raw}".encode()).hexdigest()

    def get(self, scope: str, key: str):
        hashed = self._key(scope, key)
        with self._lock:
            entry = self._entries.get(hashed)
            if entry is None:
                return None
            stored_at, value = entry
            if time.time() - stored_at > self.ttl:
                self._entries.pop(hashed, None)
                return None
            return value

    def put(self, scope: str, key: str, value: object) -> None:
        hashed = self._key(scope, key)
        with self._lock:
            self._entries[hashed] = (time.time(), value)


class RateLimiter:
    """Fixed-window limiter, per client. In-process: one Reporter instance."""

    def __init__(self, per_minute: int = 120) -> None:
        self.per_minute = max(1, int(per_minute))
        self._hits: Dict[str, Tuple[int, float]] = {}
        self._lock = threading.Lock()

    def check(self, client: str, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        window = int(now // 60)
        with self._lock:
            current, count = self._hits.get(client, (window, 0))
            if current != window:
                current, count = window, 0
            count += 1
            self._hits[client] = (current, count)
            if count > self.per_minute:
                retry_after = 60 - int(now % 60)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )


def client_of(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def idempotency_key(header: Optional[str]) -> str:
    key = (header or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required for writes",
        )
    if len(key) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key is too long",
        )
    return key


def admin_token_header(x_admin_token: Optional[str] = Header(default=None)) -> Optional[str]:
    return x_admin_token
