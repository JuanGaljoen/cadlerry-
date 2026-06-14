"""Backend tests for the Flask STL generation endpoint (RNG-2).

TDD RED: these tests define behavior in ringcad.app / ringcad.params that does
not exist yet. They MUST fail at collection (ModuleNotFoundError on ringcad.app)
until the implementer lands those modules.

TEST SEAM (critical): ringcad.app does `from ringcad.render import render_scad,
openscad_available`, binding those names into the ringcad.app namespace. So we
monkeypatch `ringcad.app.render_scad` / `ringcad.app.openscad_available` (where
they are LOOKED UP) — NOT `ringcad.render.*`. Patching the source module would
silently not take effect because app holds its own reference.
"""
import subprocess
from pathlib import Path

import pytest

# Imported only for the per-test skipif on real-render tests. This import is
# safe (ringcad.render already exists); the RED failure comes from ringcad.app.
from ringcad.render import RenderResult, openscad_available
from ringcad.app import create_app

VALID_BODY = {
    "inner_diameter": 16.5,
    "band_width": 2.2,
    "band_thickness": 1.9,
    "stone_diameter": 6.5,
    "stone_height": 4,
    "prong_count": 6,
    "setting_height": 6,
}

requires_openscad = pytest.mark.skipif(
    not openscad_available(), reason="openscad not on PATH"
)


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _failing_result() -> RenderResult:
    return RenderResult(
        returncode=1, stdout="", stderr="boom",
        stl_path=Path("x"), seconds=0.1, size_bytes=0,
    )


def _spy(monkeypatch):
    """Patch the app's render_scad seam with a spy that records its kwargs and
    writes a tiny STL so the success path returns a body. Also forces
    openscad_available -> True so the 503 pre-check passes."""
    calls = {}

    def fake_render(scad_path, stl_path, params=None, fn=None, timeout=None):
        calls["scad_path"] = scad_path
        calls["params"] = params
        calls["fn"] = fn
        calls["timeout"] = timeout
        Path(stl_path).write_bytes(b"solid x\nendsolid x\n")
        return RenderResult(
            returncode=0, stdout="", stderr="",
            stl_path=Path(stl_path), seconds=0.1, size_bytes=20,
        )

    monkeypatch.setattr("ringcad.app.render_scad", fake_render)
    monkeypatch.setattr("ringcad.app.openscad_available", lambda: True)
    return calls


# ---- AC1: accepts all 7 params; prong_count coerced to int -----------------
def test_generate_ring_accepts_all_seven_params(client, monkeypatch):
    calls = _spy(monkeypatch)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    params = calls["params"]
    for key in VALID_BODY:
        assert key in params
    assert isinstance(params["prong_count"], int)
    assert not isinstance(params["prong_count"], bool)
    assert params["prong_count"] == 6


# ---- AC2: renders via scad/solitaire.scad with default fn ------------------
def test_render_called_with_scad_path_and_fn(client, monkeypatch):
    calls = _spy(monkeypatch)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    scad = Path(calls["scad_path"])
    assert scad.name == "solitaire.scad"
    assert scad.parent.name == "scad"
    assert calls["fn"] == 24


@requires_openscad
def test_render_called_with_real_openscad_produces_stl(client):
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200, resp.data
    assert len(resp.data) > 1024


# ---- AC3: returns binary STL on success ------------------------------------
@requires_openscad
def test_generate_ring_returns_binary_stl(client):
    import io
    import trimesh

    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "model/stl"
    assert resp.headers["Content-Disposition"] == 'attachment; filename="ring.stl"'
    mesh = trimesh.load(io.BytesIO(resp.data), file_type="stl")
    assert mesh.vertices.shape[0] > 0


# ---- AC4: render failure -> 400 JSON with openscad_stderr ------------------
def test_render_failure_returns_400_with_stderr(client, monkeypatch):
    monkeypatch.setattr("ringcad.app.render_scad",
                        lambda *a, **k: _failing_result())
    monkeypatch.setattr("ringcad.app.openscad_available", lambda: True)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert data["openscad_stderr"] == "boom"


# ---- AC5: GET /health -> 200 exact body ------------------------------------
def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


# ---- AC6: validation matrix — each -> 400 JSON, never 500/traceback --------
def test_missing_param_400(client):
    body = {k: v for k, v in VALID_BODY.items() if k != "stone_diameter"}
    resp = client.post("/generate-ring", json=body)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert data.get("field") == "stone_diameter"


def test_non_numeric_param_400(client):
    body = {**VALID_BODY, "band_width": "wide"}
    resp = client.post("/generate-ring", json=body)
    assert resp.status_code == 400
    assert resp.get_json().get("field") == "band_width"


def test_null_param_400(client):
    body = {**VALID_BODY, "stone_height": None}
    resp = client.post("/generate-ring", json=body)
    assert resp.status_code == 400
    assert resp.get_json().get("field") == "stone_height"


def test_bool_param_rejected_400(client):
    body = {**VALID_BODY, "band_thickness": True}
    resp = client.post("/generate-ring", json=body)
    assert resp.status_code == 400
    assert resp.get_json().get("field") == "band_thickness"


def test_unknown_key_rejected_400(client):
    body = {**VALID_BODY, "evil": "; rm -rf /"}
    resp = client.post("/generate-ring", json=body)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert "evil" in (data.get("detail", "") + str(data.get("field", "")))


