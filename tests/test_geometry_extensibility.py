"""RNG-16 AC6 — a new archetype needs no edit to existing module files (RED).

RED until `ringcad.geometry.module` lands `SimpleModule`, `MODULES`,
`ARCHETYPES` and `compose`. This test proves the open/closed property of the
module library: a brand-new archetype can be assembled by registering a
`SimpleModule` and an ARCHETYPES entry at runtime, WITHOUT importing or editing
any existing module file (shank.py / seat.py / prong_setting.py / bezel.py).

Imports are deliberately confined to `ringcad.geometry.module` and
`ringcad.geometry._common` (plus the spec factory) — if a new archetype needed
to touch an existing module file, this test could not be written this way.
"""
from contextlib import contextmanager

import pytest

from ringcad.geometry._common import band, clamps
from ringcad.geometry.module import (
    ARCHETYPES,
    MODULES,
    SimpleModule,
    compose,
)
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

STUB_NAME = "__t_stub_module__"
STUB_ARCH = "stub_arch"


@pytest.fixture
def spec():
    return from_params(CANONICAL_PARAMS)


@contextmanager
def _stub_registered():
    """Insert a throwaway SimpleModule + archetype; pop both on teardown."""
    stub = SimpleModule(
        name=STUB_NAME,
        _build=lambda spec, c: band(c),       # a positive-volume solid via _common
        _check=lambda solid, spec, c: [],
    )
    MODULES[STUB_NAME] = stub
    ARCHETYPES[STUB_ARCH] = ["shank", STUB_NAME]
    try:
        yield
    finally:
        MODULES.pop(STUB_NAME, None)
        ARCHETYPES.pop(STUB_ARCH, None)


def test_new_archetype_composes_without_touching_modules(spec):
    with _stub_registered():
        solid = compose(spec, STUB_ARCH)
        assert solid.volume > 0


def test_simple_module_conforms_and_builds(spec):
    """The throwaway SimpleModule is a usable module: builds a positive solid
    and reports no violations from its check."""
    with _stub_registered():
        stub = MODULES[STUB_NAME]
        c = clamps(spec)
        assert stub.name == STUB_NAME
        assert stub.build(spec, c).volume > 0
        assert stub.check(stub.build(spec, c), spec, c) == []
