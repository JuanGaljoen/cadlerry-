"""Backend tests for the Flask ring generation endpoint (RNG-2, RNG-15).

The endpoint now builds the solitaire in-process via build123d driven by
RingSpec — no OpenSCAD subprocess.

TEST SEAM (critical): ringcad.app does `from ringcad.geometry import
build_solitaire, to_stl_bytes, to_step_bytes`, binding those names into the
ringcad.app namespace. So we monkeypatch `ringcad.app.build_solitaire` /
`ringcad.app.to_stl_bytes` (where they are LOOKED UP) — NOT
`ringcad.geometry.*`. Patching the source module would silently not take effect
because app holds its own reference. Most endpoint tests stub the generator to
stay fast and deterministic; a couple of end-to-end tests run the real build.
"""
import io

import pytest
import trimesh

from ringcad.app import create_app
from ringcad.ringspec import to_params

VALID_BODY = {
    "inner_diameter": 16.5,
    "band_width": 2.2,
    "band_thickness": 1.9,
    "stone_diameter": 6.5,
    "stone_height": 4,
    "prong_count": 6,
    "setting_height": 6,
}


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


class _Sentinel:
    """Stand-in for a build123d solid returned by a stubbed generator."""


def _spy(monkeypatch):
    """Patch the generator seam with a spy that records the RingSpec it was
    handed and returns a tiny STL so the success path returns a body."""
    calls = {}

    def fake_build(spec):
        calls["spec"] = spec
        return _Sentinel()

    monkeypatch.setattr("ringcad.app.build_solitaire", fake_build)
    monkeypatch.setattr(
        "ringcad.app.to_stl_bytes", lambda solid: b"solid x\nendsolid x\n"
    )
    return calls


def _spy_writing(monkeypatch, stl_bytes: bytes):
    """Like _spy, but to_stl_bytes returns the supplied STL bytes so the
    endpoint's validate_and_repair sees a mesh of our choosing."""
    monkeypatch.setattr(
        "ringcad.app.build_solitaire", lambda spec: _Sentinel()
    )
    monkeypatch.setattr(
        "ringcad.app.to_stl_bytes", lambda solid: stl_bytes
    )


# ---- AC1: accepts all 7 params; prong_count coerced to int -----------------
def test_generate_ring_accepts_all_seven_params(client, monkeypatch):
    calls = _spy(monkeypatch)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    params = to_params(calls["spec"])
    for key in VALID_BODY:
        assert key in params
    assert isinstance(params["prong_count"], int)
    assert not isinstance(params["prong_count"], bool)
    assert params["prong_count"] == 6


# ---- AC1: success response shape (binary STL + RNG-2 contract) -------------
def test_generate_ring_returns_stl_contract(client, monkeypatch):
    _spy_writing(monkeypatch, _castable_stl())
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "model/stl"
    assert resp.headers["Content-Disposition"] == 'attachment; filename="ring.stl"'
    mesh = trimesh.load(io.BytesIO(resp.data), file_type="stl", force="mesh")
    assert mesh.vertices.shape[0] > 0


# ---- RNG-15 AC4: ?format=step -> STEP body --------------------------------
def test_format_step_returns_step_body(client):
    resp = client.post("/generate-ring?format=step", json=VALID_BODY)
    assert resp.status_code == 200, resp.data
    assert resp.headers["Content-Type"] == "model/step"
    assert resp.headers["Content-Disposition"] == 'attachment; filename="ring.step"'
    assert b"ISO-10303" in resp.data


# ---- RNG-15: unsupported format -> 400 ------------------------------------
def test_unsupported_format_returns_400(client, monkeypatch):
    _spy(monkeypatch)
    resp = client.post("/generate-ring?format=obj", json=VALID_BODY)
    assert resp.status_code == 400
    assert resp.get_json().get("field") == "format"


# ---- RNG-15 AC4: non-castable params rejected before geometry --------------
def test_non_castable_body_returns_400_with_violations(client):
    body = {**VALID_BODY, "band_thickness": 0.6}
    resp = client.post("/generate-ring", json=body)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "Not castable"
    assert data["field"] is not None and "band_thickness" in data["field"]
    assert any(
        "band_thickness" in (v.get("field") or "") for v in data["violations"]
    )


