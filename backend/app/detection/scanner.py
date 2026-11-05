"""Runs every text detector and resolves overlapping matches."""

from __future__ import annotations

from app.detection import entities
from app.detection.pii import ALL_PII_DETECTORS
from app.detection.secrets import find_secrets
from app.detection.types import PRIORITY, TextMatch


def _overlap(a: TextMatch, b: TextMatch) -> int:
    return max(0, min(a.end, b.end) - max(a.start, b.start))


def resolve_overlaps(matches: list[TextMatch]) -> list[TextMatch]:
    """Keep the strongest match; drop others mostly covered by it."""
    ranked = sorted(
        matches,
        key=lambda m: (PRIORITY.get(m.category, 9), -m.confidence, -(m.end - m.start)),
    )
    kept: list[TextMatch] = []
    for m in ranked:
        length = max(1, m.end - m.start)
        if any(_overlap(m, k) / length >= 0.5 for k in kept):
            continue
        kept.append(m)
    return sorted(kept, key=lambda m: m.start)


def scan_text(text: str, *, use_entities: bool = True) -> list[TextMatch]:
    if not text:
        return []
    matches: list[TextMatch] = list(find_secrets(text))
    for detector in ALL_PII_DETECTORS:
        matches.extend(detector(text))
    if use_entities:
        matches.extend(entities.find_names(text))
    return resolve_overlaps(matches)
