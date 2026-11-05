"""Maps character offsets in reconstructed text back to page geometry.

Detectors operate on plain strings. A TextLayer joins positioned words into
lines ("\n"-separated) while remembering each word's span, so any match
(start, end) can be converted into one bounding box per visual line touched.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.detection.types import Box, Word


@dataclass
class _Span:
    start: int
    end: int
    word: Word


class TextLayer:
    def __init__(self, words: list[Word]) -> None:
        self.words = words
        self.spans: list[_Span] = []
        parts: list[str] = []
        pos = 0
        prev_line = object()
        for w in words:
            if not w.text:
                continue
            if self.spans:
                sep = " " if w.line_key == prev_line else "\n"
                parts.append(sep)
                pos += 1
            self.spans.append(_Span(pos, pos + len(w.text), w))
            parts.append(w.text)
            pos += len(w.text)
            prev_line = w.line_key
        self.text = "".join(parts)

    def boxes_for(self, start: int, end: int) -> list[Box]:
        by_line: dict[tuple, Box] = {}
        order: list[tuple] = []
        for span in self.spans:
            if span.end <= start or span.start >= end:
                continue
            w = span.word
            n = max(1, span.end - span.start)
            # Slice partially-covered words proportionally, padded by ~half a glyph.
            a = max(start, span.start) - span.start
            b = min(end, span.end) - span.start
            glyph = (w.box.x1 - w.box.x0) / n
            x0 = w.box.x0 + glyph * a - (glyph * 0.5 if a > 0 else 0)
            x1 = w.box.x0 + glyph * b + (glyph * 0.5 if b < n else 0)
            box = Box(max(w.box.x0, x0), w.box.y0, min(w.box.x1, x1), w.box.y1)
            if w.line_key in by_line:
                by_line[w.line_key] = by_line[w.line_key].union(box)
            else:
                by_line[w.line_key] = box
                order.append(w.line_key)
        return [by_line[k] for k in order]

    def min_confidence(self, start: int, end: int) -> float:
        confs = [s.word.confidence for s in self.spans if not (s.end <= start or s.start >= end)]
        return min(confs) if confs else 100.0
