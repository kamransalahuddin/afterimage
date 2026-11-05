from __future__ import annotations


class AppError(Exception):
    """An error that is safe to show to the client."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def bad_request(code: str, message: str) -> AppError:
    return AppError(400, code, message)


def not_found(message: str = "Not found.") -> AppError:
    return AppError(404, "not_found", message)


def unauthorized(message: str = "Missing or invalid credentials.") -> AppError:
    return AppError(401, "unauthorized", message)


def gone(code: str, message: str) -> AppError:
    return AppError(410, code, message)
