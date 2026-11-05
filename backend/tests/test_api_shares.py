"""Secure sharing: expiry, revocation, download limits, concurrency, audit, logging."""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.db import session_factory
from app.models.orm import Artifact, AuditEvent, Share, utcnow
from app.services.cleanup import purge_expired
from app.sharing import service as shares
from app.sharing.service import ShareUnavailable
from tests.helpers import redacted, shared


def _token(share: dict) -> str:
    return share["token"]


def test_share_link_uses_fragment_and_hash_only_storage(client, db):
    _, _, s = shared(client)
    assert "/s#" in s["url"] and s["url"].endswith(s["token"])
    row = db.get(Share, s["id"])
    assert row.token_hash != s["token"] and len(row.token_hash) == 64
    assert row.manage_token_hash != s["manage_token"]


def test_share_info_does_not_consume_downloads(client):
    _, _, s = shared(client, max_downloads=1)
    for _ in range(3):
        r = client.get(f"/api/shares/{_token(s)}")
        assert r.status_code == 200
        assert r.json()["downloads_remaining"] == 1
    assert client.post(f"/api/shares/{_token(s)}/download").status_code == 200


def test_download_returns_sanitized_artifact_not_original(client):
    a, art, s = shared(client)
    r = client.post(f"/api/shares/{_token(s)}/download")
    assert r.status_code == 200
    import hashlib

    assert hashlib.sha256(r.content).hexdigest() == art["sha256"]
    owner = client.get(f"/api/artifacts/{art['artifact_id']}/download", headers={"X-Session-Token": a["session_token"]})
    assert owner.content == r.content


def test_share_creation_requires_owner_token(client):
    a, art = redacted(client)
    other, _ = redacted(client)
    for headers in ({}, {"X-Session-Token": other["session_token"]}, {"X-Session-Token": "x"}):
        r = client.post("/api/shares", json={"artifact_id": art["artifact_id"]}, headers=headers)
        assert r.status_code == 401


def test_unknown_token_is_404(client):
    assert client.get("/api/shares/" + "A" * 43).status_code == 404
    assert client.post("/api/shares/" + "A" * 43 + "/download").status_code == 404
    assert client.get("/api/shares/short").status_code == 422


