"""Runtime configuration.

All secrets come from the environment (or a local, git-ignored `.env`). Nothing
sensitive has a default value: the application refuses to start without a
master key rather than silently generating or hardcoding one.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from typing import Annotated

from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AFTERIMAGE_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql+psycopg://localhost/afterimage"
    storage_dir: Path = Path("./var/storage")

    # Base64url-encoded 32-byte key used to wrap per-object data keys.
    master_key: str = Field(default="", repr=False)
    master_key_id: str = "k1"
    # Secret used to pseudonymise client IPs in audit events (HMAC-SHA256).
    audit_secret: str = Field(default="", repr=False)
    # Optional bearer token that unlocks the read-only audit endpoint.
    admin_token: str = Field(default="", repr=False)

    public_base_url: str = "http://localhost:5173"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    trust_proxy_headers: bool = False

    # Upload and processing limits.
    max_upload_bytes: int = 20 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    max_image_side: int = 12_000
    max_pdf_pages: int = 25
    max_concurrent_jobs: int = 2
    ocr_timeout_seconds: int = 30

    # Lifetimes.
    session_ttl_minutes: int = 60
    unshared_artifact_ttl_minutes: int = 120
    cleanup_interval_seconds: int = 300

    enable_presidio: bool = True

    @field_validator("database_url", mode="after")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        # Hosted Postgres providers hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str) and not v.startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    def master_key_bytes(self) -> bytes:
        if not self.master_key:
            raise RuntimeError(
                "AFTERIMAGE_MASTER_KEY is not set. Generate one with `python -m app.cli genkey`."
            )
        # Accept base64url (from `genkey`) or standard base64 (e.g. host-generated secrets).
        raw = self.master_key.strip().rstrip("=").replace("+", "-").replace("/", "_")
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        if len(key) != 32:
            raise RuntimeError("AFTERIMAGE_MASTER_KEY must decode to exactly 32 bytes (AES-256).")
        return key

    def audit_secret_bytes(self) -> bytes:
        if not self.audit_secret:
            raise RuntimeError("AFTERIMAGE_AUDIT_SECRET is not set.")
        return self.audit_secret.encode()


_active: Settings | None = None


@lru_cache
def _env_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return _active or _env_settings()


def set_settings(settings: Settings) -> None:
    """Pin the settings used by the running app (create_app calls this)."""
    global _active
    _active = settings
