"""Processing sessions: analyze -> preview -> redact."""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime, timedelta

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto.tokens import hash_token, new_token, verify_token
from app.detection.pipeline import analyze, load_image, render_page
from app.models.orm import Artifact, Detection, ProcessingSession, new_id, utcnow
from app.redaction.engine import Region, redact_image, redact_pdf
from app.schemas.api import (
    AnalyzeResponse,
    BoxOut,
    DetectionOut,
    MetadataOut,
    PageOut,
    RedactRequest,
    RedactResponse,
)
from app.services.context import Services
from app.services.errors import AppError, not_found, unauthorized
from app.services.validation import ValidatedFile

SUGGEST_THRESHOLD = 0.6
PREVIEW_MAX_SIDE = 2400


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _busy() -> AppError:
    return AppError(503, "busy", "The server is busy processing other files. Try again shortly.")


def analyze_upload(db: Session, svc: Services, vf: ValidatedFile) -> AnalyzeResponse:
    if not svc.jobs.acquire(timeout=20):
        raise _busy()
    try:
        result = analyze(
            vf.data, vf.kind,
            ocr_timeout=svc.settings.ocr_timeout_seconds,
            use_entities=svc.settings.enable_presidio,
        )
    finally:
        svc.jobs.release()

    sid = new_id()
    token = new_token()
    key = svc.store.new_key()
    sealed = svc.cipher.seal(vf.data, purpose="original", object_id=sid)
    svc.store.write("originals", key, sealed.blob)

    now = utcnow()
    session = ProcessingSession(
        id=sid,
        token_hash=hash_token(token),
        kind=vf.kind,
        mime=vf.mime,
        page_count=len(result.pages),
        pages=[{"width": p.width, "height": p.height} for p in result.pages],
        encrypted_name=svc.cipher.seal_text(vf.display_name, purpose="name", object_id=sid),
        original_key=key,
        original_wrapped_key=sealed.wrapped_key,
        metadata_findings=[{"key": m.key, "label": m.label} for m in result.metadata],
        created_at=now,
        expires_at=now + timedelta(minutes=svc.settings.session_ttl_minutes),
    )
    for i, f in enumerate(result.findings):
        session.detections.append(Detection(
            id=new_id(), ordinal=i, category=f.category, label=f.label, source=f.source,
            page=f.page, confidence=f.confidence, masked_preview=f.masked[:64],
            boxes=[[round(b.x0, 5), round(b.y0, 5), round(b.x1, 5), round(b.y1, 5)] for b in f.boxes],
        ))
    try:
        db.add(session)
        db.commit()
    except Exception:
        db.rollback()
        svc.store.delete("originals", key)
        raise

    return AnalyzeResponse(
        session_id=sid,
        session_token=token,
        expires_at=session.expires_at,
        filename=vf.display_name,
        kind=vf.kind,
        mime=vf.mime,
        pages=[PageOut(width=p.width, height=p.height) for p in result.pages],
        detections=[_detection_out(d) for d in session.detections],
        metadata=[MetadataOut(key=m.key, label=m.label, value=m.value) for m in result.metadata],
        notes=result.notes,
    )


def _detection_out(d: Detection) -> DetectionOut:
    return DetectionOut(
        id=d.id, category=d.category, label=d.label, page=d.page,
        boxes=[BoxOut(x=b[0], y=b[1], w=b[2] - b[0], h=b[3] - b[1]) for b in d.boxes],
        confidence=d.confidence, preview=d.masked_preview, source=d.source,
        suggested=d.confidence >= SUGGEST_THRESHOLD,
    )


def authorize_session(db: Session, session_id: str, token: str | None) -> ProcessingSession:
    session = db.get(ProcessingSession, session_id)
    # Same response for unknown and wrong-token, to avoid an enumeration oracle.
    if session is None or not verify_token(token, session.token_hash):
        raise unauthorized("This session does not exist or the session token is invalid.")
    if aware(session.expires_at) <= utcnow():
        raise AppError(410, "session_expired", "This editing session has expired. Upload the file again.")
    return session


def _load_original(svc: Services, session: ProcessingSession) -> bytes:
    if not session.original_key or not session.original_wrapped_key:
        raise AppError(409, "original_deleted", "The original was deleted after redaction. Upload it again to make changes.")
    blob = svc.store.read("originals", session.original_key)
    return svc.cipher.open(blob, session.original_wrapped_key, purpose="original", object_id=session.id)


