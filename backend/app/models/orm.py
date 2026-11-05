"""Database schema.

What is deliberately NOT stored: raw OCR text, matched sensitive strings,
plaintext filenames, plaintext file bytes, capability tokens, or client IPs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class ProcessingSession(Base):
    """A short-lived workspace for one uploaded file."""

    __tablename__ = "processing_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="analyzed")  # analyzed | redacted
    kind: Mapped[str] = mapped_column(String(8))  # image | pdf
    mime: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    pages: Mapped[list] = mapped_column(JSON, default=list)  # [{width, height}]
    encrypted_name: Mapped[bytes] = mapped_column(LargeBinary)
    # Encrypted original, deleted as soon as redaction completes.
    original_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    original_wrapped_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    metadata_findings: Mapped[list] = mapped_column(JSON, default=list)  # keys/labels only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    detections: Mapped[list[Detection]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Detection.ordinal"
    )
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="session")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("processing_sessions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(24))
    label: Mapped[str] = mapped_column(String(48))
    source: Mapped[str] = mapped_column(String(16))  # ocr | text | face | entity
    page: Mapped[int] = mapped_column(Integer, default=0)
    # Normalised [0, 1] boxes; one detection may span several boxes (wrapped lines).
    boxes: Mapped[list] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    masked_preview: Mapped[str] = mapped_column(String(64))

    session: Mapped[ProcessingSession] = relationship(back_populates="detections")


class Artifact(Base):
    """A sanitized, encrypted output file."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("processing_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(32), unique=True)
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[str] = mapped_column(String(16))
    mime: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    encrypted_name: Mapped[bytes] = mapped_column(LargeBinary)
    # Hash of the session token that may download/share it (survives session cleanup).
    owner_token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    session: Mapped[ProcessingSession | None] = relationship(back_populates="artifacts")
    shares: Mapped[list[Share]] = relationship(back_populates="artifact", cascade="all, delete-orphan")


class Share(Base):
    __tablename__ = "shares"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    manage_token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    max_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    artifact: Mapped[Artifact] = relationship(back_populates="shares")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    outcome: Mapped[str] = mapped_column(String(16))  # success | denied | rejected | error
    actor: Mapped[str | None] = mapped_column(String(24), nullable=True)  # HMAC of client IP
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    share_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_audit_type_time", "event_type", "created_at"),)
