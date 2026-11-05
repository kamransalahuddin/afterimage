"""Capability tokens.

Tokens are 256 bits from the OS CSPRNG, encoded base64url. Only their SHA-256
digest is persisted. Because tokens carry full entropy, a fast hash is
appropriate (no password-style stretching is needed) and lets us look tokens up
by digest with an index.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

TOKEN_BYTES = 32
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def looks_like_token(value: str | None) -> bool:
    return bool(value) and bool(_TOKEN_RE.match(value))  # type: ignore[arg-type]


def verify_token(token: str | None, expected_hash: str) -> bool:
    if not looks_like_token(token):
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)  # type: ignore[arg-type]


def pseudonymize(value: str, secret: bytes) -> str:
    """Keyed hash for values (like client IPs) we want to correlate but not store."""
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()[:24]
