from __future__ import annotations

import threading
from dataclasses import dataclass, field

from app.config import Settings
from app.crypto.aead import EnvelopeCipher
from app.services.storage import BlobStore


@dataclass
class Services:
    settings: Settings
    cipher: EnvelopeCipher
    store: BlobStore
    jobs: threading.BoundedSemaphore = field(init=False)

    def __post_init__(self) -> None:
        self.jobs = threading.BoundedSemaphore(self.settings.max_concurrent_jobs)

    @classmethod
    def from_settings(cls, settings: Settings) -> Services:
        return cls(
            settings=settings,
            cipher=EnvelopeCipher(settings.master_key_bytes(), settings.master_key_id),
            store=BlobStore(settings.storage_dir),
        )
