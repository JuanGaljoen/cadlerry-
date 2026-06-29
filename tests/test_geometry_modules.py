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


# === RNG-16 AC1: module registry conforms to the Module protocol =============
# Local imports so the RNG-15 tests above stay green; these RED until RNG-16's
# `ringcad.geometry.module` (Module protocol + MODULES registry) lands.
EXPECTED_MODULE_NAMES = {"shank", "seat", "prong_setting", "bezel"}


def test_expected_modules_registered():
    """Every foundation module is registered in MODULES by name (AC1)."""
    from ringcad.geometry import MODULES

    assert EXPECTED_MODULE_NAMES <= set(MODULES.keys()), (
        f"MODULES missing {EXPECTED_MODULE_NAMES - set(MODULES.keys())}"
    )


def test_all_modules_conform_to_protocol():
    """Each registered module satisfies the runtime_checkable Module protocol:
    has a `name`, and callable `build` / `check` (AC1)."""
    from ringcad.geometry import MODULES, Module

    assert MODULES, "MODULES registry is empty"
    for key, module in MODULES.items():
        assert isinstance(module, Module), f"{key} is not a Module"
        assert hasattr(module, "name"), f"{key} has no .name"
        assert isinstance(module.name, str) and module.name, f"{key} bad .name"
        assert callable(getattr(module, "build", None)), f"{key}.build not callable"
        assert callable(getattr(module, "check", None)), f"{key}.check not callable"


def test_module_name_matches_registry_key():
    """A module's own `.name` matches the key it is registered under (AC1)."""
    from ringcad.geometry import MODULES

    for key, module in MODULES.items():
        assert module.name == key, f"{key} registered under mismatched name {module.name!r}"
