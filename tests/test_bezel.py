"""RNG-16 AC3 — the bezel module + its composition (RED).

RED until `ringcad.geometry.bezel` (the `bezel(spec, c=None) -> Solid` collar)
and `ringcad.geometry._castability.check_bezel` land, and the bezel module is
registered in MODULES. Pins:

- bezel is a positive-volume solid across a range of stone diameters;
- a "bezel" archetype (registered via fixture) composes to a watertight,
  zero-non-manifold-edge, single-body manifold through the real mesh gate;
- the bezel collar self-check is clean at a normal stone diameter and flags a
  min_wall violation when the collar is forced thin.
"""
from contextlib import contextmanager
from io import BytesIO

import pytest
import trimesh

from ringcad.geometry import ARCHETYPES, MODULES, bezel, compose, to_stl_bytes
from ringcad.geometry._castability import check_bezel
from ringcad.geometry._common import clamps
from ringcad.mesh_validator import MIN_WALL_MM, validate_and_repair, validate_mesh
from ringcad.ringspec import from_params

CANONICAL_PARAMS = {
    "inner_diameter": 16.5,
    "band_width": 2.2,
    "band_thickness": 1.9,
    "stone_diameter": 6.5,
    "stone_height": 4.0,
    "prong_count": 6,
    "setting_height": 6.0,
}


def _params(**overrides):
    p = dict(CANONICAL_PARAMS)
    p.update(overrides)
    return p


@pytest.fixture
def spec():
    return from_params(CANONICAL_PARAMS)


def _mesh(data: bytes) -> trimesh.Trimesh:
    return trimesh.load(BytesIO(data), file_type="stl", force="mesh")


@contextmanager
def _bezel_archetype():
    """Register a watertight ring-with-bezel archetype for the duration of a
    test; the bezel module itself ships in MODULES, only the composition is
    test-scoped. Restores ARCHETYPES on exit."""
    ARCHETYPES["bezel"] = ["shank", "seat", "bezel"]
    try:
        yield
    finally:
        ARCHETYPES.pop("bezel", None)


# --- AC3: bezel is a positive-volume solid across stone diameters ------------
@pytest.mark.parametrize("stone_diameter", [4.0, 5.5, 6.5, 8.0])
def test_bezel_positive_volume(stone_diameter):
    spec = from_params(_params(stone_diameter=stone_diameter))
    assert bezel(spec).volume > 0


def test_bezel_accepts_optional_clamps(spec):
    """bezel(spec, c) must accept a precomputed clamps dict (compose passes it)."""
    assert bezel(spec, clamps(spec)).volume > 0


# --- AC3: a bezel composition is watertight through the real mesh gate -------
def test_bezel_composition_watertight(spec):
    with _bezel_archetype():
        assert "bezel" in MODULES
        outcome = validate_and_repair(to_stl_bytes(compose(spec, "bezel")))
    assert outcome.mesh_valid is True
    result = validate_mesh(_mesh(outcome.stl_bytes))
    assert result.is_watertight is True
    assert result.non_manifold_edges == 0
    assert result.body_count == 1


# --- AC3: bezel collar self-check ------------------------------------------
def test_bezel_selfcheck_clean_at_normal_diameter(spec):
    viols = check_bezel(bezel(spec), spec, clamps(spec))
    assert [v for v in viols if v.code == "min_wall"] == []


def test_bezel_selfcheck_flags_thin_collar():
    """A collar forced below MIN_WALL_MM (radial thickness clamped thin) must
    yield a min_wall violation whose limit comes from the mesh validator."""
    spec = from_params(CANONICAL_PARAMS)
    c = clamps(spec)
    c["bezel_wall"] = 0.4  # sub-floor collar wall hint for the bezel module
    thin = bezel(spec, c)
    viols = check_bezel(thin, spec, c)
    min_wall = [v for v in viols if v.code == "min_wall"]
    assert min_wall, "thin bezel collar did not flag min_wall"
    assert min_wall[0].limit_mm == MIN_WALL_MM
