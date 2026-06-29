"""Module library: the generic module interface + registry + compose (RNG-16).

A `Module` is a named unit that builds a build123d solid from its RingSpec slice
and self-checks the result for castability. `SimpleModule` adapts the existing
free functions (shank / seat / prong_setting / bezel) to that interface. The
`MODULES` registry maps name -> Module; `ARCHETYPES` maps an archetype name to
an ordered module list. `compose` builds and fuses an archetype's modules.

Production ships only the "solitaire" archetype; new archetypes (and modules)
register at runtime without editing any existing module file (AC6).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from ringcad.ringspec import RingSpec, Violation

from . import _castability as _ck
from ._common import clamps
from .bezel import bezel
from .prong_setting import prong_setting
from .seat import seat
from .shank import shank


@runtime_checkable
class Module(Protocol):
    """A named, composable geometry unit."""

    name: str

    def build(self, spec: RingSpec, clamps: dict): ...

    def check(self, solid, spec: RingSpec, clamps: dict) -> list[Violation]: ...


@dataclass(frozen=True)
class SimpleModule:
    """Adapts free build/check callables to the Module interface."""

    name: str
    _build: Callable
    _check: Callable

    def build(self, spec: RingSpec, clamps: dict):
        return self._build(spec, clamps)

    def check(self, solid, spec: RingSpec, clamps: dict) -> list[Violation]:
        return self._check(solid, spec, clamps)


class ComposeError(ValueError):
    """Base for all compose() failures."""


class UnknownArchetypeError(ComposeError):
    """The requested archetype is not registered in ARCHETYPES."""


class UnregisteredModuleError(ComposeError):
    """An archetype names a module absent from MODULES."""


class DegenerateModuleError(ComposeError):
    """A module produced no solid / non-positive volume."""


MODULES: dict[str, Module] = {
    "shank": SimpleModule(
        name="shank",
        _build=lambda spec, c: shank(spec, c),
        _check=_ck.check_shank,
    ),
    "seat": SimpleModule(
        name="seat",
        _build=lambda spec, c: seat(spec, c),
        _check=_ck.check_seat,
    ),
    "prong_setting": SimpleModule(
        name="prong_setting",
        _build=lambda spec, c: prong_setting(spec, c),
        _check=_ck.check_prong_setting,
    ),
    "bezel": SimpleModule(
        name="bezel",
        _build=lambda spec, c: bezel(spec, c),
        _check=_ck.check_bezel,
    ),
}

ARCHETYPES: dict[str, list[str]] = {
    "solitaire": ["shank", "seat", "prong_setting"],
}


def compose(spec: RingSpec, archetype: str | None = None):
    """Build + fuse an archetype's modules into one build123d solid."""
    name = archetype or spec.archetype
    if name not in ARCHETYPES:
        raise UnknownArchetypeError(f"unknown archetype {name!r}")
    c = clamps(spec)
    solids = []
    for mod_name in ARCHETYPES[name]:
        module = MODULES.get(mod_name)
        if module is None:
            raise UnregisteredModuleError(
                f"archetype {name!r} names unregistered module {mod_name!r}"
            )
        solid = module.build(spec, c)
        if solid is None or solid.volume <= 0:
            raise DegenerateModuleError(
                f"module {mod_name!r} produced a degenerate solid"
            )
        solids.append(solid)
    return solids[0].fuse(*solids[1:])
