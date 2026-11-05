"""Upload validation, session authorization, path handling and the redact flow."""

from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image

from app.services.storage import BlobStore, StorageError
from tests.fixtures import synthetic as fx
from tests.helpers import analyze, analyzed, redacted


def test_analyze_returns_detections_and_no_raw_text(client, db):
    body = analyzed(client)
    cats = {d["category"] for d in body["detections"]}
    assert {"email", "card"} <= cats
    assert body["session_token"] and len(body["session_token"]) == 43
    # API response carries masked previews only.
    assert fx.FAKE_EMAIL not in str(body) and "4242 4242" not in str(body)

    # Nothing sensitive or token-shaped is stored in the database.
    from sqlalchemy import text

    dump = " ".join(str(row) for t in ("processing_sessions", "detections", "audit_events")
                    for row in db.execute(text(f"SELECT * FROM {t}")))
    assert fx.FAKE_EMAIL not in dump and "4242 4242" not in dump
    assert body["session_token"] not in dump
    assert "shot" not in dump  # filename is encrypted


def test_original_is_encrypted_at_rest(client, svc):
    analyzed(client)
    keys = svc.store.keys("originals")
    assert len(keys) == 1
    blob = (svc.store.root / "originals" / f"{keys[0]}.bin").read_bytes()
    assert not blob.startswith(b"\x89PNG") and b"IHDR" not in blob


@pytest.mark.parametrize("data,code", [
    (b"", "empty_file"),
    (b"this is not an image", "unsupported_type"),
    (b"MZ\x90\x00" + b"\x00" * 100, "unsupported_type"),              # Windows executable
    (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "unsupported_type"),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "malformed_file"),          # truncated PNG
    (b"%PDF-1.7\n garbage", "malformed_file"),
])
def test_invalid_uploads_rejected(client, data, code):
    r = analyze(client, data=data, name="file.png")
    assert r.status_code in (400, 415)
    assert r.json()["error"]["code"] == code


def test_extension_is_not_trusted(client):
    # A real PDF uploaded with a .png name is treated as a PDF; an HTML file named .pdf is rejected.
    ok = analyze(client, data=fx.sample_pdf(), name="photo.png", mime="image/png")
    assert ok.status_code == 201 and ok.json()["kind"] == "pdf"
    bad = analyze(client, data=b"<html><script>alert(1)</script></html>", name="doc.pdf", mime="application/pdf")
    assert bad.status_code == 415


def test_oversized_file_rejected(client, settings):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (settings.max_upload_bytes + 10)
    r = analyze(client, data=big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_decompression_bomb_rejected(client):
    img = Image.new("1", (12_000, 12_000))  # within side limit but > 40 MP
    buf = io.BytesIO()
    img.save(buf, "PNG")
    r = analyze(client, data=buf.getvalue())
    assert r.status_code == 400 and r.json()["error"]["code"] in ("image_too_large", "image_dimensions")


def test_encrypted_pdf_rejected(client):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    r = analyze(client, data=data, name="x.pdf", mime="application/pdf")
    assert r.json()["error"]["code"] == "encrypted_pdf"


def test_too_many_pages_rejected(client, settings):
    doc = pymupdf.open()
    for _ in range(settings.max_pdf_pages + 1):
        doc.new_page()
    r = analyze(client, data=doc.tobytes(), name="x.pdf", mime="application/pdf")
    assert r.json()["error"]["code"] == "too_many_pages"


def test_preview_requires_session_token(client):
    a = analyzed(client)
    url = f"/api/files/{a['session_id']}/pages/0/preview"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"X-Session-Token": "A" * 43}).status_code == 401
    r = client.get(url, headers={"X-Session-Token": a["session_token"]})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_session_token_cannot_access_other_session(client):
    a = analyzed(client)
    b = analyzed(client)
    r = client.get(f"/api/files/{a['session_id']}/pages/0/preview", headers={"X-Session-Token": b["session_token"]})
    assert r.status_code == 401


