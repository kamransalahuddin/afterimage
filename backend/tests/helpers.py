from __future__ import annotations

from tests.fixtures import synthetic as fx


def analyze(client, data: bytes | None = None, name: str = "shot.png", mime: str = "image/png"):
    data = data if data is not None else fx.text_image([f"Email: {fx.FAKE_EMAIL}", f"Card: {fx.FAKE_CARD}"])
    return client.post("/api/files/analyze", files={"file": (name, data, mime)})


def analyzed(client, **kw) -> dict:
    r = analyze(client, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def redacted(client, **kw) -> tuple[dict, dict]:
    a = analyzed(client, **kw)
    r = client.post(
        "/api/files/redact",
        json={"session_id": a["session_id"], "detection_ids": [d["id"] for d in a["detections"] if d["suggested"]]},
        headers={"X-Session-Token": a["session_token"]},
    )
    assert r.status_code == 201, r.text
    return a, r.json()


def shared(client, expires_in="24h", max_downloads=None) -> tuple[dict, dict, dict]:
    a, art = redacted(client)
    r = client.post(
        "/api/shares",
        json={"artifact_id": art["artifact_id"], "expires_in": expires_in, "max_downloads": max_downloads},
        headers={"X-Session-Token": a["session_token"]},
    )
    assert r.status_code == 201, r.text
    return a, art, r.json()
