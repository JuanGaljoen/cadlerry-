"""STL / STEP byte exporters for build123d solids (RNG-15 AC4).

Both write to a tempfile via build123d's `export_stl` / `export_step`, then read
the bytes back. STEP keeps OCCT's default ISO-10303 header (we don't strip it).
"""
from __future__ import annotations

import os
import tempfile

from build123d import export_step, export_stl


def _export_bytes(solid, suffix: str, writer) -> bytes:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        writer(solid, path)
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        os.remove(path)


def to_stl_bytes(solid) -> bytes:
    """Export a build123d solid to binary STL bytes."""
    return _export_bytes(solid, ".stl", export_stl)


def to_step_bytes(solid) -> bytes:
    """Export a build123d solid to STEP bytes (ISO-10303 header preserved)."""
    return _export_bytes(solid, ".step", export_step)