def render_preview(svc: Services, session: ProcessingSession, page: int) -> bytes:
    if not 0 <= page < session.page_count:
        raise not_found("Page not found.")
    data = _load_original(svc, session)
    if session.kind == "pdf":
        doc = pymupdf.open(stream=data, filetype="pdf")
        try:
            p = doc[page]
            zoom = min(2.0, PREVIEW_MAX_SIDE / max(p.rect.width, p.rect.height))
            img = render_page(p, zoom)
        finally:
            doc.close()
    else:
        img = load_image(data)
        img.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def redact_session(db: Session, svc: Services, session: ProcessingSession, req: RedactRequest,
                   token: str) -> RedactResponse:
    detections = {d.id: d for d in session.detections}
    unknown = [i for i in req.detection_ids if i not in detections]
    if unknown:
        raise AppError(422, "unknown_detection", "One or more detections do not belong to this session.")

    regions: list[Region] = []
    for did in dict.fromkeys(req.detection_ids):
        d = detections[did]
        regions += [Region(d.page, *b) for b in d.boxes]
    for m in req.manual_regions:
        if m.page >= session.page_count:
            raise AppError(422, "invalid_region", "A manual region refers to a page that does not exist.")
        regions.append(Region(m.page, m.x, m.y, min(1.0, m.x + m.w), min(1.0, m.y + m.h)))

    data = _load_original(svc, session)
    if not svc.jobs.acquire(timeout=20):
        raise _busy()
    try:
        if session.kind == "pdf":
            output = redact_pdf(data, regions, rasterize=req.rasterize)
        else:
            output = redact_image(data, session.mime, regions)
    finally:
        svc.jobs.release()
        del data

    name = svc.cipher.open_text(session.encrypted_name, purpose="name", object_id=session.id)
    stem, _, ext = name.rpartition(".")
    out_name = f"{stem or 'file'}-redacted.{ext or 'bin'}"

    aid = new_id()
    key = svc.store.new_key()
    sealed = svc.cipher.seal(output.data, purpose="artifact", object_id=aid)
    svc.store.write("artifacts", key, sealed.blob)

    now = utcnow()
    artifact = Artifact(
        id=aid, session_id=session.id, storage_key=key, wrapped_key=sealed.wrapped_key, key_id=sealed.key_id,
        mime=output.mime, size=len(output.data), sha256=hashlib.sha256(output.data).hexdigest(),
        encrypted_name=svc.cipher.seal_text(out_name, purpose="name", object_id=aid),
        owner_token_hash=hash_token(token), created_at=now,
        expires_at=now + timedelta(minutes=svc.settings.unshared_artifact_ttl_minutes),
    )
    # Processing is complete: the original is destroyed (file + wrapped key).
    original_key = session.original_key
    session.original_key = None
    session.original_wrapped_key = None
    session.status = "redacted"
    db.add(artifact)
    db.commit()
    svc.store.delete("originals", original_key)

    return RedactResponse(
        artifact_id=aid, filename=out_name, mime=output.mime, size=artifact.size, sha256=artifact.sha256,
        expires_at=artifact.expires_at, regions=output.report.get("regions", 0),
        metadata_removed=[m["label"] for m in session.metadata_findings],
        verification=output.report.get("verification", {}) | {"rasterized": output.report.get("rasterized", False)},
    )


def authorize_artifact(db: Session, artifact_id: str, token: str | None) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if artifact is None or not verify_token(token, artifact.owner_token_hash):
        raise unauthorized("This file does not exist or you do not have access to it.")
    if aware(artifact.expires_at) <= utcnow():
        raise AppError(410, "artifact_expired", "This file has expired and was deleted.")
    return artifact


def read_artifact(svc: Services, artifact: Artifact) -> tuple[bytes, str]:
    blob = svc.store.read("artifacts", artifact.storage_key)
    data = svc.cipher.open(blob, artifact.wrapped_key, purpose="artifact", object_id=artifact.id)
    if hashlib.sha256(data).hexdigest() != artifact.sha256:
        raise AppError(500, "integrity_error", "Stored file failed its integrity check.")
    name = svc.cipher.open_text(artifact.encrypted_name, purpose="name", object_id=artifact.id)
    return data, name


def artifacts_for_session(db: Session, session_id: str) -> list[Artifact]:
    return list(db.scalars(select(Artifact).where(Artifact.session_id == session_id)))