def test_redact_rejects_foreign_detection_ids(client):
    a = analyzed(client)
    b = analyzed(client)
    r = client.post("/api/files/redact", json={"session_id": a["session_id"], "detection_ids": [b["detections"][0]["id"]]},
                    headers={"X-Session-Token": a["session_token"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_detection"


def test_redact_rejects_bad_regions(client):
    a = analyzed(client)
    for region in ({"page": 0, "x": 1.5, "y": 0, "w": 0.1, "h": 0.1}, {"page": 0, "x": 0, "y": 0, "w": 0, "h": 0.1},
                   {"page": 3, "x": 0, "y": 0, "w": 0.1, "h": 0.1}):
        r = client.post("/api/files/redact", json={"session_id": a["session_id"], "manual_regions": [region]},
                        headers={"X-Session-Token": a["session_token"]})
        assert r.status_code == 422, region


def test_redact_flow_deletes_original_and_produces_clean_artifact(client, svc):
    a, art = redacted(client)
    assert svc.store.keys("originals") == []  # original destroyed after processing
    assert art["filename"] == "shot-redacted.png"

    # Original is gone: preview of the original now fails.
    r = client.get(f"/api/files/{a['session_id']}/pages/0/preview", headers={"X-Session-Token": a["session_token"]})
    assert r.status_code == 409

    dl = client.get(f"/api/artifacts/{art['artifact_id']}/download", headers={"X-Session-Token": a["session_token"]})
    assert dl.status_code == 200
    assert dl.headers["content-disposition"].startswith("attachment;")
    assert dl.headers["x-content-type-options"] == "nosniff"
    assert Image.open(io.BytesIO(dl.content)).format == "PNG"


def test_manual_region_redaction(client):
    a = analyzed(client)
    r = client.post("/api/files/redact",
                    json={"session_id": a["session_id"], "manual_regions": [{"page": 0, "x": 0, "y": 0, "w": 0.5, "h": 0.5}]},
                    headers={"X-Session-Token": a["session_token"]})
    assert r.status_code == 201 and r.json()["regions"] == 1


def test_pdf_flow_text_not_extractable(client):
    a = analyzed(client, data=fx.sample_pdf(), name="record.pdf", mime="application/pdf")
    ids = [d["id"] for d in a["detections"] if d["suggested"]]
    r = client.post("/api/files/redact", json={"session_id": a["session_id"], "detection_ids": ids},
                    headers={"X-Session-Token": a["session_token"]})
    assert r.status_code == 201, r.text
    dl = client.get(f"/api/artifacts/{r.json()['artifact_id']}/download", headers={"X-Session-Token": a["session_token"]})
    doc = pymupdf.open(stream=dl.content, filetype="pdf")
    text = "".join(p.get_text() for p in doc)
    for s in (fx.FAKE_EMAIL, fx.FAKE_CARD, fx.FAKE_SSN, fx.FAKE_AWS_KEY):
        assert s not in text
    assert not doc.metadata.get("author")


@pytest.mark.parametrize("path", [
    "/api/files/..%2F..%2Fetc%2Fpasswd/pages/0/preview",
    "/api/files/../../etc/passwd/pages/0/preview",
    "/api/artifacts/..%2F..%2F.env/download",
    "/api/artifacts/%2e%2e%2f%2e%2e%2fetc%2fpasswd/download",
    "/api/shares/..%2F..%2F..%2Fetc%2Fpasswd",
])
def test_path_traversal_rejected(client, path):
    r = client.get(path, headers={"X-Session-Token": "A" * 43})
    assert r.status_code in (404, 422)
    assert b"root:" not in r.content


def test_storage_rejects_untrusted_keys(tmp_path):
    store = BlobStore(tmp_path)
    for key in ("../../etc/passwd", "a" * 31, "A" * 32, "../" + "a" * 29, "a" * 32 + "/../x"):
        with pytest.raises(StorageError):
            store.read("artifacts", key)
    with pytest.raises(StorageError):
        store.read("../originals", "a" * 32)


def test_structured_errors(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post("/api/files/redact", json={"session_id": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_rate_limit_on_auth_failures(client):
    a = analyzed(client)
    url = f"/api/files/{a['session_id']}/pages/0/preview"
    codes = [client.get(url, headers={"X-Session-Token": "B" * 43}).status_code for _ in range(25)]
    assert 429 in codes
    # Once locked out, even the right token is refused for a while.
    assert client.get(url, headers={"X-Session-Token": a["session_token"]}).status_code == 429


def test_faces_detector_runs_on_blank_image():
    from app.detection.faces import backend_name, detect_faces

    assert backend_name() in ("yunet", "haar")
    assert detect_faces(Image.new("RGB", (640, 480), "white")) == []
