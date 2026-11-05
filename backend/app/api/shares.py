from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TOKEN_PATTERN, UUID_PATTERN, bearer, services, session_token
from app.api.responses import file_response
from app.db import get_db
from app.models.orm import AuditEvent
from app.schemas.api import ShareCreate, ShareCreated, SharePublic, ShareStatus
from app.services import audit, sessions
from app.services.context import Services
from app.services.errors import AppError, unauthorized
from app.services.ratelimit import note_auth_failure, rate_limit
from app.sharing import service as shares
from app.sharing.service import ShareUnavailable

router = APIRouter(prefix="/api", tags=["shares"])

_DENIAL_EVENTS = {
    "not_found": audit.Event.SHARE_NOT_FOUND,
    "expired": audit.Event.SHARE_DENIED_EXPIRED,
    "revoked": audit.Event.SHARE_DENIED_REVOKED,
    "download_limit": audit.Event.SHARE_DENIED_LIMIT,
}


def _deny(request: Request, exc: ShareUnavailable) -> None:
    if exc.reason == "not_found":
        note_auth_failure(request)
    audit.record(_DENIAL_EVENTS[exc.reason], request=request, outcome="denied", reason=exc.reason)


@router.post("/shares", response_model=ShareCreated, status_code=201,
             dependencies=[Depends(rate_limit("share_create"))])
def create_share(
    request: Request,
    body: ShareCreate,
    token: str | None = Depends(session_token),
    db: Session = Depends(get_db),
    svc: Services = Depends(services),
) -> ShareCreated:
    try:
        artifact = sessions.authorize_artifact(db, body.artifact_id, token)
    except AppError as exc:
        if exc.status == 401:
            note_auth_failure(request)
            audit.record(audit.Event.AUTH_FAILED, request=request, outcome="denied", route="share_create")
        raise
    created = shares.create_share(db, artifact, body.expires_in, body.max_downloads)
    audit.record(
        audit.Event.SHARE_CREATED, request=request, artifact_id=artifact.id, share_id=created.share.id,
        expires_in=body.expires_in, max_downloads=body.max_downloads,
    )
    # The token lives in the URL fragment, which browsers never send to servers.
    url = f"{svc.settings.public_base_url.rstrip('/')}/s#{created.token}"
    return ShareCreated(
        id=created.share.id, url=url, token=created.token, manage_token=created.manage_token,
        expires_at=created.share.expires_at, max_downloads=created.share.max_downloads,
    )


@router.get("/shares/{token}", response_model=SharePublic, dependencies=[Depends(rate_limit("share_access"))])
def share_info(
    request: Request,
    token: str = Path(pattern=TOKEN_PATTERN),
    db: Session = Depends(get_db),
    svc: Services = Depends(services),
) -> SharePublic:
    """Metadata for the recipient page. Viewing does not consume a download."""
    try:
        share = shares.lookup(db, token)
        artifact = shares.get_artifact(db, share)
    except ShareUnavailable as exc:
        _deny(request, exc)
        raise
    name = svc.cipher.open_text(artifact.encrypted_name, purpose="name", object_id=artifact.id)
    audit.record(audit.Event.SHARE_ACCESSED, request=request, share_id=share.id)
    remaining = None if share.max_downloads is None else share.max_downloads - share.download_count
    return SharePublic(filename=name, mime=artifact.mime, size=artifact.size,
                       expires_at=share.expires_at, downloads_remaining=remaining)


@router.post("/shares/{token}/download", dependencies=[Depends(rate_limit("share_access"))])
def share_download(
    request: Request,
    token: str = Path(pattern=TOKEN_PATTERN),
    db: Session = Depends(get_db),
    svc: Services = Depends(services),
) -> Response:
    """POST, not GET: link-preview bots must not burn single-use downloads."""
    try:
        share = shares.consume(db, token)
        artifact = shares.get_artifact(db, share)
        data, name = sessions.read_artifact(svc, artifact)
        db.commit()  # only count the download once the bytes are in hand
    except ShareUnavailable as exc:
        db.rollback()
        _deny(request, exc)
        raise
    except Exception:
        db.rollback()
        raise
    audit.record(audit.Event.SHARE_DOWNLOADED, request=request, share_id=share.id,
                 artifact_id=artifact.id, download_count=share.download_count)
    return file_response(data, artifact.mime, name)


def _manage(request: Request, db: Session, share_id: str, manage_token: str | None):
    try:
        return shares.authorize_manage(db, share_id, manage_token)
    except AppError:
        note_auth_failure(request)
        audit.record(audit.Event.AUTH_FAILED, request=request, outcome="denied", share_id=share_id, route="share_manage")
        raise


@router.get("/shares/{share_id}/status", response_model=ShareStatus, dependencies=[Depends(rate_limit("share_manage"))])
def share_status(
    request: Request,
    share_id: str = Path(pattern=UUID_PATTERN),
    manage_token: str | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> ShareStatus:
    share = _manage(request, db, share_id, manage_token)
    return ShareStatus(id=share.id, expires_at=share.expires_at, max_downloads=share.max_downloads,
                       download_count=share.download_count, revoked=share.revoked_at is not None)


@router.delete("/shares/{share_id}", status_code=204, dependencies=[Depends(rate_limit("share_manage"))])
def revoke_share(
    request: Request,
    share_id: str = Path(pattern=UUID_PATTERN),
    manage_token: str | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Response:
    share = _manage(request, db, share_id, manage_token)
    shares.revoke(db, share)
    audit.record(audit.Event.SHARE_REVOKED, request=request, share_id=share.id)
    return Response(status_code=204)


@router.get("/admin/audit", tags=["admin"], dependencies=[Depends(rate_limit("share_manage"))])
def audit_log(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
    event_type: str | None = Query(None, max_length=48),
    admin: str | None = Depends(bearer),
    db: Session = Depends(get_db),
    svc: Services = Depends(services),
) -> list[dict]:
    expected = svc.settings.admin_token
    if not expected or not admin or not hmac.compare_digest(admin, expected):
        note_auth_failure(request)
        audit.record(audit.Event.AUTH_FAILED, request=request, outcome="denied", route="admin")
        raise unauthorized()
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if event_type:
        q = q.where(AuditEvent.event_type == event_type)
    return [
        {"id": e.id, "at": e.created_at.isoformat(), "event": e.event_type, "outcome": e.outcome, "actor": e.actor,
         "session_id": e.session_id, "artifact_id": e.artifact_id, "share_id": e.share_id, "details": e.details}
        for e in db.scalars(q)
    ]
