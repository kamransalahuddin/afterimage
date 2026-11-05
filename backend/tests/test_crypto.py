from __future__ import annotations

import os

import pytest

from app.crypto.aead import DecryptionError, EnvelopeCipher, decrypt, encrypt
from app.crypto.tokens import hash_token, looks_like_token, new_token, verify_token


@pytest.fixture
def cipher():
    return EnvelopeCipher(os.urandom(32), "k1")


def test_round_trip(cipher):
    data = os.urandom(10_000)
    sealed = cipher.seal(data, purpose="artifact", object_id="obj-1")
    assert data not in sealed.blob
    assert cipher.open(sealed.blob, sealed.wrapped_key, purpose="artifact", object_id="obj-1") == data


def test_unique_nonces_and_keys(cipher):
    a = cipher.seal(b"same", purpose="artifact", object_id="x")
    b = cipher.seal(b"same", purpose="artifact", object_id="x")
    assert a.blob != b.blob and a.wrapped_key != b.wrapped_key
    assert a.blob[3:15] != b.blob[3:15]  # nonces differ


@pytest.mark.parametrize("where", ["blob_body", "blob_nonce", "blob_tag", "wrapped_key"])
def test_tampering_is_detected(cipher, where):
    sealed = cipher.seal(b"sensitive bytes", purpose="artifact", object_id="obj")
    blob, wrapped = bytearray(sealed.blob), bytearray(sealed.wrapped_key)
    if where == "blob_body":
        blob[20] ^= 1
    elif where == "blob_nonce":
        blob[5] ^= 1
    elif where == "blob_tag":
        blob[-1] ^= 1
    else:
        wrapped[-1] ^= 1
    with pytest.raises(DecryptionError):
        cipher.open(bytes(blob), bytes(wrapped), purpose="artifact", object_id="obj")


def test_ciphertext_bound_to_object_identity(cipher):
    sealed = cipher.seal(b"data", purpose="artifact", object_id="a")
    with pytest.raises(DecryptionError):
        cipher.open(sealed.blob, sealed.wrapped_key, purpose="artifact", object_id="b")
    with pytest.raises(DecryptionError):
        cipher.open(sealed.blob, sealed.wrapped_key, purpose="original", object_id="a")


def test_wrong_master_key_fails(cipher):
    sealed = cipher.seal(b"data", purpose="artifact", object_id="a")
    other = EnvelopeCipher(os.urandom(32))
    with pytest.raises(DecryptionError):
        other.open(sealed.blob, sealed.wrapped_key, purpose="artifact", object_id="a")


def test_low_level_rejects_bad_inputs():
    with pytest.raises(ValueError):
        encrypt(b"x", b"short", b"")
    with pytest.raises(DecryptionError):
        decrypt(b"tiny", os.urandom(32), b"")


def test_text_sealing(cipher):
    t = cipher.seal_text("passport-scan.jpg", purpose="name", object_id="s")
    assert b"passport" not in t
    assert cipher.open_text(t, purpose="name", object_id="s") == "passport-scan.jpg"


def test_tokens():
    t = new_token()
    assert looks_like_token(t) and len(t) == 43
    assert new_token() != t
    h = hash_token(t)
    assert len(h) == 64 and t not in h
    assert verify_token(t, h)
    assert not verify_token(t[:-1] + ("A" if t[-1] != "A" else "B"), h)
    assert not verify_token(None, h)
    assert not verify_token("../../etc/passwd", h)


def test_master_key_validation():
    from app.config import Settings

    with pytest.raises(RuntimeError):
        Settings(master_key="").master_key_bytes()
    with pytest.raises(RuntimeError):
        Settings(master_key="c2hvcnQ").master_key_bytes()
