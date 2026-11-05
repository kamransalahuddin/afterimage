"""Upload validation.

The declared filename and Content-Type are never trusted. A file is accepted
only if its leading bytes match a supported signature AND a real decoder can
fully parse it within conservative resource limits.
"""

from __future__ import annotations

import io
import re
import unicodedata
import warnings
from dataclasses import dataclass

import pymupdf
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.services.errors import AppError

SUPPORTED = {
    "image/png": (".png", "image"),
    "image/jpeg": (".jpg", "image"),
    "image/webp": (".webp", "image"),
    "application/pdf": (".pdf", "pdf"),
}


@dataclass(frozen=True)
class ValidatedFile:
    data: bytes
    mime: str
    kind: str  # image | pdf
    extension: str
    display_name: str


def sniff_mime(head: bytes) -> str | None:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    # PDF header may legally be preceded by a little junk; we require it up front.
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


_UNSAFE_NAME = re.compile(r"[^\w.\- ()]+")


def safe_display_name(name: str | None, extension: str) -> str:
    """A filename safe for Content-Disposition. Only ever used for display."""
    base = unicodedata.normalize("NFKC", (name or "file").replace("\\", "/").split("/")[-1])
    base = base.rsplit(".", 1)[0] if "." in base else base
    base = _UNSAFE_NAME.sub("", base).strip(" .")[:80] or "file"
    return f"{base}{extension}"


def _reject(code: str, message: str) -> AppError:
    return AppError(415 if code == "unsupported_type" else 400, code, message)


def validate_upload(data: bytes, filename: str | None, settings: Settings) -> ValidatedFile:
    if not data:
        raise _reject("empty_file", "The file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise AppError(413, "file_too_large", f"Files must be {settings.max_upload_bytes // (1024 * 1024)} MB or smaller.")

    mime = sniff_mime(data[:16])
    if mime is None:
        raise _reject("unsupported_type", "Unsupported file. Use PNG, JPG, WEBP or PDF.")
    extension, kind = SUPPORTED[mime]

    if kind == "image":
        _validate_image(data, mime, settings)
    else:
        _validate_pdf(data, settings)

    return ValidatedFile(
        data=data, mime=mime, kind=kind, extension=extension,
        display_name=safe_display_name(filename, extension),
    )


def _validate_image(data: bytes, mime: str, settings: Settings) -> None:
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
    expected = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}[mime]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                if probe.format != expected:
                    raise _reject("mismatched_type", "File contents do not match a supported image format.")
                w, h = probe.size
                if w < 1 or h < 1 or max(w, h) > settings.max_image_side:
                    raise _reject("image_dimensions", "Image dimensions are outside the supported range.")
                if getattr(probe, "n_frames", 1) > 1:
                    raise _reject("animated_image", "Animated images are not supported.")
                probe.verify()
            with Image.open(io.BytesIO(data)) as full:
                full.load()  # verify() does not decode pixel data; load() does.
    except AppError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise _reject("image_too_large", "Image has too many pixels to process safely.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise _reject("malformed_file", "The image appears to be corrupted.") from None


def _validate_pdf(data: bytes, settings: Settings) -> None:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise _reject("malformed_file", "The PDF appears to be corrupted.") from None
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise _reject("encrypted_pdf", "Password-protected PDFs are not supported.")
        if doc.page_count < 1:
            raise _reject("malformed_file", "The PDF has no pages.")
        if doc.page_count > settings.max_pdf_pages:
            raise _reject("too_many_pages", f"PDFs are limited to {settings.max_pdf_pages} pages.")
        for page in doc:
            r = page.rect
            if r.width <= 0 or r.height <= 0 or max(r.width, r.height) > 14_400:
                raise _reject("page_dimensions", "A PDF page has unsupported dimensions.")
    except AppError:
        raise
    except Exception:
        raise _reject("malformed_file", "The PDF appears to be corrupted.") from None
    finally:
        doc.close()
