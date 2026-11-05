"""Retention enforcement: deletes expired sessions, originals and artifacts."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.orm import Artifact, ProcessingSession, utcnow
from app.services import audit
from app.services.context import Services

log = logging.getLogger("afterimage.cleanup")


def purge_expired(db: Session, svc: Services) -> dict[str, int]:
    now = utcnow()
    counts = {"sessions": 0, "artifacts": 0, "originals": 0}

    for s in db.scalars(select(ProcessingSession).where(ProcessingSession.expires_at <= now)).all():
        if s.original_key:
            svc.store.delete("originals", s.original_key)
            counts["originals"] += 1
        db.execute(update(Artifact).where(Artifact.session_id == s.id).values(session_id=None))
        db.delete(s)
        counts["sessions"] += 1

    for a in db.scalars(select(Artifact).where(Artifact.expires_at <= now)).all():
        svc.store.delete("artifacts", a.storage_key)
        db.delete(a)  # cascades to shares; wrapped key is gone => crypto-shredded
        counts["artifacts"] += 1
    db.commit()

    # Orphaned blobs (e.g. a crash between write and commit) older than a grace period.
    known_originals = set(db.scalars(select(ProcessingSession.original_key).where(ProcessingSession.original_key.is_not(None))))
    known_artifacts = set(db.scalars(select(Artifact.storage_key)))
    grace = (now - timedelta(minutes=10)).timestamp()
    for bucket, known in (("originals", known_originals), ("artifacts", known_artifacts)):
        for key in svc.store.keys(bucket):
            path = svc.store.root / bucket / f"{key}.bin"
            if key not in known and path.stat().st_mtime < grace:
                svc.store.delete(bucket, key)
    return counts


async def cleanup_loop(svc: Services) -> None:
    from app.db import session_factory

    while True:
        try:
            with session_factory()() as db:
                counts = await asyncio.to_thread(purge_expired, db, svc)
            if any(counts.values()):
                audit.record(audit.Event.CLEANUP_RUN, **counts)
                log.info("cleanup removed %s", counts)
        except Exception:
            log.exception("cleanup run failed")
        await asyncio.sleep(svc.settings.cleanup_interval_seconds)
