import base64
import os

import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "url",
    ["postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"],
)
def test_database_url_uses_psycopg_driver(url):
    assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@h:5432/db"


@pytest.mark.parametrize("encode", [base64.urlsafe_b64encode, base64.b64encode])
def test_master_key_accepts_urlsafe_and_standard_base64(encode):
    # Force bytes that encode to '+' / '/' (standard) or '-' / '_' (urlsafe).
    raw = bytes([0xFB, 0xFF, 0xBF] * 10 + [0xFB, 0xFF])
    assert len(raw) == 32
    assert Settings(master_key=encode(raw).decode()).master_key_bytes() == raw


def test_master_key_wrong_length_rejected():
    with pytest.raises(RuntimeError):
        Settings(master_key=base64.b64encode(os.urandom(16)).decode()).master_key_bytes()
