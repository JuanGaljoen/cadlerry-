"""RNG-16 AC2 + AC5 — compose() over the module library (RED).

RED until `ringcad.geometry.module` lands `compose`, the `MODULES` /
`ARCHETYPES` registries and the named compose errors. Pins:

- AC2: `compose(spec)` reproduces the pre-existing `build_solitaire` geometry
  (volume + bbox) within the RNG-13 parity band; `build_solitaire` is a thin
  wrapper that delegates to `compose`; the solitaire archetype's module order is
  fixed; and the three failure modes raise their named, `ComposeError`-rooted
  errors.
- AC5: the composed solitaire exports to an STL that `validate_and_repair`
  welds to a watertight, zero-non-manifold-edge, single-body mesh.
"""
from contextlib import contextmanager
from io import BytesIO

import pytest
import trimesh

from ringcad.geometry import (
    ARCHETYPES,
    MODULES,
    ComposeError,
    DegenerateModuleError,
    UnknownArchetypeError,
    UnregisteredModuleError,
    build_solitaire,
    compose,
    to_stl_bytes,
)
from ringcad.geometry.module import SimpleModule
from ringcad.mesh_validator import validate_and_repair, validate_mesh
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

# Spike-measured build123d volume (RNG-13 / RNG-15 parity target).
EXPECTED_VOLUME_MM3 = 389.56
VOLUME_TOL = 0.05   # ±5%, the RNG-13 parity tolerance
BBOX_TOL_MM = 0.5   # per-axis, the RNG-13 parity tolerance


@pytest.fixture
def spec():
    return from_params(CANONICAL_PARAMS)


def _mesh(data: bytes) -> trimesh.Trimesh:
    return trimesh.load(BytesIO(data), file_type="stl", force="mesh")


@contextmanager
def _registered(modules=None, archetypes=None):
    """Temporarily extend MODULES / ARCHETYPES; restore on exit."""
    modules = modules or {}
    archetypes = archetypes or {}
    for k, v in modules.items():
        MODULES[k] = v
    for k, v in archetypes.items():
        ARCHETYPES[k] = v
    try:
        yield
    finally:
        for k in modules:
            MODULES.pop(k, None)
        for k in archetypes:
            ARCHETYPES.pop(k, None)


# --- AC2: compose reproduces the legacy build_solitaire geometry -------------
def test_compose_volume_matches_spike(spec):
    vol = compose(spec).volume
    lo = EXPECTED_VOLUME_MM3 * (1 - VOLUME_TOL)
    hi = EXPECTED_VOLUME_MM3 * (1 + VOLUME_TOL)
    assert lo <= vol <= hi, f"volume {vol:.2f} outside ±5% of {EXPECTED_VOLUME_MM3}"


def test_build_solitaire_delegates_to_compose(spec):
    """build_solitaire becomes a thin wrapper → identical volume & bbox."""
    composed = compose(spec)
    legacy = build_solitaire(spec)
    assert composed.volume == pytest.approx(legacy.volume, rel=1e-9)
    cb, lb = composed.bounding_box(), legacy.bounding_box()
    for got, ref in zip(cb.size, lb.size):
        assert got == pytest.approx(ref, abs=1e-6)


def test_compose_bbox_matches_build_solitaire(spec):
    cb = compose(spec).bounding_box().size
    lb = build_solitaire(spec).bounding_box().size
    for axis, (got, ref) in enumerate(zip(cb, lb)):
        assert abs(got - ref) <= BBOX_TOL_MM, f"bbox axis {axis}: {got} vs {ref}"


def test_solitaire_archetype_module_order():
    assert ARCHETYPES["solitaire"] == ["shank", "seat", "prong_setting"]


# --- AC2: named, ComposeError-rooted failure modes ---------------------------
def test_compose_errors_subclass_compose_error():
    assert issubclass(ComposeError, ValueError)
    for err in (UnknownArchetypeError, UnregisteredModuleError, DegenerateModuleError):
        assert issubclass(err, ComposeError)


def test_unknown_archetype_raises(spec):
    with pytest.raises(UnknownArchetypeError):
        compose(spec, "halo-does-not-exist")


def test_unregistered_module_raises(spec):
    with _registered(archetypes={"_t_unreg": ["__no_such_module__"]}):
        with pytest.raises(UnregisteredModuleError):
            compose(spec, "_t_unreg")


def test_degenerate_module_raises(spec):
    degen = SimpleModule(
        name="__t_degen__",
        _build=lambda spec, c: None,
        _check=lambda solid, spec, c: [],
    )
    with _registered(
        modules={"__t_degen__": degen},
        archetypes={"_t_degen": ["__t_degen__"]},
    ):
        with pytest.raises(DegenerateModuleError):
            compose(spec, "_t_degen")


# --- AC5: composed solitaire is a watertight, single-body manifold -----------
def test_compose_solitaire_watertight_zero_nme(spec):
    outcome = validate_and_repair(to_stl_bytes(compose(spec)))
    assert outcome.mesh_valid is True
    result = validate_mesh(_mesh(outcome.stl_bytes))
    assert result.is_watertight is True
    assert result.non_manifold_edges == 0
    assert result.body_count == 1
