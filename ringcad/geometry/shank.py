"""shank() — the tapered oval-section band (port of the spike's `_band`)."""
from __future__ import annotations

from ringcad.ringspec import RingSpec

from ._common import band, clamps


def shank(spec: RingSpec):
    """Tapered oval-section shank for a RingSpec → one build123d solid."""
    return band(clamps(spec))