def test_expired_link_denied(client, db):
    _, _, s = shared(client, expires_in="1h")
    db.execute(update(Share).where(Share.id == s["id"]).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    r = client.post(f"/api/shares/{_token(s)}/download")
    assert r.status_code == 410 and r.json()["error"]["code"] == "share_expired"
    assert client.get(f"/api/shares/{_token(s)}").status_code == 410


def test_revoked_link_denied(client):
    _, _, s = shared(client)
    r = client.delete(f"/api/shares/{s['id']}", headers={"Authorization": f"Bearer {s['manage_token']}"})
    assert r.status_code == 204
    r = client.post(f"/api/shares/{_token(s)}/download")
    assert r.status_code == 410 and r.json()["error"]["code"] == "share_revoked"


def test_revocation_requires_manage_token(client):
    _, _, s = shared(client)
    _, _, other = shared(client)
    for headers in ({}, {"Authorization": f"Bearer {s['token']}"},  # the download token is NOT a revoke token
                    {"Authorization": f"Bearer {other['manage_token']}"}):
        assert client.delete(f"/api/shares/{s['id']}", headers=headers).status_code == 401
    assert client.post(f"/api/shares/{_token(s)}/download").status_code == 200


def test_max_downloads_enforced(client):
    _, _, s = shared(client, max_downloads=5)
    codes = [client.post(f"/api/shares/{_token(s)}/download").status_code for _ in range(7)]
    assert codes == [200] * 5 + [410, 410]
    status = client.get(f"/api/shares/{s['id']}/status", headers={"Authorization": f"Bearer {s['manage_token']}"})
    assert status.json()["download_count"] == 5


@pytest.mark.parametrize("limit", [1, 5])
def test_concurrent_downloads_cannot_exceed_limit(client, limit):
    _, _, s = shared(client, max_downloads=limit)
    token = _token(s)
    n = 24
    barrier = threading.Barrier(n)
    results: list[str] = []
    lock = threading.Lock()

    def worker():
        db = session_factory()()
        try:
            barrier.wait()
            try:
                shares.consume(db, token)
                db.commit()
                outcome = "ok"
            except ShareUnavailable as exc:
                outcome = exc.reason
        finally:
            db.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == limit
    assert results.count("download_limit") == n - limit
    with session_factory()() as db:
        assert db.get(Share, s["id"]).download_count == limit


def test_unlimited_link(client):
    _, _, s = shared(client, max_downloads=None)
    assert all(client.post(f"/api/shares/{_token(s)}/download").status_code == 200 for _ in range(8))


def test_invalid_share_options_rejected(client):
    a, art = redacted(client)
    for body in ({"artifact_id": art["artifact_id"], "expires_in": "30d"},
                 {"artifact_id": art["artifact_id"], "max_downloads": 1000},
                 {"artifact_id": art["artifact_id"], "extra": True}):
        r = client.post("/api/shares", json=body, headers={"X-Session-Token": a["session_token"]})
        assert r.status_code == 422


def test_artifact_lifetime_extends_to_share(client, db):
    _, art, s = shared(client, expires_in="7d")
    a = db.get(Artifact, art["artifact_id"])
    assert abs((a.expires_at - db.get(Share, s["id"]).expires_at).total_seconds()) < 1


def test_audit_trail(client, db):
    _, _, s = shared(client, max_downloads=1)
    client.post(f"/api/shares/{_token(s)}/download")
    client.post(f"/api/shares/{_token(s)}/download")
    client.delete(f"/api/shares/{s['id']}", headers={"Authorization": "Bearer " + "Z" * 43})
    client.delete(f"/api/shares/{s['id']}", headers={"Authorization": f"Bearer {s['manage_token']}"})
    events = [e.event_type for e in db.scalars(select(AuditEvent).order_by(AuditEvent.id))]
    for expected in ("file.analyzed", "redaction.completed", "share.created", "share.downloaded",
                     "share.denied.download_limit", "auth.failed", "share.revoked"):
        assert expected in events, events
    actors = {e.actor for e in db.scalars(select(AuditEvent))}
    assert "testclient" not in actors  # IPs are pseudonymised
    dump = " ".join(str(e.details) for e in db.scalars(select(AuditEvent)))
    assert s["token"] not in dump and s["manage_token"] not in dump


def test_tokens_never_logged(client, caplog):
    caplog.set_level(logging.INFO)
    _, _, s = shared(client)
    client.get(f"/api/shares/{_token(s)}")
    client.post(f"/api/shares/{_token(s)}/download")
    client.get("/api/shares/" + "Q" * 43)
    access = [r.getMessage() for r in caplog.records if r.name == "afterimage.access"]
    assert any("/api/shares/[redacted]" in m for m in access)
    assert all(s["token"] not in m and "Q" * 43 not in m for m in access)


def test_scrub_filter():
    from app.main import ScrubFilter

    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "GET %s", ("/api/shares/" + "a" * 43,), None)
    ScrubFilter().filter(rec)
    assert "a" * 43 not in rec.getMessage()


def test_cleanup_deletes_expired_artifacts(client, db, svc):
    _, art, s = shared(client)
    db.execute(update(Artifact).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    counts = purge_expired(db, svc)
    assert counts["artifacts"] == 1
    assert svc.store.keys("artifacts") == []
    assert db.get(Share, s["id"]) is None
    assert client.post(f"/api/shares/{_token(s)}/download").status_code == 404


def test_cleanup_deletes_expired_sessions_and_originals(client, db, svc):
    from app.models.orm import ProcessingSession
    from tests.helpers import analyzed

    a = analyzed(client)
    assert len(svc.store.keys("originals")) == 1
    db.execute(update(ProcessingSession).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    counts = purge_expired(db, svc)
    assert counts == {"sessions": 1, "artifacts": 0, "originals": 1}
    assert svc.store.keys("originals") == []
    r = client.get(f"/api/files/{a['session_id']}/pages/0/preview", headers={"X-Session-Token": a["session_token"]})
    assert r.status_code == 401


def test_admin_audit_endpoint(client, settings):
    shared(client)
    assert client.get("/api/admin/audit").status_code == 401
    r = client.get("/api/admin/audit", headers={"Authorization": f"Bearer {settings.admin_token}"})
    assert r.status_code == 200 and len(r.json()) >= 3
