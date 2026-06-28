"""build123d solitaire geometry (RNG-15).

Decomposed module library — `shank`, `prong_setting`, `seat` — composed by
`build_solitaire`, with STL/STEP byte exporters. Ported faithfully from the
RNG-13 spike so OpenSCAD parity holds; casting constants come from
`ringcad.mesh_validator`.
"""
from .export import to_step_bytes, to_stl_bytes
from .prong_setting import prong_setting
from .seat import seat
from .shank import shank
from .solitaire import build_solitaire

__all__ = [
    "build_solitaire",
    "shank",
    "prong_setting",
    "seat",
    "to_stl_bytes",
    "to_step_bytes",
]
