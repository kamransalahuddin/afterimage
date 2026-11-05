from __future__ import annotations

import io

import pymupdf
from fastapi import APIRouter, Depends, File, Path, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import UUID_PATTERN, services, session_token
from app.api.responses import file_response, png_response
from app.db import get_db
from app.detection.pipeline import render_page
from app.schemas.api import AnalyzeResponse, RedactRequest, RedactResponse
from app.services import audit, sessions
from app.services.context import Services
from app.services.errors import AppError
from app.services.ratelimit import note_auth_failure, rate_limit
from app.services.validation import validate_upload

router = APIRouter(prefix="/api", tags=["files"])


def _read_limited(upload: UploadFile, limit: int) -> bytes:
    chunks, total = [], 0
    while chunk := upload.file.read(1024 * 1024):
        total += len(chunk)
        if total > limit:
            raise AppError(413, "file_too_large", f"Files must be {limit // (1024 * 1024)} MB or smaller.")
        chunks.append(chunk)
    return b"".join(chunks)


def _auth_session(request: Request, db: Session, session_id: str, token: str | None):
    try:
        return sessions.authorize_session(db, session_id, token)
    except AppError as exc:
        if exc.status == 401:
            note_auth_failure(request)
            audit.record(audit.Event.AUTH_FAILED, request=request, outcome="denied", session_id=session_id, route="session")
        raise


@router.post("/files/analyze", response_model=AnalyzeResponse, status_code=201,
             dependencies=[Depends(rate_limit("analyze"))])
def analyze_file(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    svc: Services = Depends(services),
) -> AnalyzeResponse:
    try:
        data = _read_limited(file, svc.settings.max_upload_bytes)
        vf = validate_upload(data, file.filename, svc.settings)
    except AppError as exc:
        audit.record(audit.Event.FILE_REJECTED, request=request, outcome="rejected", reason=exc.code)
        raise
    result = sessions.analyze_upload(db, svc, vf)
    counts: dict[str, int] = {}
    for d in result.detections:
        counts[d.category] = counts.get(d.category, 0) + 1
    audit.record(
        audit.Event.FILE_ANALYZED, request=request, session_id=result.session_id,
        kind=vf.kind, mime=vf.mime, size=len(vf.data), pages=len(result.pages),
        detections=len(result.detections), categories=counts,
    )
    return result


@router.get("/files/{session_id}/pages/{page}/preview", dependencies=[Depends(rate_limit("preview"))])
def preview_page(
    request: Request,
    session_id: str = Path(pattern=UUID_PATTERN),
    page: int = Path(ge=0, le=500),
    token: str | None = Depends(session_token),
    db: Session = Depends(get_db),
    svc: Services = Depends(services),
) -> Response:
    session = _auth_session(request, db, session_id, token)
    return png_response(sessions.render_preview(svc, session, page))


@router.post("/files/redact", response_model=RedactResponse, status_code=201,
             dependencies=[Depends(rate_limit("redact"))])
def redact_file(
    request: Request,
    body: RedactRequest,
    token: str | None = Depends(session_token),
    db: Session = Depends(get_db),
    svc: Services = Depends(services),
) -> RedactResponse:
    session = _auth_session(request, db, body.session_id, token)
    try:
        result = sessions.redact_session(db, svc, session, body, token or "")
    except AppError as exc:
        audit.record(audit.Event.REDACTION_FAILED, request=request, outcome="error", session_id=session.id, reason=exc.code)
        raise
    audit.record(
        audit.Event.REDACTION_COMPLETED, request=request, session_id=session.id, artifact_id=result.artifact_id,
        selected=len(body.detection_ids), manual=len(body.manual_regions), rasterized=body.rasterize,
        verification=result.verification, metadata_removed=len(result.metadata_removed),
    )
    return result


def _auth_artifact(request: Request, db: Session, artifact_id: str, token: str | None):
    try:
        return sessions.authorize_artifact(db, artifact_id, token)
    except AppError as exc:
        if exc.status == 401:
            note_auth_failure(request)
            audit.record(audit.Event.AUTH_FAILED, request=request, outcome="denied", artifact_id=artifact_id, route="artifact")
        raise


@router.get("/artifacts/{artifact_id}/download", dependencies=[Depends(rate_limit("preview"))])
def download_artifact(
    request: Request,
    artifact_id: str = Path(pattern=UUID_PATTERN),
    token: str | None = Depends(session_token),
    db: Session = Depends(get_db),
    svc: Services = Depends(services),
) -> Response:
    artifact = _auth_artifact(request, db, artifact_id, token)
    data, name = sessions.read_artifact(svc, artifact)
    audit.record(audit.Event.ARTIFACT_DOWNLOADED, request=request, artifact_id=artifact.id)
    return file_response(data, artifact.mime, name)


@router.get("/artifacts/{artifact_id}/pages/{page}/preview", dependencies=[Depends(rate_limit("preview"))])
def preview_artifact(
    request: Request,
    artifact_id: str = Path(pattern=UUID_PATTERN),
    page: int = Path(ge=0, le=500),
    token: str | None = Depends(session_token),
    db: Session = Depends(get_db),
    svc: Services = Depends(services),
) -> Response:
    artifact = _auth_artifact(request, db, artifact_id, token)
    data, _ = sessions.read_artifact(svc, artifact)
    if artifact.mime != "application/pdf":
        if page != 0:
            raise AppError(404, "not_found", "Page not found.")
        return Response(content=data, media_type=artifact.mime, headers={"Cache-Control": "no-store, private"})
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        if page >= doc.page_count:
            raise AppError(404, "not_found", "Page not found.")
        p = doc[page]
        img = render_page(p, min(2.0, sessions.PREVIEW_MAX_SIDE / max(p.rect.width, p.rect.height)))
    finally:
        doc.close()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return png_response(buf.getvalue())
