"""Encrypted blob storage on local disk.

Storage keys are always generated server-side (128 random bits, hex) and are
validated against a strict pattern before touching the filesystem, so no user
input can ever influence a path. Every resolved path is additionally checked
to sit inside the storage root.
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

_KEY_RE = re.compile(r"^[a-f0-9]{32}$")
BUCKETS = ("originals", "artifacts")


class StorageError(Exception):
    pass


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        for bucket in BUCKETS:
            (self.root / bucket).mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def new_key() -> str:
        return secrets.token_hex(16)

    def _path(self, bucket: str, key: str) -> Path:
        if bucket not in BUCKETS or not isinstance(key, str) or not _KEY_RE.match(key):
            raise StorageError("invalid storage key")
        path = (self.root / bucket / f"{key}.bin").resolve()
        if path.parent != self.root / bucket:
            raise StorageError("path escapes storage root")
        return path

    def write(self, bucket: str, key: str, data: bytes) -> None:
        path = self._path(bucket, key)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def read(self, bucket: str, key: str) -> bytes:
        path = self._path(bucket, key)
        if not path.exists():
            raise StorageError("blob not found")
        return path.read_bytes()

    def delete(self, bucket: str, key: str | None) -> None:
        if not key:
            return
        try:
            path = self._path(bucket, key)
        except StorageError:
            return
        try:
            # Overwrite before unlinking. On SSDs/journaling filesystems this is
            # best-effort only; the real guarantee is crypto-shredding the DEK.
            size = path.stat().st_size
            with open(path, "r+b") as fh:
                fh.write(b"\0" * size)
            path.unlink()
        except FileNotFoundError:
            pass

    def keys(self, bucket: str) -> list[str]:
        return [p.stem for p in (self.root / bucket).glob("*.bin") if _KEY_RE.match(p.stem)]
