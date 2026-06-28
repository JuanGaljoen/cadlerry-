"""prong_setting() — gallery peg + N prong claws (the peg/claw portion of the
spike's `_setting_solids`, with the seat torus split out into `seat.py`).

The peg + claw nodes/segments are authored in a local +Z frame then laid onto
the global +X head axis via the shared placement transform — identical to the
spike so the fused solid is unchanged.
"""
from __future__ import annotations

from build123d import Align, Cone, Pos, Rot, Sphere, Vector

from ringcad.ringspec import RingSpec

from ._common import (
    MIN_PRONG_TIP, MIN_WALL, body_solid, clamps, placement,
)


def prong_setting(spec: RingSpec):
    """Gallery peg + claws for a RingSpec → one fused build123d solid."""
    c = clamps(spec)
    stone_r, ring_z, claw_rise = c["stone_r"], c["ring_z"], c["claw_rise"]
    wire_r = max(MIN_WALL / 2 + 0.1, 0.5)
    tip_r = max(MIN_PRONG_TIP / 2, 0.4)
    base_r = max(stone_r * 0.20, MIN_WALL)

    local = []
    peg_h = max(ring_z * 0.4, 1.0) + 0.4
    local.append(Cone(base_r + wire_r, base_r, peg_h,
                      align=(Align.CENTER, Align.CENTER, Align.MIN)))
    # Claw nodes (one sphere each) + segment bodies between them.
    A, B = Vector(base_r, 0, 0), Vector(stone_r, 0, ring_z)
    C = Vector(stone_r, 0, ring_z + claw_rise * 0.55)
    D = Vector(stone_r * 0.88, 0, ring_z + claw_rise)
    nodes = [(A, wire_r), (B, wire_r), (C, wire_r * 0.92), (D, tip_r * 1.45)]
    edges = [(A, wire_r, B, wire_r), (B, wire_r, C, wire_r * 0.92),
             (C, wire_r * 0.92, D, tip_r)]
    n = int(c["prong_n"])
    for i in range(n):
        rot = Rot(0, 0, i * 360.0 / n)
        for v, r in nodes:
            local.append(rot * (Pos(*v) * Sphere(r)))
        for v1, r1, v2, r2 in edges:
            local.append(rot * body_solid(v1, r1, v2, r2))

    place = placement(c)
    solids = [place * s for s in local]
    return solids[0].fuse(*solids[1:])
