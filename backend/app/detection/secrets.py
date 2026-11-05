"""Credential and secret detection.

Three tiers, in decreasing confidence:

1. Provider-specific formats with distinctive prefixes (AWS, GitHub, Stripe ...).
2. Structural formats (JWT, PEM private keys, Bearer/Basic auth, credentials in URLs).
3. High-entropy values that appear next to a contextual keyword such as
   `api_key=` or a "Secret key" label.

A random-looking string with no context is deliberately NOT reported: hashes,
UUIDs and build IDs are everywhere in screenshots and would drown real findings.
"""

from __future__ import annotations

import base64
import json
import math
import re
from collections import Counter
from collections.abc import Iterable

from app.detection import masking
from app.detection.types import SECRET, TextMatch

# (label, pattern, confidence, visible-prefix length for the masked preview)
_PROVIDER_PATTERNS: list[tuple[str, re.Pattern[str], float, int]] = [
    ("Private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----[\s\S]{0,6000}?(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----|\Z)"), 0.99, 0),
    ("AWS access key ID", re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b"), 0.95, 4),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{60,255})\b"), 0.98, 4),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"), 0.97, 6),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b"), 0.97, 5),
    ("Slack webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{20,}"), 0.97, 0),
    ("Stripe secret key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"), 0.97, 8),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), 0.98, 7),
    ("OpenAI API key", re.compile(r"\bsk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}\b"), 0.9, 3),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), 0.95, 4),
    ("SendGrid API key", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,32}\.[A-Za-z0-9_-]{16,64}\b"), 0.97, 3),
    ("Twilio API key", re.compile(r"\bSK[0-9a-f]{32}\b"), 0.8, 2),
    ("npm token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"), 0.97, 4),
    ("PyPI token", re.compile(r"\bpypi-[A-Za-z0-9_-]{50,}\b"), 0.97, 5),
    ("Discord webhook", re.compile(r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]{30,}"), 0.95, 0),
]

_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_BEARER_RE = re.compile(r"\b[Bb]earer\s+([A-Za-z0-9\-._~+/]{20,}=*)")
_BASIC_RE = re.compile(r"(?i)authorization\s*[:=]?\s*[\"']?Basic\s+([A-Za-z0-9+/]{12,}={0,2})")
_URL_CREDS_RE = re.compile(r"\b[a-z][a-z0-9+.-]{1,20}://([^\s:/@]{1,64}:[^\s@/]{3,128})@[^\s/]+", re.IGNORECASE)

_KEYWORDS = (
    r"api[_\- ]?key|apikey|secret|token|passwd|password|passphrase|pwd|access[_\- ]?key|"
    r"client[_\- ]?secret|auth[_\- ]?key|private[_\- ]?key|credential|signing[_\- ]?key"
)
_ASSIGNMENT_RE = re.compile(
    rf"(?i)\b([A-Za-z0-9_.-]*(?:{_KEYWORDS})s?[A-Za-z0-9_.-]*)[\"']?\s*(?:=>|:=|[:=])\s*[\"'`]?([^\s\"'`,;]{{6,}})"
)
_CONTEXT_RE = re.compile(rf"(?i)\b(?:{_KEYWORDS}|bearer)\b")
_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9+/_=-])[A-Za-z0-9+/_=-]{20,}(?![A-Za-z0-9+/_=-])")
_PLACEHOLDER_RE = re.compile(
    r"(?i)^(?:\*+|x+|\.+|•+|<.*>|\$\{.*\}|\{\{.*\}\}|%.*%|your[_-].*|example.*|changeme|redacted|null|none|true|false|undefined|required|optional|string)$"
)
_REFERENCE_RE = re.compile(r"(?i)^(?:process\.env|os\.environ|env\.|settings\.|config\.|self\.|this\.)")


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    n = len(value)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _char_classes(value: str) -> int:
    return sum(bool(re.search(p, value)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))


def looks_random(value: str, min_len: int = 16, min_entropy: float = 3.0) -> bool:
    return (
        len(value) >= min_len
        and shannon_entropy(value) >= min_entropy
        and _char_classes(value) >= 2
        and bool(re.search(r"\d", value))
    )


def _jwt_header_ok(token: str) -> bool:
    head = token.split(".", 1)[0]
    try:
        decoded = json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))
        return isinstance(decoded, dict) and "alg" in decoded
    except Exception:
        return False


def find_secrets(text: str) -> Iterable[TextMatch]:
    for label, pattern, conf, prefix in _PROVIDER_PATTERNS:
        for m in pattern.finditer(text):
            yield TextMatch(m.start(), m.end(), SECRET, label, conf, masking.mask_secret(m.group(0), prefix))

    for m in _JWT_RE.finditer(text):
        # OCR can garble a character or two; an undecodable header lowers confidence.
        conf = 0.95 if _jwt_header_ok(m.group(0)) else 0.75
        yield TextMatch(m.start(), m.end(), SECRET, "JSON Web Token", conf, masking.mask_secret(m.group(0), 3))

    for m in _BEARER_RE.finditer(text):
        yield TextMatch(m.start(1), m.end(1), SECRET, "Bearer token", 0.9, masking.mask_secret(m.group(1)))

    for m in _BASIC_RE.finditer(text):
        yield TextMatch(m.start(1), m.end(1), SECRET, "Basic auth credentials", 0.85, masking.mask_secret(m.group(1)))

    for m in _URL_CREDS_RE.finditer(text):
        yield TextMatch(m.start(1), m.end(1), SECRET, "Credentials in URL", 0.95, masking.mask_secret(m.group(1)))

    for m in _ASSIGNMENT_RE.finditer(text):
        key, value = m.group(1).lower(), m.group(2)
        if _PLACEHOLDER_RE.match(value) or _REFERENCE_RE.match(value):
            continue
        is_password = any(k in key for k in ("pass", "pwd"))
        if is_password and len(value) >= 6 and not value.isalpha():
            conf = 0.8
        elif is_password and len(value) >= 8:
            conf = 0.6
        elif looks_random(value):
            conf = 0.85
        elif looks_random(value, min_len=10, min_entropy=2.8):
            conf = 0.6
        else:
            continue
        label = "Password" if is_password else "Secret value"
        yield TextMatch(m.start(2), m.end(2), SECRET, label, conf, masking.mask_secret(value))

    # Labels on one line, value on the next (common in dashboards).
    for m in _CANDIDATE_RE.finditer(text):
        value = m.group(0)
        if not looks_random(value, min_len=20, min_entropy=3.5):
            continue
        window = text[max(0, m.start() - 48):m.start()]
        if _CONTEXT_RE.search(window):
            yield TextMatch(m.start(), m.end(), SECRET, "Possible secret", 0.7, masking.mask_secret(value))
