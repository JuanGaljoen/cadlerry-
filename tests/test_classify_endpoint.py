"""Endpoint tests for POST /classify-ring (RNG-6).

TDD RED: these tests FAIL today because the route does not exist (404/405) and
because ringcad.app does not yet import classify_available / classify_ring.

TEST SEAM: like ringcad.app's render_scad seam, the endpoint binds
`from ringcad.classify import classify_available, classify_ring` into the
ringcad.app namespace, so we monkeypatch `ringcad.app.classify_available` /
`ringcad.app.classify_ring` (where they are LOOKED UP) -- NOT ringcad.classify.*.
NO network / NO API key is ever used. Multipart uploads go through the Flask
test client; magic bytes drive the byte-sniff (real JPEG header for valid, GIF
for wrong type).
"""
import io

import pytest

from ringcad.app import create_app

JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 64
GIF_MAGIC = b"GIF89a" + b"\x00" * 64


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _classify_result(**overrides):
    """Lightweight ClassifyResult stand-in for the classify_ring seam. The
    endpoint only needs .ok, .ring_detected and .to_json(); this avoids
    depending on ringcad.classify (which may not exist yet)."""
    data = dict(
        ok=True, ring_detected=True, style="solitaire", prong_count=6,
        shank_taper="straight", features=["polished"],
        estimates={"band_width": 2.2, "prong_count": 6}, note="rough",
    )
    data.update(overrides)
    body = {k: data[k] for k in (
        "ring_detected", "style", "prong_count", "shank_taper",
        "features", "estimates", "note",
    )}
    return type("FakeResult", (), {
        "ok": data["ok"],
        "ring_detected": data["ring_detected"],
        "to_json": lambda self, _b=body: dict(_b),
    })()


def _upload(client, magic=JPEG_MAGIC, filename="ring.jpg"):
    return client.post(
        "/classify-ring",
        data={"image": (io.BytesIO(magic), filename)},
        content_type="multipart/form-data",
    )


def _set_classify(monkeypatch, *, available=True, result=None):
    monkeypatch.setattr("ringcad.app.classify_available", lambda: available)
    if result is not None:
        monkeypatch.setattr("ringcad.app.classify_ring",
                            lambda *a, **k: result)


# ---- AC8: no API key -> 503 JSON; /health unaffected ----------------------
def test_classify_no_key_returns_503(client, monkeypatch):
    _set_classify(monkeypatch, available=False)
    resp = _upload(client)
    assert resp.status_code == 503
    assert "error" in resp.get_json()
    health = client.get("/health")
    assert health.status_code == 200
    assert health.get_json() == {"status": "ok"}


# ---- AC2/AC3/AC4: success -> 200 with full classification body -------------
def test_classify_success_returns_200_with_body(client, monkeypatch):
    _set_classify(monkeypatch, available=True,
                  result=_classify_result(ring_detected=True))
    resp = _upload(client)
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ("style", "prong_count", "shank_taper",
                "features", "estimates", "note"):
        assert key in data, f"response missing {key}"
    assert data["ring_detected"] is True


# ---- AC7: not-a-ring -> 200, ring_detected false --------------------------
def test_classify_not_a_ring_returns_200_false(client, monkeypatch):
    _set_classify(monkeypatch, available=True,
                  result=_classify_result(ring_detected=False, estimates={}))
    resp = _upload(client)
    assert resp.status_code == 200
    assert resp.get_json()["ring_detected"] is False


# ---- AC10: classifier failure (ok=False) -> 502, never 500 ----------------
def test_classify_service_failure_returns_502(client, monkeypatch):
    _set_classify(monkeypatch, available=True,
                  result=_classify_result(ok=False))
    resp = _upload(client)
    assert resp.status_code == 502
    assert "error" in resp.get_json()


# ---- AC1: missing image field -> 400 --------------------------------------
def test_classify_missing_image_returns_400(client, monkeypatch):
    _set_classify(monkeypatch, available=True)
    resp = client.post("/classify-ring", data={},
                       content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


# ---- AC1: wrong magic bytes (GIF) -> 400 ----------------------------------
def test_classify_wrong_magic_bytes_returns_400(client, monkeypatch):
    _set_classify(monkeypatch, available=True)
    resp = _upload(client, magic=GIF_MAGIC, filename="ring.gif")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


# ---- AC10: oversized (>8MB) -> 400, NOT 413 -------------------------------
def test_classify_oversized_returns_400_not_413(client, monkeypatch):
    _set_classify(monkeypatch, available=True)
    big = JPEG_MAGIC + b"\x00" * (8 * 1024 * 1024 + 1)
    resp = _upload(client, magic=big)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


# ---- empty file -> 400 ----------------------------------------------------
def test_classify_empty_file_returns_400(client, monkeypatch):
    _set_classify(monkeypatch, available=True)
    resp = _upload(client, magic=b"")
    assert resp.status_code == 400
    assert "error" in resp.get_json()
