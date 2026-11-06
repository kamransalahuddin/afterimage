"""Redaction permanence for images and PDFs, plus metadata stripping."""

from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image

from app.detection import ocr
from app.detection.pipeline import analyze_image, analyze_pdf
from app.redaction.engine import Region, redact_image, redact_pdf
from tests.fixtures import synthetic as fx

needs_ocr = pytest.mark.skipif(ocr.tesseract_version() is None, reason="Tesseract not installed")


def regions_for(result, categories=None):
    out = []
    for f in result.findings:
        if categories is None or f.category in categories:
            out += [Region(f.page, b.x0, b.y0, b.x1, b.y1) for b in f.boxes]
    return out


def ocr_text(data: bytes) -> str:
    img = Image.open(io.BytesIO(data))
    return " ".join(w.text for w in ocr.ocr_words(img))


# ---------------------------------------------------------------- OCR + detection on images

@needs_ocr
def test_screenshot_detection_finds_expected_categories():
    result = analyze_image(fx.screenshot_png(), use_entities=False)
    labels = {f.label for f in result.findings}
    cats = {f.category for f in result.findings}
    assert {"email", "phone", "card", "secret", "address"} <= cats, labels
    assert "AWS access key ID" in labels
    # The GitHub token must be caught. Some Tesseract builds misread one character of it,
    # in which case the generic high-entropy rule flags it instead of the ghp_ pattern.
    secret_labels = sorted(f.label for f in result.findings if f.category == "secret")
    assert len(secret_labels) == 2 and ({"GitHub token", "Secret value"} & set(secret_labels)), secret_labels
    for f in result.findings:
        for b in f.boxes:
            assert 0 <= b.x0 < b.x1 <= 1 and 0 <= b.y0 < b.y1 <= 1


@needs_ocr
def test_dark_mode_screenshot():
    data = fx.text_image([f"Email: {fx.FAKE_EMAIL}"], dark=True)
    result = analyze_image(data, use_entities=False)
    assert any(f.category == "email" for f in result.findings)


# ---------------------------------------------------------------- image permanence

