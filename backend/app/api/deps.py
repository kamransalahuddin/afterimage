from __future__ import annotations

from fastapi import Header, Request

from app.services.context import Services


def services(request: Request) -> Services:
    return request.app.state.services


def session_token(x_session_token: str | None = Header(default=None)) -> str | None:
    return x_session_token


def bearer(authorization: str | None = Header(default=None)) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
TOKEN_PATTERN = r"^[A-Za-z0-9_-]{43}$"
