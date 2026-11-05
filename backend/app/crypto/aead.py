"""Envelope encryption built on AES-256-GCM from `cryptography`.

Design
------
* Every stored object (an uploaded original or a sanitized artifact) is
  encrypted with its own freshly generated 256-bit data key (DEK).
* The DEK is wrapped (encrypted) with the server master key (KEK) using
  AES-256-GCM and stored in PostgreSQL next to the object's metadata.
* The encrypted bytes on disk never contain key material.
* Both layers use a unique 96-bit random nonce per encryption and bind the
  object identity as associated data, so a ciphertext cannot be swapped onto
  another record without failing authentication.
* Deleting the wrapped DEK from the database makes the blob on disk
  unrecoverable even if the file itself lingers (crypto-shredding).

No primitives are implemented here; this module only composes the AEAD
construction provided by the `cryptography` library.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32
FORMAT_VERSION = b"AI1"


class DecryptionError(Exception):
    """Raised when ciphertext fails authentication (tampered, wrong key or wrong context)."""


@dataclass(frozen=True)
class SealedObject:
    blob: bytes  # version || nonce || ciphertext+tag, written to disk
    wrapped_key: bytes  # nonce || wrapped DEK+tag, stored in the database
    key_id: str


def _aad(purpose: str, object_id: str) -> bytes:
    return f"afterimage:{purpose}:{object_id}".encode()


def encrypt(plaintext: bytes, key: bytes, aad: bytes) -> bytes:
    if len(key) != KEY_BYTES:
        raise ValueError("AES-256-GCM requires a 32-byte key")
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(token: bytes, key: bytes, aad: bytes) -> bytes:
    if len(token) < NONCE_BYTES + 16:
        raise DecryptionError("ciphertext too short")
    nonce, body = token[:NONCE_BYTES], token[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, body, aad)
    except InvalidTag as exc:
        raise DecryptionError("authentication failed") from exc


class EnvelopeCipher:
    def __init__(self, master_key: bytes, key_id: str = "k1") -> None:
        if len(master_key) != KEY_BYTES:
            raise ValueError("master key must be 32 bytes")
        self._kek = master_key
        self.key_id = key_id

    def seal(self, plaintext: bytes, *, purpose: str, object_id: str) -> SealedObject:
        dek = AESGCM.generate_key(bit_length=256)
        aad = _aad(purpose, object_id)
        blob = FORMAT_VERSION + encrypt(plaintext, dek, aad)
        wrapped = encrypt(dek, self._kek, _aad("dek:" + purpose, object_id))
        return SealedObject(blob=blob, wrapped_key=wrapped, key_id=self.key_id)

    def open(self, blob: bytes, wrapped_key: bytes, *, purpose: str, object_id: str) -> bytes:
        if not blob.startswith(FORMAT_VERSION):
            raise DecryptionError("unknown blob format")
        dek = decrypt(wrapped_key, self._kek, _aad("dek:" + purpose, object_id))
        return decrypt(blob[len(FORMAT_VERSION):], dek, _aad(purpose, object_id))

    # Small helpers for encrypting short strings (e.g. original filenames).
    def seal_text(self, text: str, *, purpose: str, object_id: str) -> bytes:
        return encrypt(text.encode(), self._kek, _aad("text:" + purpose, object_id))

    def open_text(self, token: bytes, *, purpose: str, object_id: str) -> str:
        return decrypt(token, self._kek, _aad("text:" + purpose, object_id)).decode()
