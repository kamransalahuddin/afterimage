from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import files, shares
from app.config import Settings, get_settings, set_settings
from app.db import get_engine, init_engine
from app.detection import entities, faces, ocr
from app.models.orm import Base
from app.services import audit
from app.services.cleanup import cleanup_loop
from app.services.context import Services
from app.services.errors import AppError

# ------------------------------------------------------------------ logging hygiene

_TOKENISH = re.compile(r"[A-Za-z0-9_-]{40,}")


def scrub(text: str) -> str:
    """Remove anything shaped like a capability token from log output."""
    return _TOKENISH.sub("[redacted]", text)


class ScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        record.msg, record.args = scrub(message), None
        return True


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, ScrubFilter) for f in handler.filters):
            handler.addFilter(ScrubFilter())
    # Uvicorn's access log prints raw paths; we emit our own scrubbed access log.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)


access_log = logging.getLogger("afterimage.access")


# ------------------------------------------------------------------ app factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    set_settings(settings)
    configure_logging()
    settings.audit_secret_bytes()  # fail fast if unset
    init_engine(settings.database_url)
    Base.metadata.create_all(get_engine())
    svc = Services.from_settings(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(cleanup_loop(svc)) if settings.cleanup_interval_seconds > 0 else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    is_prod = settings.env == "production"
    app = FastAPI(
        title="AFTERIMAGE API", version="1.0.0", lifespan=lifespan,
        docs_url=None if is_prod else "/api/docs", redoc_url=None, openapi_url=None if is_prod else "/api/openapi.json",
    )
    app.state.services = svc

    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Session-Token"], expose_headers=["Content-Disposition"],
        allow_credentials=False, max_age=600,
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        start = time.perf_counter()
        # Reject oversized bodies before reading them.
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_upload_bytes + 64 * 1024:
            response = _error(413, "file_too_large", "Request body is too large.")
        else:
            response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        response.headers.setdefault("Cache-Control", "no-store")
        if is_prod:
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        access_log.info("%s %s %s %.0fms", request.method, scrub(request.url.path), response.status_code,
                        (time.perf_counter() - start) * 1000)
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        audit.record(audit.Event.REQUEST_REJECTED, request=request, outcome="rejected", reason="validation")
        fields = [".".join(str(p) for p in e.get("loc", [])[1:]) for e in exc.errors()][:5]
        return _error(422, "invalid_request", "The request was malformed.", fields=fields)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, "Not found." if exc.status_code == 404 else str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logging.getLogger("afterimage").exception("unhandled error on %s", scrub(request.url.path))
        return _error(500, "internal_error", "Something went wrong. No file was shared.")

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {
            "status": "ok",
            "capabilities": {
                "ocr": ocr.tesseract_version() is not None,
                "faces": faces.backend_name(),
                "names": settings.enable_presidio and entities.available(),
                "formats": ["image/png", "image/jpeg", "image/webp", "application/pdf"],
                "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
            },
        }

    app.include_router(files.router)
    app.include_router(shares.router)
    return app


def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


def app_factory() -> FastAPI:  # used by `uvicorn --factory`
    return create_app()