@needs_ocr
@pytest.mark.parametrize("fmt,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_image_redaction_is_permanent(fmt, mime):
    lines = [f"Email: {fx.FAKE_EMAIL}", f"Card: {fx.FAKE_CARD}"]
    data = fx.text_image(lines, fmt=fmt)
    result = analyze_image(data, use_entities=False)
    out = redact_image(data, mime, regions_for(result))
    assert out.report["verification"]["regions_verified"] >= 2

    text_after = ocr_text(out.data)
    assert "jordan" not in text_after.lower() and "example.com" not in text_after
    assert "4242" not in text_after
    # Labels outside the boxes are untouched (pixel check; OCR next to a solid
    # block is unreliable for the label itself).
    src = Image.open(io.BytesIO(data)).convert("L").crop((40, 28, 118, 54))
    dst = Image.open(io.BytesIO(out.data)).convert("L").crop((40, 28, 118, 54))
    assert abs(sum(src.getdata()) - sum(dst.getdata())) / (78 * 26) < 6

    # Re-analysis of the output finds nothing left to redact.
    again = analyze_image(out.data, use_entities=False)
    assert not [f for f in again.findings if f.category in ("email", "card")]


def test_image_redaction_pixels_overwritten():
    img = Image.new("RGB", (200, 100), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = redact_image(buf.getvalue(), "image/png", [Region(0, 0.25, 0.25, 0.75, 0.75)])
    result = Image.open(io.BytesIO(out.data)).convert("RGB")
    assert result.getpixel((100, 50)) == (0, 0, 0)
    assert result.getpixel((10, 10)) == (255, 0, 0)
    # No red survives anywhere inside the region.
    crop = result.crop((50, 25, 150, 75))
    assert crop.getextrema()[0] == (0, 0)


def test_transparent_png_region_becomes_opaque():
    img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = redact_image(buf.getvalue(), "image/png", [Region(0, 0.1, 0.1, 0.5, 0.5)])
    px = Image.open(io.BytesIO(out.data)).getpixel((30, 30))
    assert px == (0, 0, 0, 255)


def test_image_metadata_is_detected_and_stripped():
    data = fx.jpeg_with_gps()
    result = analyze_image(data, use_entities=False)
    keys = {m.key for m in result.metadata}
    assert {"gps", "device", "timestamp", "serial", "software"} <= keys
    gps = next(m for m in result.metadata if m.key == "gps")
    assert gps.value.startswith("41.87")

    out = redact_image(data, "image/jpeg", [])
    clean = Image.open(io.BytesIO(out.data))
    assert len(clean.getexif()) == 0
    assert b"FakeCam" not in out.data and b"SN-0000" not in out.data and b"GPS" not in out.data
    assert not any(k in clean.info for k in ("exif", "xmp", "icc_profile"))


def test_png_text_chunks_stripped():
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "Jordan Avery")
    info.add_text("Comment", fx.FAKE_EMAIL)
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(buf, "PNG", pnginfo=info)
    assert any(m.key == "text" for m in analyze_image(buf.getvalue(), use_entities=False).metadata)
    out = redact_image(buf.getvalue(), "image/png", [])
    assert b"Jordan" not in out.data and b"example.com" not in out.data


def test_exif_orientation_is_baked_in():
    img = Image.new("RGB", (200, 100), "white")
    img.paste((255, 0, 0), (0, 0, 20, 20))  # red square top-left in stored orientation
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90 CW on display
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    result = analyze_image(buf.getvalue(), use_entities=False)
    assert (result.pages[0].width, result.pages[0].height) == (100, 200)
    out = Image.open(io.BytesIO(redact_image(buf.getvalue(), "image/jpeg", []).data))
    assert out.size == (100, 200) and 0x0112 not in out.getexif()


# ---------------------------------------------------------------- PDF permanence

SENSITIVE = [fx.FAKE_EMAIL, fx.FAKE_CARD, fx.FAKE_SSN, fx.FAKE_AWS_KEY, "4242"]


def pdf_text(data: bytes) -> str:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        return "".join(p.get_text("text") for p in doc)
    finally:
        doc.close()


def test_pdf_detection():
    result = analyze_pdf(fx.sample_pdf(), use_entities=False)
    cats = {f.category for f in result.findings}
    assert {"email", "phone", "card", "secret", "address", "other"} <= cats
    meta = {m.key for m in result.metadata}
    assert {"author", "title", "annotations"} <= meta


@pytest.mark.parametrize("rasterize", [False, True])
def test_pdf_redaction_removes_text(rasterize):
    data = fx.sample_pdf()
    before = pdf_text(data)
    assert all(s in before for s in SENSITIVE)

    result = analyze_pdf(data, use_entities=False)
    out = redact_pdf(data, regions_for(result), rasterize=rasterize)
    after = pdf_text(out.data)
    for s in SENSITIVE:
        assert s not in after, f"{s!r} still extractable"
    # Also check raw bytes (catches uncompressed leftovers).
    raw = pymupdf.open(stream=out.data, filetype="pdf")
    try:
        for xref in range(1, raw.xref_length()):
            stream = raw.xref_stream(xref) or b""
            assert fx.FAKE_EMAIL.encode() not in stream
    finally:
        raw.close()
    assert out.report["verification"]["text_in_redacted_areas"] == 0
    if not rasterize:
        assert "Customer record" in after  # unselected content is preserved


def test_pdf_metadata_and_annotations_removed():
    data = fx.sample_pdf()
    out = redact_pdf(data, [])
    doc = pymupdf.open(stream=out.data, filetype="pdf")
    try:
        meta = doc.metadata
        assert not meta.get("author") and not meta.get("title") and not meta.get("creator")
        assert not any(list(p.annots() or []) for p in doc)
        assert not doc.get_xml_metadata()
    finally:
        doc.close()
    assert b"Jordan Avery" not in out.data and b"Reviewer note" not in out.data


def test_pdf_residual_occurrence_reported():
    """If a redacted value also appears in a place the user did not select, we say so."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), f"Email {fx.FAKE_EMAIL}", fontsize=12)
    page.insert_text((72, 300), f"Again {fx.FAKE_EMAIL}", fontsize=12)
    data = doc.tobytes()
    result = analyze_pdf(data, use_entities=False)
    first = [f for f in result.findings if f.category == "email"][0]
    out = redact_pdf(data, regions_for(type(result)(pages=result.pages, findings=[first])))
    assert out.report["verification"]["residual_matches"] == 1


def test_rotated_pdf_page():
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), f"Email {fx.FAKE_EMAIL}", fontsize=12)
    page.set_rotation(90)
    data = doc.tobytes()
    result = analyze_pdf(data, use_entities=False)
    assert result.pages[0].width == 792
    out = redact_pdf(data, regions_for(result))
    assert fx.FAKE_EMAIL not in pdf_text(out.data)


@needs_ocr
def test_scanned_pdf_is_ocrd_and_redacted():
    data = fx.scanned_pdf()
    result = analyze_pdf(data, use_entities=False)
    assert 0 in result.ocr_pages
    cats = {f.category for f in result.findings}
    assert {"email", "card"} <= cats
    out = redact_pdf(data, regions_for(result), rasterize=True)
    doc = pymupdf.open(stream=out.data, filetype="pdf")
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    words = " ".join(w.text for w in ocr.ocr_words(img))
    assert "example.com" not in words and "4242" not in words
