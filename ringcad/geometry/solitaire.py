"""build_solitaire() — compose shank + prong_setting + seat into one solid.

The spike fused `[_band] + _setting_solids` (peg, torus, claws) in a single
boolean batch. Splitting into shank / prong_setting (peg+claws) / seat (torus)
and fusing all three yields the same manifold (boolean union is commutative)
because every piece keeps the spike's exact placement.
"""
from __future__ import annotations

from ringcad.ringspec import RingSpec

from .prong_setting import prong_setting
from .seat import seat
from .shank import shank


def build_solitaire(spec: RingSpec):
    """RingSpec (solitaire-7) → one watertight build123d solid."""
    solids = [shank(spec), prong_setting(spec), seat(spec)]
    return solids[0].fuse(*solids[1:])
