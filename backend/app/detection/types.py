from __future__ import annotations

from dataclasses import dataclass, field

# Public category identifiers (mirrored by the frontend).
FACE = "face"
EMAIL = "email"
PHONE = "phone"
ADDRESS = "address"
SECRET = "secret"
CARD = "card"
OTHER = "other"

CATEGORIES = (FACE, EMAIL, PHONE, ADDRESS, SECRET, CARD, OTHER)

# Lower number wins when two text matches overlap.
PRIORITY = {SECRET: 0, CARD: 1, EMAIL: 2, OTHER: 3, PHONE: 4, ADDRESS: 5}


@dataclass(frozen=True)
class Box:
    """Axis-aligned box in source coordinates (pixels for images, points for PDFs)."""

    x0: float
    y0: float
    x1: float
    y1: float

    def union(self, other: Box) -> Box:
        return Box(min(self.x0, other.x0), min(self.y0, other.y0), max(self.x1, other.x1), max(self.y1, other.y1))

    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def intersects(self, other: Box) -> bool:
        return self.x0 < other.x1 and other.x0 < self.x1 and self.y0 < other.y1 and other.y0 < self.y1


@dataclass(frozen=True)
class Word:
    text: str
    box: Box
    line_key: tuple  # words sharing a key are on the same visual line
    confidence: float = 100.0  # OCR confidence 0-100 (100 for native PDF text)


@dataclass(frozen=True)
class TextMatch:
    start: int
    end: int
    category: str
    label: str
    confidence: float
    masked: str


@dataclass
class Finding:
    category: str
    label: str
    page: int
    boxes: list[Box]
    confidence: float
    masked: str
    source: str  # ocr | text | face | entity


@dataclass
class MetadataFinding:
    key: str
    label: str
    value: str


@dataclass
class PageInfo:
    width: float
    height: float


@dataclass
class AnalysisResult:
    pages: list[PageInfo]
    findings: list[Finding] = field(default_factory=list)
    metadata: list[MetadataFinding] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
