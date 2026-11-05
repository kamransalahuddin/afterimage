"""Detection pipeline: file bytes -> positioned potential exposures.

Coordinates are normalised to [0, 1] in *display* space (EXIF orientation
applied for images; page rotation applied for PDFs) so the browser can draw
overlays without knowing anything about the source format.
"""

from __future__ import annotations

import io
import logging

import pymupdf
from PIL import Image, ImageOps

from app.detection import faces, metadata, ocr
from app.detection.scanner import scan_text
from app.detection.textlayer import TextLayer
from app.detection.types import FACE, AnalysisResult, Box, Finding, PageInfo, Word

log = logging.getLogger("afterimage.detection")

PDF_OCR_ZOOM = 2.5  # ~180 DPI
PDF_FACE_ZOOM = 1.5


def load_image(data: bytes) -> Image.Image:
    """Decode and normalise orientation. The caller owns the returned image."""
    with Image.open(io.BytesIO(data)) as raw:
        raw.load()
        img = ImageOps.exif_transpose(raw) or raw.copy()
    return img


def _normalise(box: Box, width: float, height: float) -> Box:
    return Box(
        max(0.0, box.x0 / width), max(0.0, box.y0 / height),
        min(1.0, box.x1 / width), min(1.0, box.y1 / height),
    )


def _text_findings(words: list[Word], page: int, width: float, height: float, source: str,
                   use_entities: bool) -> list[Finding]:
    layer = TextLayer(words)
    out: list[Finding] = []
    for m in scan_text(layer.text, use_entities=use_entities):
        boxes = [_normalise(b, width, height) for b in layer.boxes_for(m.start, m.end)]
        boxes = [b for b in boxes if b.area() > 0]
        if not boxes:
            continue
        conf = m.confidence
        if source == "ocr" and layer.min_confidence(m.start, m.end) < 60:
            conf *= 0.85  # shaky OCR => less certain
        out.append(Finding(m.category, m.label, page, boxes, round(conf, 2), m.masked, source))
    return out


def _face_findings(img: Image.Image, page: int, sx: float, sy: float) -> list[Finding]:
    out = []
    for box, score in faces.detect_faces(img):
        out.append(Finding(FACE, "Face", page, [_normalise(box, sx, sy)], score, "Face", "face"))
    return out


def analyze_image(data: bytes, *, ocr_timeout: int = 30, use_entities: bool = True) -> AnalysisResult:
    with Image.open(io.BytesIO(data)) as original:
        original.load()
        meta = metadata.inspect_image(original)
    img = load_image(data)
    w, h = img.size
    result = AnalysisResult(pages=[PageInfo(w, h)], metadata=meta, ocr_pages=[0])
    try:
        words = ocr.ocr_words(img, timeout=ocr_timeout, page=0)
        result.findings += _text_findings(words, 0, w, h, "ocr", use_entities)
    except ocr.OCRUnavailable as exc:
        result.notes.append(f"Text recognition unavailable: {exc}")
    result.findings += _face_findings(img, 0, w, h)
    return result


def _page_words(page: pymupdf.Page, page_no: int) -> list[Word]:
    mat = page.rotation_matrix
    words = []
    for x0, y0, x1, y1, text, block, line, _ in page.get_text("words", sort=True):
        r = pymupdf.Rect(x0, y0, x1, y1) * mat
        words.append(Word(text, Box(r.x0, r.y0, r.x1, r.y1), (page_no, block, line)))
    return words


def _image_coverage(page: pymupdf.Page) -> float:
    area = page.rect.width * page.rect.height or 1
    covered = 0.0
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & page.rect
        covered += r.width * r.height if not r.is_empty else 0
    return min(1.0, covered / area)


def render_page(page: pymupdf.Page, zoom: float) -> Image.Image:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def analyze_pdf(data: bytes, *, ocr_timeout: int = 30, use_entities: bool = True) -> AnalysisResult:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        result = AnalysisResult(pages=[PageInfo(p.rect.width, p.rect.height) for p in doc])
        result.metadata = metadata.inspect_pdf(doc)
        for page_no, page in enumerate(doc):
            pw, ph = page.rect.width, page.rect.height
            words = _page_words(page, page_no)
            coverage = _image_coverage(page)

            # Scanned pages or pages with significant imagery get OCR'd; OCR words
            # that overlap native text are dropped to avoid double counting.
            if len(words) < 3 or coverage > 0.15:
                raster = render_page(page, PDF_OCR_ZOOM)
                try:
                    ocr_raw = ocr.ocr_words(raster, timeout=ocr_timeout, page=page_no)
                    scaled = [
                        Word(w.text, Box(w.box.x0 / PDF_OCR_ZOOM, w.box.y0 / PDF_OCR_ZOOM,
                                         w.box.x1 / PDF_OCR_ZOOM, w.box.y1 / PDF_OCR_ZOOM),
                             ("ocr",) + w.line_key, w.confidence)
                        for w in ocr_raw
                    ]
                    extra = [w for w in scaled if not any(w.box.intersects(n.box) for n in words)]
                    if extra:
                        result.ocr_pages.append(page_no)
                        result.findings += _text_findings(extra, page_no, pw, ph, "ocr", use_entities)
                except ocr.OCRUnavailable as exc:
                    result.notes.append(f"Text recognition unavailable on page {page_no + 1}: {exc}")
            result.findings += _text_findings(words, page_no, pw, ph, "text", use_entities)

            if coverage > 0.02:
                raster = render_page(page, PDF_FACE_ZOOM)
                result.findings += _face_findings(raster, page_no, raster.width, raster.height)
        return result
    finally:
        doc.close()


def analyze(data: bytes, kind: str, **kwargs) -> AnalysisResult:
    return analyze_pdf(data, **kwargs) if kind == "pdf" else analyze_image(data, **kwargs)
