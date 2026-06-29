"""Per-module in-kernel castability self-checks (RNG-16 AC4).

Each `check_*(solid, spec, clamps) -> list[Violation]` probes the *actual*
build123d geometry a module produced (not the spec fields) against the lost-wax
casting floors. Limits are single-sourced from `ringcad.mesh_validator`
(MIN_WALL_MM / MIN_PRONG_TIP_MM) and the structured `Violation` is reused from
`ringcad.ringspec` — never redefined, never a hardcoded literal.

These self-checks AUGMENT the post-geometry `validate_and_repair` mesh gate;
they do not replace it.
"""
from __future__ import annotations

from build123d import Plane

from ringcad.mesh_validator import MIN_PRONG_TIP_MM, MIN_WALL_MM
from ringcad.ringspec import RingSpec, Violation


def _section_sizes(solid, plane: Plane) -> list:
    """Bounding-box sizes of every face of `solid` cut by `plane`."""
    return [f.bounding_box().size for f in solid.intersect(plane).faces()]


def _min_nonzero(size) -> float | None:
    """Smallest non-zero dimension of a bounding-box size Vector."""
    dims = [d for d in (size.X, size.Y, size.Z) if d > 1e-9]
    return min(dims) if dims else None


def check_shank(solid, spec: RingSpec, clamps: dict) -> list[Violation]:
    """Radial band wall via an XZ section through the ring's top/bottom."""
    radial = [s.X for s in _section_sizes(solid, Plane.XZ) if s.X > 1e-9]
    if not radial:
        return []
    wall = min(radial)
    if wall < MIN_WALL_MM:
        return [Violation(
            code="min_wall",
            field="shank.band_thickness",
            message=f"Shank radial wall {wall:.3f}mm is below the "
            f"{MIN_WALL_MM}mm minimum wall thickness for lost-wax casting.",
            limit_mm=MIN_WALL_MM,
            actual_mm=wall,
        )]
    return []


def check_seat(solid, spec: RingSpec, clamps: dict) -> list[Violation]:
    """Seat-collar tube thickness via an XZ section through the torus."""
    sizes = [_min_nonzero(s) for s in _section_sizes(solid, Plane.XZ)]
    sizes = [s for s in sizes if s is not None]
    if not sizes:
        return []
    wall = min(sizes)
    if wall < MIN_WALL_MM:
        return [Violation(
            code="min_wall",
            field="setting.setting_height",
            message=f"Seat collar tube {wall:.3f}mm is below the "
            f"{MIN_WALL_MM}mm minimum wall thickness for lost-wax casting.",
            limit_mm=MIN_WALL_MM,
            actual_mm=wall,
        )]
    return []


def check_prong_setting(solid, spec: RingSpec, clamps: dict) -> list[Violation]:
    """Prong-tip feature size via a section just below the claw tips.

    Claws point along the global +X head axis; section perpendicular to it a
    short way below the tips and read the smallest claw cross-section.
    """
    bb = solid.bounding_box()
    sizes = [_min_nonzero(s)
             for s in _section_sizes(solid, Plane.YZ.offset(bb.max.X - 0.3))]
    sizes = [s for s in sizes if s is not None]
    if not sizes:
        return []
    tip = min(sizes)
    if tip < MIN_PRONG_TIP_MM:
        return [Violation(
            code="min_prong_tip",
            field="setting.prong_count",
            message=f"Prong-tip feature {tip:.3f}mm is below the "
            f"{MIN_PRONG_TIP_MM}mm minimum prong-tip diameter.",
            limit_mm=MIN_PRONG_TIP_MM,
            actual_mm=tip,
        )]
    return []


def check_bezel(solid, spec: RingSpec, clamps: dict) -> list[Violation]:
    """Bezel-collar radial wall via the annulus in an upper cross-axis section.

    The collar axis is the global +X head axis; section the pure-annulus region
    above the base and read wall = outer_radius - inner_radius from the two
    circular edges.
    """
    bb = solid.bounding_box()
    x = bb.max.X - 0.30 * (bb.max.X - bb.min.X)
    radii: list[float] = []
    for f in solid.intersect(Plane.YZ.offset(x)).faces():
        for e in f.edges():
            try:
                radii.append(e.radius)
            except Exception:
                pass
    if len(radii) < 2:
        return []
    wall = max(radii) - min(radii)
    if wall < MIN_WALL_MM:
        return [Violation(
            code="min_wall",
            field="setting.setting_height",
            message=f"Bezel collar wall {wall:.3f}mm is below the "
            f"{MIN_WALL_MM}mm minimum wall thickness for lost-wax casting.",
            limit_mm=MIN_WALL_MM,
            actual_mm=wall,
        )]
    return []
