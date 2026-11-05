"""Permanent redaction.

Images: selected pixels are overwritten with a solid colour on a decoded
bitmap, then the bitmap is copied into a brand-new image object (no info
dict, EXIF, XMP, ICC or text chunks) and re-encoded. The original encoded
bytes are never reused.

PDFs: real redaction annotations are applied with PyMuPDF, which deletes the
text, the overlapping image pixels, and vector graphics contained in each
area from the content streams. The document is then scrubbed (metadata, XMP,
JavaScript, embedded files, links, form fields, hidden text, thumbnails),
all annotations are removed, and the file is rewritten from scratch with
garbage collection so no prior revision survives. Optionally every page is
flattened to an image for the strongest guarantee.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pymupdf
from PIL import Image, ImageCms, ImageDraw

from app.detection.pipeline import load_image
from app.services.errors import AppError

FILL_RGB = (0, 0, 0)
IMAGE_PAD_PX = 2
PDF_PAD_PT = 0.75
RASTER_ZOOM = 200 / 72


@dataclass(frozen=True)
class Region:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    def clamp(self) -> Region:
        x0, x1 = sorted((min(max(self.x0, 0.0), 1.0), min(max(self.x1, 0.0), 1.0)))
        y0, y1 = sorted((min(max(self.y0, 0.0), 1.0), min(max(self.y1, 0.0), 1.0)))
        return Region(self.page, x0, y0, x1, y1)


@dataclass
class RedactionOutput:
    data: bytes
    mime: str
    report: dict = field(default_factory=dict)


class RedactionVerificationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(500, "verification_failed", message)


# ------------------------------------------------------------------ images

_ENCODERS = {
    "image/png": ("PNG", {"optimize": False}),
    "image/jpeg": ("JPEG", {"quality": 92, "optimize": True}),
    "image/webp": ("WEBP", {"quality": 92, "method": 4}),
}


def _to_srgb(img: Image.Image) -> Image.Image:
    icc = img.info.get("icc_profile")
    if not icc:
        return img
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        dst = ImageCms.createProfile("sRGB")
        mode = "RGBA" if img.mode == "RGBA" else "RGB"
        return ImageCms.profileToProfile(img.convert(mode), src, dst, outputMode=mode)
    except Exception:
        return img


def redact_image(data: bytes, mime: str, regions: list[Region]) -> RedactionOutput:
    img = _to_srgb(load_image(data))
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    mode = "RGBA" if has_alpha and mime != "image/jpeg" else "RGB"
    img = img.convert(mode)
    w, h = img.size

    draw = ImageDraw.Draw(img)
    fill = FILL_RGB + ((255,) if mode == "RGBA" else ())
    pixel_boxes = []
    for r in (r.clamp() for r in regions if r.page == 0):
        box = (
            max(0, int(r.x0 * w) - IMAGE_PAD_PX), max(0, int(r.y0 * h) - IMAGE_PAD_PX),
            min(w - 1, int(r.x1 * w + 0.999) + IMAGE_PAD_PX), min(h - 1, int(r.y1 * h + 0.999) + IMAGE_PAD_PX),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        draw.rectangle(box, fill=fill)
        pixel_boxes.append(box)

    # Copy raw pixels into a fresh image so no ancillary data can carry over.
    clean = Image.frombytes(mode, img.size, img.tobytes())
    fmt, opts = _ENCODERS[mime]
    buf = io.BytesIO()
    clean.save(buf, format=fmt, **opts)
    out = buf.getvalue()

    verification = _verify_image(out, fmt, pixel_boxes, lossy=mime != "image/png")
    return RedactionOutput(out, mime, {"regions": len(pixel_boxes), "verification": verification})


def _verify_image(data: bytes, fmt: str, boxes: list[tuple[int, int, int, int]], lossy: bool) -> dict:
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        if img.format != fmt:
            raise RedactionVerificationError("Encoded output has an unexpected format.")
        leftovers = [k for k in ("exif", "xmp", "XML:com.adobe.xmp", "icc_profile", "comment") if img.info.get(k)]
        if len(img.getexif()) or leftovers or getattr(img, "text", None):
            raise RedactionVerificationError("Metadata survived re-encoding.")
        rgb = img.convert("RGB")
        tolerance = 24 if lossy else 0
        for x0, y0, x1, y1 in boxes:
            # Lossy codecs blur the edges; check the interior.
            inset = 3 if lossy else 0
            crop = rgb.crop((x0 + inset, y0 + inset, max(x0 + inset + 1, x1 - inset), max(y0 + inset + 1, y1 - inset)))
            lo, hi = zip(*crop.getextrema())
            if max(hi) > max(FILL_RGB) + tolerance:
                raise RedactionVerificationError("A redacted area was not fully overwritten.")
    return {"metadata_stripped": True, "regions_verified": len(boxes)}


# ------------------------------------------------------------------ PDFs


def _display_to_page_rect(page: pymupdf.Page, r: Region) -> pymupdf.Rect:
    pw, ph = page.rect.width, page.rect.height
    disp = pymupdf.Rect(r.x0 * pw - PDF_PAD_PT, r.y0 * ph - PDF_PAD_PT, r.x1 * pw + PDF_PAD_PT, r.y1 * ph + PDF_PAD_PT)
    return (disp * page.derotation_matrix).normalize()


def _norm(s: str) -> str:
    return "".join(s.split())


def redact_pdf(data: bytes, regions: list[Region], *, rasterize: bool = False) -> RedactionOutput:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        by_page: dict[int, list[Region]] = {}
        for r in regions:
            if 0 <= r.page < doc.page_count:
                by_page.setdefault(r.page, []).append(r.clamp())

        # Capture (in memory only) what text sits under each area so we can
        # prove it no longer extracts afterwards. Never persisted or logged.
        removed_snippets: set[str] = set()
        applied = 0
        for page_no, page in enumerate(doc):
            for annot in list(page.annots() or []):
                page.delete_annot(annot)
            for widget in list(page.widgets() or []):
                page.delete_widget(widget)
            for r in by_page.get(page_no, []):
                rect = _display_to_page_rect(page, r)
                snippet = _norm(page.get_text("text", clip=rect))
                if len(snippet) >= 4:
                    removed_snippets.add(snippet)
                page.add_redact_annot(rect, fill=FILL_RGB)
                applied += 1
            page.apply_redactions(
                images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                text=pymupdf.PDF_REDACT_TEXT_REMOVE,
            )

        doc.scrub(
            attached_files=True, clean_pages=True, embedded_files=True, hidden_text=True,
            javascript=True, metadata=True, redactions=True, remove_links=True,
            reset_fields=True, reset_responses=True, thumbnails=True, xml_metadata=True,
        )
        doc.set_metadata({})
        doc.del_xml_metadata()
        out = doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()

    if rasterize:
        out = _rasterize_pdf(out)

    verification = _verify_pdf(out, by_page, removed_snippets)
    return RedactionOutput(out, "application/pdf", {
        "regions": applied, "rasterized": rasterize, "verification": verification,
    })


def _rasterize_pdf(data: bytes) -> bytes:
    src = pymupdf.open(stream=data, filetype="pdf")
    dst = pymupdf.open()
    try:
        for page in src:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(RASTER_ZOOM, RASTER_ZOOM), alpha=False)
            new = dst.new_page(width=page.rect.width, height=page.rect.height)
            new.insert_image(new.rect, stream=pix.tobytes("jpeg", jpg_quality=90))
        dst.set_metadata({})
        return dst.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        src.close()
        dst.close()


def _verify_pdf(data: bytes, by_page: dict[int, list[Region]], removed: set[str]) -> dict:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise RedactionVerificationError("Redacted PDF could not be re-opened.") from exc
    try:
        if doc.is_encrypted or doc.page_count < 1:
            raise RedactionVerificationError("Redacted PDF is not a valid document.")
        for page_no, regions in by_page.items():
            page = doc[page_no]
            for r in regions:
                inner = _display_to_page_rect(page, r)
                inner = pymupdf.Rect(inner.x0 + 2 * PDF_PAD_PT, inner.y0 + 2 * PDF_PAD_PT,
                                     inner.x1 - 2 * PDF_PAD_PT, inner.y1 - 2 * PDF_PAD_PT)
                if not inner.is_empty and _norm(page.get_text("text", clip=inner)):
                    raise RedactionVerificationError("Text is still extractable inside a redacted area.")
            if list(page.annots() or []):
                raise RedactionVerificationError("Annotations survived redaction.")
        meta = doc.metadata or {}
        if doc.get_xml_metadata() or any(
            meta.get(k) for k in ("author", "creator", "producer", "title", "subject", "keywords", "creationDate", "modDate")
        ):
            raise RedactionVerificationError("Document metadata survived redaction.")
        full_text = _norm("".join(p.get_text("text") for p in doc))
        residual = sum(1 for s in removed if s in full_text)
    finally:
        doc.close()
    return {"text_in_redacted_areas": 0, "metadata_stripped": True, "residual_matches": residual}
