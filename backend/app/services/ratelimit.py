"""In-process sliding-window rate limiter.

Adequate for a single API instance. A horizontally scaled deployment should
back this with a shared store (e.g. Redis) — see README "Future improvements".
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import get_settings
from app.services import audit
from app.services.errors import AppError

LIMITS: dict[str, tuple[int, float]] = {
    "analyze": (20, 60.0),
    "redact": (30, 60.0),
    "preview": (240, 60.0),
    "share_create": (20, 60.0),
    "share_access": (60, 60.0),
    "share_manage": (30, 60.0),
    "auth_fail": (20, 300.0),
}


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, bucket: str, key: str) -> bool:
        limit, window = LIMITS[bucket]
        now = time.monotonic()
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def exceeded(self, bucket: str, key: str) -> bool:
        limit, window = LIMITS[bucket]
        now = time.monotonic()
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and q[0] <= now - window:
                q.popleft()
            return len(q) >= limit

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def rate_limit(bucket: str):
    def dependency(request: Request) -> None:
        ip = audit.client_ip(request, get_settings().trust_proxy_headers)
        if limiter.exceeded("auth_fail", ip) or not limiter.hit(bucket, ip):
            audit.record(audit.Event.RATE_LIMITED, request=request, outcome="denied", route=bucket)
            raise AppError(429, "rate_limited", "Too many requests. Please wait a moment and try again.")

    return dependency


def note_auth_failure(request: Request) -> None:
    ip = audit.client_ip(request, get_settings().trust_proxy_headers)
    limiter.hit("auth_fail", ip)
