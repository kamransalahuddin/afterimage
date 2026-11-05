"""Synthetic test documents.

Every value here is fake: reserved example domains, 555-01xx phone numbers,
public card-network *test* numbers, AWS's documented example key, and tokens
generated at runtime (so no credential-shaped literal is committed to git).

Run `python -m tests.fixtures.synthetic out/` to write the samples to disk for
manual demo use.
"""

from __future__ import annotations

import io
import random
import string
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

FAKE_EMAIL = "jordan.avery@example.com"
FAKE_PHONE = "(312) 555-0142"
FAKE_CARD = "4242 4242 4242 4242"  # Stripe's public Visa test number
FAKE_ADDRESS = "1200 Lakeshore Drive, Chicago, IL 60611"
FAKE_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"  # AWS documentation example
FAKE_SSN = "123-45-6789"


def fake_github_token(seed: int = 7) -> str:
    rng = random.Random(seed)
    return "ghp_" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(36))


def _font(size: int = 30):
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/Library/Fonts/Arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def text_image(lines: list[str], *, size=(1400, 90), fmt="PNG", dark=False, exif=None) -> bytes:
    w = size[0]
    h = max(size[1], 40 + 60 * len(lines))
    bg, fg = ((24, 24, 27), (235, 235, 240)) if dark else ((255, 255, 255), (20, 20, 24))
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    font = _font()
    for i, line in enumerate(lines):
        draw.text((40, 24 + 60 * i), line, fill=fg, font=font)
    buf = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def screenshot_png() -> bytes:
    return text_image([
        f"Email: {FAKE_EMAIL}",
        f"Phone: {FAKE_PHONE}",
        f"Card: {FAKE_CARD}",
        f"Address: {FAKE_ADDRESS}",
        f"AWS_ACCESS_KEY_ID={FAKE_AWS_KEY}",
        f"token: {fake_github_token()}",
    ])


def jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (640, 480), (200, 210, 220))
    exif = img.getexif()
    exif[0x010F] = "FakeCam"        # Make
    exif[0x0110] = "Model X1"       # Model
    exif[0x0131] = "FakeOS 1.0"     # Software
    exif[0x0132] = "2024:05:01 10:00:00"
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (41.0, 52.0, 41.0)
    gps[3] = "W"
    gps[4] = (87.0, 37.0, 47.0)
    sub = exif.get_ifd(0x8769)
    sub[36867] = "2024:05:01 10:00:00"
    sub[42033] = "SN-0000-FAKE-1234"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif, quality=90)
    return buf.getvalue()


def sample_pdf(*, with_metadata=True, extra_secret: str | None = None) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    y = 90
    lines = [
        "Customer record (synthetic)",
        f"Email: {FAKE_EMAIL}",
        f"Phone: {FAKE_PHONE}",
        f"Card number: {FAKE_CARD}",
        f"SSN: {FAKE_SSN}",
        f"Address: {FAKE_ADDRESS}",
        f"Access key: {FAKE_AWS_KEY}",
    ]
    if extra_secret:
        lines.append(f"token: {extra_secret}")
    for line in lines:
        page.insert_text((72, y), line, fontsize=13)
        y += 28
    page.add_text_annot((400, 90), f"Reviewer note: call {FAKE_PHONE}")
    if with_metadata:
        doc.set_metadata({"author": "Jordan Avery", "title": "Customer record", "creator": "FakeWriter 2.0",
                          "producer": "FakePDF", "subject": "Synthetic"})
    page2 = doc.new_page(width=612, height=792)
    page2.insert_text((72, 90), "Page two contains nothing sensitive.", fontsize=13)
    out = doc.tobytes()
    doc.close()
    return out


def scanned_pdf() -> bytes:
    """A PDF whose only content is an image of text (requires OCR)."""
    png = text_image([f"Contact {FAKE_EMAIL}", f"Card {FAKE_CARD}"], size=(1700, 200))
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=200)
    page.insert_image(page.rect, stream=png)
    out = doc.tobytes()
    doc.close()
    return out


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
    out.mkdir(parents=True, exist_ok=True)
    (out / "screenshot.png").write_bytes(screenshot_png())
    (out / "dark-screenshot.png").write_bytes(text_image([f"Email: {FAKE_EMAIL}", f"API_KEY={fake_github_token(3)}"], dark=True))
    (out / "photo-with-gps.jpg").write_bytes(jpeg_with_gps())
    (out / "record.pdf").write_bytes(sample_pdf())
    (out / "scanned.pdf").write_bytes(scanned_pdf())
    print(f"wrote samples to {out}/")
