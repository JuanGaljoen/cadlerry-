"""RNG-15 AC3 — decomposed build123d geometry modules (RED).

RED until `ringcad.geometry` exists. Pins the public surface the implementer
promotes from the RNG-13 spike (`spikes/rng13/b123d_solitaire.py`) into the
package: a `build_solitaire(spec)` composer that fuses three positive-volume
module solids — `shank()`, `prong_setting()`, `seat()` — driven by a RingSpec,
plus `to_stl_bytes` / `to_step_bytes` exporters.

Covers AC3 (decomposed, not monolithic) and AC4 (clean STL + STEP export).
The volume target (389.56 mm^3 ±5%) is the spike's measured build123d output
for the canonical params; the implementer must land within that band.
"""
from io import BytesIO

import pytest
import trimesh

from ringcad.geometry import (
    build_solitaire,
    prong_setting,
    seat,
    shank,
    to_step_bytes,
    to_stl_bytes,
)
from ringcad.ringspec import from_params

# Canonical solitaire — the contract's worked example (RNG-14 GOOD_PARAMS).
CANONICAL_PARAMS = {
    "inner_diameter": 16.5,
    "band_width": 2.2,
    "band_thickness": 1.9,
    "stone_diameter": 6.5,
    "stone_height": 4.0,
    "prong_count": 6,
    "setting_height": 6.0,
}

# Spike-measured build123d volume for CANONICAL_PARAMS (FINDINGS / mission brief).
EXPECTED_VOLUME_MM3 = 389.56
VOLUME_TOL = 0.05  # ±5%, the RNG-13 parity tolerance


@pytest.fixture
def spec():
    return from_params(CANONICAL_PARAMS)


# --- AC3: composed solitaire is one positive-volume solid --------------------
def test_build_solitaire_has_positive_volume(spec):
    solid = build_solitaire(spec)
    assert solid.volume > 0


def test_build_solitaire_volume_matches_spike(spec):
    vol = build_solitaire(spec).volume
    lo = EXPECTED_VOLUME_MM3 * (1 - VOLUME_TOL)
    hi = EXPECTED_VOLUME_MM3 * (1 + VOLUME_TOL)
    assert lo <= vol <= hi, f"volume {vol:.2f} outside ±5% of {EXPECTED_VOLUME_MM3}"


# --- AC3: each module is a discrete, positive-volume solid -------------------
def test_shank_has_positive_volume(spec):
    assert shank(spec).volume > 0


def test_prong_setting_has_positive_volume(spec):
    assert prong_setting(spec).volume > 0


def test_seat_has_positive_volume(spec):
    assert seat(spec).volume > 0


# --- AC4: STL export is loadable, non-empty mesh -----------------------------
def test_to_stl_bytes_is_loadable_mesh(spec):
    data = to_stl_bytes(build_solitaire(spec))
    assert isinstance(data, bytes)
    assert len(data) > 0
    mesh = trimesh.load(BytesIO(data), file_type="stl", force="mesh")
    assert len(mesh.faces) > 0


# --- AC4: STEP export is non-empty and ISO-10303 -----------------------------
def test_to_step_bytes_is_iso_10303(spec):
    data = to_step_bytes(build_solitaire(spec))
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert b"ISO-10303" in data[:512]