# ---- RNG-15: geometry failure -> 400 generic error (no subprocess stderr) --
def test_geometry_failure_returns_400_generic(client, monkeypatch):
    def boom(spec):
        raise RuntimeError("kernel exploded")

    monkeypatch.setattr("ringcad.app.build_solitaire", boom)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "Geometry generation failed"
    assert "openscad_stderr" not in data


# ---- AC5: GET /health -> 200 exact body ------------------------------------
def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


# ---- Validation matrix — each -> 400 JSON, never 500/traceback -------------
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


# ---- Edge: prong_count=5 now rejected at RingSpec schema (4 or 6 only) ------
def test_prong_count_five_rejected_400(client):
    body = {**VALID_BODY, "prong_count": 5}
    resp = client.post("/generate-ring", json=body)
    assert resp.status_code == 400
    assert resp.get_json().get("field") == "prong_count"


# ===========================================================================
# Mesh validation/repair headers on /generate-ring (RNG-5)
#
# These write CRAFTED STL bytes through the to_stl_bytes seam so the real
# validate_and_repair runs on a known mesh shape — no mocking of trimesh.
# ===========================================================================
def _castable_stl() -> bytes:
    return trimesh.creation.box(extents=(3, 3, 3)).export(file_type="stl")


def _multibody_stl() -> bytes:
    a = trimesh.creation.box(extents=(1, 1, 1))
    b = trimesh.creation.box(extents=(1, 1, 1))
    b.apply_translation([5, 0, 0])
    return trimesh.util.concatenate([a, b]).export(file_type="stl")


# ---- castable mesh -> valid headers + RNG-2 contract preserved -------------
def test_castable_stl_sets_valid_headers(client, monkeypatch):
    _spy_writing(monkeypatch, _castable_stl())
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    assert resp.headers["X-Mesh-Valid"] == "true"
    assert resp.headers["X-Mesh-Repaired"] == "false"
    assert resp.headers["Content-Type"] == "model/stl"
    assert resp.headers["Content-Disposition"] == 'attachment; filename="ring.stl"'
    mesh = trimesh.load(io.BytesIO(resp.data), file_type="stl", force="mesh")
    assert len(mesh.faces) > 0


# ---- multi-body mesh -> repaired but still invalid, body returned ----------
def test_multibody_stl_sets_repaired_invalid_headers(client, monkeypatch):
    _spy_writing(monkeypatch, _multibody_stl())
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200
    assert resp.headers["X-Mesh-Repaired"] == "true"
    assert resp.headers["X-Mesh-Valid"] == "false"
    assert len(resp.data) > 0


# ---- unloadable bytes -> raw passthrough, header-safe detail ---------------
def test_garbage_stl_passes_through_with_safe_headers(client, monkeypatch):
    garbage = b"not an stl at all, just bytes"
    _spy_writing(monkeypatch, garbage)
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200  # endpoint never 500s on bad mesh
    assert resp.headers["X-Mesh-Valid"] == "false"
    assert resp.headers["X-Mesh-Repaired"] == "false"
    assert resp.data == garbage  # raw passthrough
    detail = resp.headers["X-Mesh-Repair-Detail"]
    assert detail.isascii()
    assert len(detail) <= 200


# ===========================================================================
# End-to-end: the real build123d generator drives the endpoint (slower).
# ===========================================================================
def test_real_default_ring_produces_valid_stl(client):
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200, resp.data
    assert resp.headers["Content-Type"] == "model/stl"
    assert resp.headers["X-Mesh-Valid"] == "true"
    assert len(resp.data) > 1024
    mesh = trimesh.load(io.BytesIO(resp.data), file_type="stl", force="mesh")
    assert len(mesh.faces) > 0


# ---- RNG-17 AC3: real generation is watertight WITHOUT repair --------------
def test_real_default_ring_is_watertight_without_repair(client):
    """The canonical ring's raw geometry must already be a watertight manifold,
    so the endpoint marks it valid AND reports no repair was needed. FAILS now:
    the tangent claw joints leave open edges, so validate_and_repair welds them
    and X-Mesh-Repaired comes back 'true'."""
    resp = client.post("/generate-ring", json=VALID_BODY)
    assert resp.status_code == 200, resp.data
    assert resp.headers["X-Mesh-Valid"] == "true"
    assert resp.headers["X-Mesh-Repaired"] == "false"
