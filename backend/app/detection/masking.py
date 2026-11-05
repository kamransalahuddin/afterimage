"""Short masked previews. These are the only representation of a finding we keep."""

from __future__ import annotations

DOT = "•"


def mask_generic(value: str) -> str:
    v = value.strip()
    if len(v) >= 10:
        return f"{v[:2]}{DOT * 5}{v[-2:]}"
    return DOT * 6


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    return f"{local[:1]}{DOT * 3}@{DOT * 3}.{tld}"


def mask_digits_tail(value: str, keep: int) -> str:
    digits = "".join(c for c in value if c.isdigit())
    return f"{DOT * 4} {digits[-keep:]}" if len(digits) > keep else DOT * 6


def mask_secret(value: str, prefix_len: int = 0) -> str:
    prefix = value[:prefix_len] if prefix_len else ""
    return f"{prefix}{DOT * 8}"


def mask_words(value: str) -> str:
    parts = value.split()
    return " ".join(p[:1] + DOT * 3 for p in parts[:3])
