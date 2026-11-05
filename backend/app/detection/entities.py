"""Optional context-aware entity recognition via Microsoft Presidio.

Presidio (with a small local spaCy model) is used for person names, which
regexes cannot find. Everything runs locally. If Presidio or the model is not
installed the detector reports itself unavailable and the pipeline continues.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable

from app.detection import masking
from app.detection.types import OTHER, TextMatch

log = logging.getLogger("afterimage.detection")

_lock = threading.Lock()
_analyzer = None
_unavailable_reason: str | None = None


def _load():
    global _analyzer, _unavailable_reason
    with _lock:
        if _analyzer is not None or _unavailable_reason is not None:
            return _analyzer
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            })
            _analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        except Exception as exc:  # pragma: no cover - depends on environment
            _unavailable_reason = f"{type(exc).__name__}"
            log.warning("Presidio unavailable (%s); name detection disabled", _unavailable_reason)
        return _analyzer


def available() -> bool:
    return _load() is not None


def find_names(text: str) -> Iterable[TextMatch]:
    analyzer = _load()
    if analyzer is None or not text.strip():
        return []
    results = analyzer.analyze(text=text[:100_000], language="en", entities=["PERSON"], score_threshold=0.6)
    out: list[TextMatch] = []
    for r in results:
        value = text[r.start:r.end]
        # spaCy-small is noisy on UI text: require 2+ capitalised tokens on one line.
        tokens = value.split()
        if "\n" in value or len(tokens) < 2 or not all(t[:1].isupper() for t in tokens) or len(value) > 48:
            continue
        out.append(TextMatch(r.start, r.end, OTHER, "Person name", round(min(0.6, r.score * 0.7), 2), masking.mask_words(value)))
    return out
