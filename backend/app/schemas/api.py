from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ExpiresIn = Literal["1h", "24h", "7d"]
EXPIRY_SECONDS: dict[str, int] = {"1h": 3600, "24h": 86_400, "7d": 604_800}


class BoxOut(BaseModel):
    x: float
    y: float
    w: float
    h: float


class DetectionOut(BaseModel):
    id: str
    category: str
    label: str
    page: int
    boxes: list[BoxOut]
    confidence: float
    preview: str
    source: str
    suggested: bool  # pre-selected for redaction in the UI


class MetadataOut(BaseModel):
    key: str
    label: str
    value: str


class PageOut(BaseModel):
    width: float
    height: float


class AnalyzeResponse(BaseModel):
    session_id: str
    session_token: str = Field(description="Bearer capability for this session. Shown once.")
    expires_at: datetime
    filename: str
    kind: str
    mime: str
    pages: list[PageOut]
    detections: list[DetectionOut]
    metadata: list[MetadataOut]
    notes: list[str]


class ManualRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(ge=0, le=500)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class RedactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    detection_ids: list[str] = Field(default_factory=list, max_length=2000)
    manual_regions: list[ManualRegion] = Field(default_factory=list, max_length=500)
    rasterize: bool = False


class RedactResponse(BaseModel):
    artifact_id: str
    filename: str
    mime: str
    size: int
    sha256: str
    expires_at: datetime
    regions: int
    metadata_removed: list[str]
    verification: dict


class ShareCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    expires_in: ExpiresIn = "24h"
    max_downloads: Literal[1, 5] | None = None


class ShareCreated(BaseModel):
    id: str
    url: str
    token: str = Field(description="Capability token, shown once.")
    manage_token: str = Field(description="Required to revoke. Shown once.")
    expires_at: datetime
    max_downloads: int | None


class SharePublic(BaseModel):
    filename: str
    mime: str
    size: int
    expires_at: datetime
    downloads_remaining: int | None


class ShareStatus(BaseModel):
    id: str
    expires_at: datetime
    max_downloads: int | None
    download_count: int
    revoked: bool
