"""build_solitaire() — compose shank + prong_setting + seat into one solid.

The spike fused `[_band] + _setting_solids` (peg, torus, claws) in a single
boolean batch. Splitting into shank / prong_setting (peg+claws) / seat (torus)
and fusing all three yields the same manifold (boolean union is commutative)
because every piece keeps the spike's exact placement.
"""
from __future__ import annotations

from ringcad.ringspec import RingSpec

from .module import compose


def build_solitaire(spec: RingSpec):
    """RingSpec (solitaire-7) → one watertight build123d solid.

    Thin wrapper over the module library: composes the "solitaire" archetype
    (shank + seat + prong_setting). Boolean union is commutative and the mesh
    repair gate absorbs seam differences, so parity with the RNG-15 batch fuse
    holds.
    """
    return compose(spec)
