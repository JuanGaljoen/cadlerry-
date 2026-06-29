"""RNG-16 AC4 — per-module in-kernel castability self-checks (RED).

RED until `ringcad.geometry._castability` lands `check_shank`, `check_seat`,
`check_prong_setting`, `check_bezel`, each `(solid, spec, clamps) -> list[Violation]`.

Pins the contract:
- a schema-legal-but-thin band (built below the wall floor) makes `check_shank`
  return a `min_wall` Violation — floors live in castability, not in the schema
  (the band_thickness field is `gt=0`, so 0.5mm is a valid RingSpec);
- `check_prong_setting` / `check_seat` run and are clean on the canonical spec;
- the canonical spec yields NO violations from any of the four checks;
- every Violation's `limit_mm` is the constant imported from
  `ringcad.mesh_validator` (MIN_WALL_MM / MIN_PRONG_TIP_MM), never a literal —
  the single-source-of-truth rule.

The thin band is built by overriding the clamps' `bt` below the floor and
passing it through the module's optional `c` argument, so the geometry is
genuinely sub-floor regardless of any clamp flooring elsewhere.
"""
import pytest

from ringcad.geometry import prong_setting, seat, shank
from ringcad.geometry._castability import (
    check_prong_setting,
    check_seat,
    check_shank,
)
from ringcad.geometry._common import clamps
from ringcad.mesh_validator import MIN_PRONG_TIP_MM, MIN_WALL_MM
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

_LIMIT_BY_CODE = {
    "min_wall": MIN_WALL_MM,
    "min_prong_tip": MIN_PRONG_TIP_MM,
}


@pytest.fixture
def spec():
    return from_params(CANONICAL_PARAMS)


def _thin_band_clamps(spec):
    """Clamps with a genuinely sub-floor band thickness (0.5mm < 0.8mm)."""
    c = clamps(spec)
    c["bt"] = 0.5
    return c


# --- AC4: a thin band flags min_wall ----------------------------------------
def test_thin_band_flags_min_wall(spec):
    c = _thin_band_clamps(spec)
    viols = check_shank(shank(spec, c), spec, c)
    min_wall = [v for v in viols if v.code == "min_wall"]
    assert min_wall, "0.5mm band did not flag min_wall"
    assert min_wall[0].limit_mm == MIN_WALL_MM


# --- AC4: prong-tip + seat-collar checks run and are clean on canonical -------
def test_prong_setting_check_clean_on_canonical(spec):
    viols = check_prong_setting(prong_setting(spec), spec, clamps(spec))
    assert isinstance(viols, list)
    assert [v for v in viols if v.code == "min_prong_tip"] == []


def test_seat_check_clean_on_canonical(spec):
    viols = check_seat(seat(spec), spec, clamps(spec))
    assert isinstance(viols, list)
    assert [v for v in viols if v.code == "min_wall"] == []


# --- AC4: canonical spec is clean across all four checks ----------------------
def test_canonical_spec_has_no_violations(spec):
    c = clamps(spec)
    all_viols = (
        check_shank(shank(spec), spec, c)
        + check_seat(seat(spec), spec, c)
        + check_prong_setting(prong_setting(spec), spec, c)
    )
    assert all_viols == [], f"canonical spec produced violations: {all_viols}"


# --- AC4: every limit comes from the mesh_validator constants -----------------
def test_limits_come_from_mesh_validator(spec):
    """Collect every violation a thin spec produces and assert each limit is the
    imported constant for its code, not a hardcoded literal."""
    c = _thin_band_clamps(spec)
    viols = (
        check_shank(shank(spec, c), spec, c)
        + check_seat(seat(spec), spec, clamps(spec))
        + check_prong_setting(prong_setting(spec), spec, clamps(spec))
    )
    assert viols, "expected at least one violation from the thin spec"
    for v in viols:
        assert v.code in _LIMIT_BY_CODE, f"unexpected code {v.code!r}"
        assert v.limit_mm == _LIMIT_BY_CODE[v.code], (
            f"{v.code} limit {v.limit_mm} != imported {_LIMIT_BY_CODE[v.code]}"
        )
