"""Expiring, revocable, download-limited capability links.

Every access decision is made server-side. The download counter is
incremented with a single conditional UPDATE, so the database — not
application code — arbitrates concurrent requests: with `max_downloads=1`,
exactly one of N simultaneous requests can succeed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.crypto.tokens import hash_token, looks_like_token, new_token, verify_token
from app.models.orm import Artifact, Share, new_id, utcnow
from app.schemas.api import EXPIRY_SECONDS
from app.services.errors import AppError, gone, not_found, unauthorized
from app.services.sessions import aware


@dataclass
class CreatedShare:
    share: Share
    token: str
    manage_token: str


class ShareUnavailable(AppError):
    def __init__(self, reason: str) -> None:
        messages = {
            "not_found": (404, "This link is not valid."),
            "expired": (410, "This link has expired."),
            "revoked": (410, "This link was revoked by its owner."),
            "download_limit": (410, "This link has reached its download limit."),
        }
        status, message = messages[reason]
        super().__init__(status, f"share_{reason}", message)
        self.reason = reason


def create_share(db: Session, artifact: Artifact, expires_in: str, max_downloads: int | None) -> CreatedShare:
    token, manage = new_token(), new_token()
    now = utcnow()
    expires_at = now + timedelta(seconds=EXPIRY_SECONDS[expires_in])
    share = Share(
        id=new_id(), artifact_id=artifact.id, token_hash=hash_token(token), manage_token_hash=hash_token(manage),
        created_at=now, expires_at=expires_at, max_downloads=max_downloads,
    )
    # Keep the encrypted artifact exactly as long as its longest-lived link.
    if aware(artifact.expires_at) < expires_at:
        artifact.expires_at = expires_at
    db.add(share)
    db.commit()
    return CreatedShare(share, token, manage)


def _why_unavailable(share: Share | None, now: datetime) -> str:
    if share is None:
        return "not_found"
    if share.revoked_at is not None:
        return "revoked"
    if aware(share.expires_at) <= now:
        return "expired"
    if share.max_downloads is not None and share.download_count >= share.max_downloads:
        return "download_limit"
    return "ok"


def lookup(db: Session, token: str) -> Share:
    """Read-only check used by the recipient landing page. Does not consume a download."""
    if not looks_like_token(token):
        raise ShareUnavailable("not_found")
    share = db.scalar(select(Share).where(Share.token_hash == hash_token(token)))
    reason = _why_unavailable(share, utcnow())
    if reason != "ok":
        raise ShareUnavailable(reason)
    return share  # type: ignore[return-value]


def consume(db: Session, token: str) -> Share:
    """Atomically claim one download. Caller must commit after the bytes are read."""
    if not looks_like_token(token):
        raise ShareUnavailable("not_found")
    now = utcnow()
    stmt = (
        update(Share)
        .where(
            Share.token_hash == hash_token(token),
            Share.revoked_at.is_(None),
            Share.expires_at > now,
            or_(Share.max_downloads.is_(None), Share.download_count < Share.max_downloads),
        )
        .values(download_count=Share.download_count + 1, last_accessed_at=now)
        .returning(Share.id)
        .execution_options(synchronize_session=False)
    )
    share_id = db.execute(stmt).scalar_one_or_none()
    if share_id is None:
        db.rollback()
        share = db.scalar(select(Share).where(Share.token_hash == hash_token(token)))
        raise ShareUnavailable(_why_unavailable(share, now) if share else "not_found")
    share = db.get(Share, share_id, populate_existing=True)
    assert share is not None
    return share


def authorize_manage(db: Session, share_id: str, manage_token: str | None) -> Share:
    share = db.get(Share, share_id)
    if share is None or not verify_token(manage_token, share.manage_token_hash):
        raise unauthorized("Missing or invalid share management token.")
    return share


def revoke(db: Session, share: Share) -> None:
    if share.revoked_at is None:
        share.revoked_at = utcnow()
        db.commit()


def get_artifact(db: Session, share: Share) -> Artifact:
    artifact = db.get(Artifact, share.artifact_id)
    if artifact is None:
        raise not_found()
    if aware(artifact.expires_at) <= utcnow():
        raise gone("share_expired", "This link has expired.")
    return artifact
