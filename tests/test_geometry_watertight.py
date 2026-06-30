"""RNG-17 — watertight-by-construction for prong_setting + compose (RED).

These pin the RNG-17 target: the RAW (pre-repair) geometry must be a single
watertight manifold. They FAIL today because the prong_setting claw joints are
tangent (segment cap circles lie exactly on the node spheres), which OCCT turns
into boundary edges — 12 open edges on prong_setting, 6 on the composed
solitaire. The fix inflates the claw node spheres by a small epsilon so the
joints become true volumetric overlaps.

RAW geometry only — `raw_validate` (tests/conftest.py) never calls
`validate_and_repair`, so the open edges are measured, not welded away.
"""
from __future__ import annotations

import pytest

from ringcad.geometry import compose, prong_setting
from ringcad.geometry._common import clamps
from ringcad.ringspec import from_params

# Canonical solitaire (RNG-14 GOOD_PARAMS); the grid overrides three fields.
CANONICAL_PARAMS = {
    "inner_diameter": 16.5,
    "band_width": 2.2,
    "band_thickness": 1.9,
    "stone_diameter": 6.5,
    "stone_height": 4.0,
    "prong_count": 6,
    "setting_height": 6.0,
}

PRONG_COUNTS = (4, 6)
STONE_DIAMETERS = (2.0, 6.5, 10.0)
SETTING_HEIGHTS = (3.0, 6.0, 8.0)


def _spec(prong_count: int, stone_diameter: float, setting_height: float):
    return from_params({
        **CANONICAL_PARAMS,
        "prong_count": prong_count,
        "stone_diameter": stone_diameter,
        "setting_height": setting_height,
    })


def _assert_castable(result, label: str) -> None:
    assert result.body_count == 1, (
        f"{label}: body_count={result.body_count} (want 1)"
    )
    assert result.non_manifold_edges == 0, (
        f"{label}: non_manifold_edges={result.non_manifold_edges} (want 0)"
    )
    assert result.is_watertight, f"{label}: raw mesh is not watertight"


@pytest.mark.parametrize("prong_count", PRONG_COUNTS)
@pytest.mark.parametrize("stone_diameter", STONE_DIAMETERS)
@pytest.mark.parametrize("setting_height", SETTING_HEIGHTS)
def test_prong_setting_raw_watertight(
    raw_validate, prong_count, stone_diameter, setting_height
):
    """AC1: a raw prong_setting solid is a single watertight manifold across
    the prong_count x stone_diameter x setting_height grid (FAILS now: tangent
    claw joints leave 12 open edges)."""
    spec = _spec(prong_count, stone_diameter, setting_height)
    solid = prong_setting(spec, clamps(spec))
    label = f"prong_setting(n={prong_count}, sd={stone_diameter}, gh={setting_height})"
    _assert_castable(raw_validate(solid), label)


@pytest.mark.parametrize("prong_count", PRONG_COUNTS)
@pytest.mark.parametrize("stone_diameter", STONE_DIAMETERS)
@pytest.mark.parametrize("setting_height", SETTING_HEIGHTS)
def test_compose_solitaire_raw_watertight(
    raw_validate, prong_count, stone_diameter, setting_height
):
    """AC2: the raw composed solitaire is a single watertight manifold across
    the same grid (FAILS now: 6 open edges carried up from prong_setting)."""
    spec = _spec(prong_count, stone_diameter, setting_height)
    solid = compose(spec)
    label = f"compose(n={prong_count}, sd={stone_diameter}, gh={setting_height})"
    _assert_castable(raw_validate(solid), label)
