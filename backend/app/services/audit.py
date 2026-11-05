"""Security audit trail.

Events are written to the `audit_events` table in their own short transaction
so that a failed request still leaves a record. Details are restricted to an
allow-list of non-sensitive keys; client IPs are pseudonymised with HMAC.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from fastapi import Request

from app.crypto.tokens import pseudonymize
from app.db import session_factory
from app.models.orm import AuditEvent

log = logging.getLogger("afterimage.audit")


class Event(StrEnum):
    FILE_ANALYZED = "file.analyzed"
    FILE_REJECTED = "file.rejected"
    REDACTION_COMPLETED = "redaction.completed"
    REDACTION_FAILED = "redaction.failed"
    ARTIFACT_DOWNLOADED = "artifact.downloaded"
    SHARE_CREATED = "share.created"
    SHARE_ACCESSED = "share.accessed"
    SHARE_DOWNLOADED = "share.downloaded"
    SHARE_DENIED_EXPIRED = "share.denied.expired"
    SHARE_DENIED_REVOKED = "share.denied.revoked"
    SHARE_DENIED_LIMIT = "share.denied.download_limit"
    SHARE_NOT_FOUND = "share.denied.not_found"
    SHARE_REVOKED = "share.revoked"
    AUTH_FAILED = "auth.failed"
    RATE_LIMITED = "request.rate_limited"
    REQUEST_REJECTED = "request.rejected"
    CLEANUP_RUN = "maintenance.cleanup"


_ALLOWED_DETAIL_KEYS = {
    "reason", "kind", "mime", "size", "pages", "detections", "categories", "selected",
    "manual", "rasterized", "expires_in", "max_downloads", "download_count", "route",
    "sessions", "artifacts", "shares", "originals", "verification", "metadata_removed",
}


def client_ip(request: Request | None, trust_proxy: bool = False) -> str:
    if request is None:
        return "internal"
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def record(
    event: Event,
    *,
    request: Request | None = None,
    outcome: str = "success",
    session_id: str | None = None,
    artifact_id: str | None = None,
    share_id: str | None = None,
    **details: object,
) -> None:
    from app.config import get_settings

    settings = get_settings()
    safe = {k: v for k, v in details.items() if k in _ALLOWED_DETAIL_KEYS}
    actor = pseudonymize(client_ip(request, settings.trust_proxy_headers), settings.audit_secret_bytes())
    try:
        with session_factory()() as db:
            db.add(
                AuditEvent(
                    event_type=str(event),
                    outcome=outcome,
                    actor=actor,
                    session_id=session_id,
                    artifact_id=artifact_id,
                    share_id=share_id,
                    details=safe,
                )
            )
            db.commit()
    except Exception:  # auditing must never take the request down, but must be visible
        log.exception("failed to persist audit event %s", event)
