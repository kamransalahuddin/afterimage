"""Local OCR with Tesseract, returning positioned words."""

from __future__ import annotations

import logging

import pytesseract
from PIL import Image, ImageOps, ImageStat

from app.detection.types import Box, Word

log = logging.getLogger("afterimage.detection")


class OCRUnavailable(RuntimeError):
    pass


def tesseract_version() -> str | None:
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return None


def _prepare(img: Image.Image) -> tuple[Image.Image, float]:
    gray = ImageOps.grayscale(img.convert("RGB"))
    # Dark-mode screenshots OCR far better inverted.
    if ImageStat.Stat(gray).mean[0] < 110:
        gray = ImageOps.invert(gray)
    scale = 1.0
    longest = max(gray.size)
    if longest < 1800:
        scale = 2.0  # small UI text benefits from upsampling
    elif longest > 5000:
        scale = 5000 / longest
    if scale != 1.0:
        gray = gray.resize((round(gray.width * scale), round(gray.height * scale)), Image.Resampling.LANCZOS)
    return gray, scale


def ocr_words(img: Image.Image, *, timeout: int = 30, page: int = 0) -> list[Word]:
    prepared, scale = _prepare(img)
    try:
        data = pytesseract.image_to_data(
            prepared, output_type=pytesseract.Output.DICT, config="--oem 1 --psm 3", timeout=timeout
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailable("Tesseract is not installed") from exc
    except RuntimeError as exc:  # pytesseract raises RuntimeError on timeout
        log.warning("OCR timed out on page %s", page)
        raise OCRUnavailable("OCR timed out") from exc

    words: list[Word] = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        box = Box(x / scale, y / scale, (x + w) / scale, (y + h) / scale)
        key = (page, data["block_num"][i], data["par_num"][i], data["line_num"][i])
        words.append(Word(text=text, box=box, line_key=key, confidence=conf))
    return words
