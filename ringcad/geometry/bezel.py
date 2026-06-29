"""bezel() — a closed-base collar (cup) that wraps the stone (RNG-16 AC3).

The collar wall is an outer Cylinder minus an inner Cylinder; the inner bore is
positioned to leave a solid base disk at the bottom. The base sits on the head
axis (where the shank centreline runs) so the bezel bridges shank -> seat into a
single watertight manifold — a purely open tube cannot, because its bore is
hollow exactly where the on-axis band material is. Laid onto the global +X head
axis via the shared `placement(c)`.

Deviation note: the plan sketched an open tube ("taller inner cylinder"); a
closed base is the minimal change that makes the AC3 watertight composition
satisfiable, and is the physically correct bezel (the stone rests on the base).
"""
from __future__ import annotations

from build123d import Align, Cylinder, Pos

from ringcad.ringspec import RingSpec

from ._common import MIN_WALL, clamps, placement

_EPS = 0.1          # bore over-cut for a clean top opening
_CLEARANCE = 0.10   # radial gap between stone and collar bore


def bezel(spec: RingSpec, c: dict | None = None):
    """Closed-base bezel collar for a RingSpec -> one build123d solid.

    Honours a `c["bezel_wall"]` override (sub-floor allowed, for self-check
    testing); otherwise the collar wall defaults to `max(MIN_WALL, 0.9)`.
    """
    c = c if c is not None else clamps(spec)
    wall = c.get("bezel_wall", max(MIN_WALL, 0.9))
    base_t = max(MIN_WALL, 0.9)
    inner_r = c["stone_r"] + _CLEARANCE
    outer_r = inner_r + wall
    z0 = -0.6                       # base digs into the band along the head axis
    top = c["ring_z"] + 1.0         # collar rises past the seat
    h = top - z0
    al = (Align.CENTER, Align.CENTER, Align.MIN)
    cup = Cylinder(outer_r, h, align=al) - (
        Pos(0, 0, base_t) * Cylinder(inner_r, h - base_t + _EPS, align=al)
    )
    return placement(c) * (Pos(0, 0, z0) * cup)
