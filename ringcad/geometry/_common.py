"""Shared geometry helpers for the build123d solitaire (RNG-15).

Faithful port of the arithmetic in `spikes/rng13/b123d_solitaire.py`. Casting
constants are imported from `ringcad.mesh_validator` (single source of truth),
not re-declared. Clamps, the band cross-section, and the claw primitives live
here so the shank / prong_setting / seat modules share one copy.
"""
from __future__ import annotations

import math
from typing import Mapping

from build123d import (
    Align, Cone, Cylinder, Ellipse, Location, Plane, Pos, Rot, Vector, loft,
)

from ringcad.mesh_validator import MIN_PRONG_TIP_MM, MIN_WALL_MM
from ringcad.ringspec import RingSpec, to_params

SHANK_TAPER = 1.7
NA = 96  # sections around the ring (matches the spike)


def _head_t(a_deg: float) -> float:
    return ((1 + math.cos(math.radians(a_deg))) / 2) ** 1.5


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _clamps(p: Mapping[str, object]) -> dict:
    id_c = max(float(p["inner_diameter"]), 5.0)
    bt_c = max(float(p["band_thickness"]), MIN_WALL_MM)
    bw_c = max(float(p["band_width"]), MIN_WALL_MM)
    sd_c = max(float(p["stone_diameter"]), 1.0)
    gh_c = max(float(p["setting_height"]), MIN_WALL_MM)
    taper = max(SHANK_TAPER, 1.0)
    inner_r = id_c / 2
    return {
        "inner_r": inner_r,
        "bt": bt_c,
        "bw": bw_c,
        "stone_r": sd_c / 2,
        "gh": gh_c,
        "taper": taper,
        "head_r": inner_r + bt_c * taper,
        "ring_z": gh_c * 0.5,
        "claw_rise": gh_c * 0.5,
    }


def clamps(spec: RingSpec) -> dict:
    """Derive the casting clamps for a RingSpec (with `prong_n` resolved)."""
    p = to_params(spec)
    c = _clamps(p)
    pc = int(p["prong_count"])
    c["prong_n"] = pc if pc in (4, 6) else 4
    return c


def placement(c: dict) -> Location:
    """Local +Z setting frame laid onto the global +X head axis (the spike's
    `place` transform). Shared so peg, claws and seat torus land identically."""
    return Pos(c["head_r"] - 0.4, 0, 0) * Rot(0, 90, 0)


def _band_section(c: dict, a_deg: float):
    """One oval cross-section face at ring angle `a` (deg)."""
    r = math.radians(a_deg)
    t = _head_t(a_deg)
    th = _lerp(c["bt"], c["bt"] * c["taper"], t)
    w = _lerp(c["bw"], c["bw"] * c["taper"], t)
    rc = c["inner_r"] + th / 2
    origin = Vector(rc * math.cos(r), rc * math.sin(r), 0)
    x_dir = Vector(math.cos(r), math.sin(r), 0)            # radial
    z_dir = Vector(-math.sin(r), math.cos(r), 0)           # sweep tangent
    return Plane(origin=origin, x_dir=x_dir, z_dir=z_dir) * Ellipse(th / 2, w / 2)


def band(c: dict):
    """Tapered oval-section shank, pairwise-lofted and fused into one solid."""
    secs = [_band_section(c, i * 360.0 / NA) for i in range(NA + 1)]
    wedges = [loft([secs[i], secs[i + 1]]) for i in range(NA)]
    return wedges[0].fuse(*wedges[1:])


def _rot_between(a: Vector, b: Vector) -> Location:
    a, b = a.normalized(), b.normalized()
    dot = max(-1.0, min(1.0, a.dot(b)))
    ang = math.degrees(math.acos(dot))
    if ang < 1e-6:
        return Location()
    if ang > 180 - 1e-6:
        return Rot(180, 0, 0)
    axis = a.cross(b).normalized()
    return Location((0, 0, 0), (axis.X, axis.Y, axis.Z), ang)


def body_solid(v1, r1, v2, r2):
    """Cone/cylinder body of a claw segment (no end caps)."""
    axis = v2 - v1
    length = axis.length
    rot = _rot_between(Vector(0, 0, 1), axis.normalized())
    align = (Align.CENTER, Align.CENTER, Align.MIN)
    body = Cylinder(r1, length, align=align) if abs(r1 - r2) < 1e-6 \
        else Cone(r1, r2, length, align=align)
    return Pos(v1) * (rot * body)


# Re-export casting constants under the spike's local names for porting clarity.
MIN_WALL = MIN_WALL_MM
MIN_PRONG_TIP = MIN_PRONG_TIP_MM