def test_empty_body_400(client):
    resp = client.post("/generate-ring", json={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_non_json_content_type_400(client):
    resp = client.post("/generate-ring", data="inner_diameter=16.5",
                       content_type="text/plain")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_json_array_body_400(client):
    resp = client.post("/generate-ring", json=[1, 2, 3])
    assert resp.status_code == 400
    assert "error" in resp.get_json()


# ---- AC7: render timeout -> 400 JSON ---------------------------------------
def test_render_timeout_returns_400(client, monkeypatch):
    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(["openscad"], 120)

    monkeypatch.setattr("ringcad.app.render_scad", raise_timeout)
    monkeypatch.setattr("ringcad.app.openscad_available", lambda: True)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert "time" in (data["error"] + data.get("detail", "")).lower()


# ---- AC8: OpenSCAD unavailable -> 503; /health still 200 -------------------
def test_openscad_unavailable_returns_503(client, monkeypatch):
    monkeypatch.setattr("ringcad.app.openscad_available", lambda: False)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 503
    assert "error" in resp.get_json()
    # /health must NOT depend on openscad availability.
    health = client.get("/health")
    assert health.status_code == 200
    assert health.get_json() == {"status": "ok"}


# ---- Edge: prong_count=5 still renders (SCAD snaps + warns) -----------------
@requires_openscad
def test_prong_count_five_accepted_and_renders(client):
    body = {**VALID_BODY, "prong_count": 5}
    resp = client.post("/generate-ring", json=body)
    assert resp.status_code == 200
    assert len(resp.data) > 1024


# ---- Env override: RENDER_FN respected (default is 24) ---------------------
def test_render_fn_env_override(client, monkeypatch):
    monkeypatch.setenv("RENDER_FN", "48")
    calls = _spy(monkeypatch)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    assert calls["fn"] == 48


# ===========================================================================
# RNG-5: mesh validation/repair headers on /generate-ring
#
# These reuse the established render seam (ringcad.app.render_scad /
# ringcad.app.openscad_available) but write CRAFTED STL bytes into stl_path so
# the real validate_and_repair runs on a known mesh shape — no mocking of
# trimesh. They FAIL today because the endpoint emits no X-Mesh-* headers yet.
# ===========================================================================
import io  # noqa: E402

import trimesh  # noqa: E402


def _spy_writing(monkeypatch, stl_bytes: bytes):
    """Like _spy, but writes the supplied STL bytes into stl_path so the
    endpoint's validate_and_repair sees a mesh of our choosing."""

    def fake_render(scad_path, stl_path, params=None, fn=None, timeout=None):
        Path(stl_path).write_bytes(stl_bytes)
        return RenderResult(
            returncode=0, stdout="", stderr="",
            stl_path=Path(stl_path), seconds=0.1, size_bytes=len(stl_bytes),
        )

    monkeypatch.setattr("ringcad.app.render_scad", fake_render)
    monkeypatch.setattr("ringcad.app.openscad_available", lambda: True)


def _castable_stl() -> bytes:
    return trimesh.creation.box(extents=(3, 3, 3)).export(file_type="stl")


def _multibody_stl() -> bytes:
    a = trimesh.creation.box(extents=(1, 1, 1))
    b = trimesh.creation.box(extents=(1, 1, 1))
    b.apply_translation([5, 0, 0])
    return trimesh.util.concatenate([a, b]).export(file_type="stl")


# ---- AC1/AC3: castable mesh -> valid headers + RNG-2 contract preserved -----
def test_castable_stl_sets_valid_headers(client, monkeypatch):
    _spy_writing(monkeypatch, _castable_stl())
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    assert resp.headers["X-Mesh-Valid"] == "true"
    assert resp.headers["X-Mesh-Repaired"] == "false"
    # RNG-2 contract must survive byte-for-byte
    assert resp.headers["Content-Type"] == "model/stl"
    assert resp.headers["Content-Disposition"] == 'attachment; filename="ring.stl"'
    mesh = trimesh.load(io.BytesIO(resp.data), file_type="stl", force="mesh")
    assert len(mesh.faces) > 0


# ---- AC3/AC5: multi-body mesh -> repaired but still invalid, body returned --
def test_multibody_stl_sets_repaired_invalid_headers(client, monkeypatch):
    _spy_writing(monkeypatch, _multibody_stl())
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    assert resp.headers["X-Mesh-Repaired"] == "true"
    assert resp.headers["X-Mesh-Valid"] == "false"
    # AC5: download works regardless of validity -> a body is still returned
    assert len(resp.data) > 0


# ---- AC7/AC9: unloadable bytes -> raw passthrough, header-safe detail -------
def test_garbage_stl_passes_through_with_safe_headers(client, monkeypatch):
    garbage = b"not an stl at all, just bytes"
    _spy_writing(monkeypatch, garbage)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200  # AC7: endpoint never 500s on bad mesh
    assert resp.headers["X-Mesh-Valid"] == "false"
    assert resp.headers["X-Mesh-Repaired"] == "false"
    assert resp.data == garbage  # raw passthrough
    detail = resp.headers["X-Mesh-Repair-Detail"]
    assert detail.isascii()
    assert len(detail) <= 200


# ---- AC1/AC3: real default-ring render -> valid headers (OpenSCAD only) -----
@requires_openscad
def test_real_default_ring_sets_valid_headers(client):
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200, resp.data
    assert resp.headers["X-Mesh-Valid"] == "true"
    assert resp.headers["X-Mesh-Repaired"] == "false"
