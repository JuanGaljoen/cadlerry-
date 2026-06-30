"""STL / STEP byte exporters for build123d solids (RNG-15 AC4).

Both write to a tempfile via build123d's `export_stl` / `export_step`, then read
the bytes back. STEP keeps OCCT's default ISO-10303 header (we don't strip it).

RNG-17: build123d/OCCT's `export_stl` emits spurious *null* triangles — zero-area
faces with a repeated vertex at every sphere/loft pole (it even warns "null
triangulation"). The fused B-rep solid is already a single watertight manifold
(`solid.solids()` is length 1), but those degenerate triangles leave the *mesh*
non-manifold: open edges that split the STL into phantom one-face bodies. We drop
them at export so the raw STL faithfully reflects the watertight B-rep. This is
not mesh repair (no hole filling, no reshaping) and not a tolerance change — it
only discards zero-area triangles, so volume and bounding box are untouched.
"""
from __future__ import annotations

import os
import tempfile
from io import BytesIO

import trimesh
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


def _drop_null_triangles(stl_bytes: bytes) -> bytes:
    """Load STL bytes (vertices merged on load), discard zero-area triangles,
    and re-export. Removes build123d's degenerate pole faces only."""
    mesh = trimesh.load(BytesIO(stl_bytes), file_type="stl", force="mesh")
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    return mesh.export(file_type="stl")


def to_stl_bytes(solid) -> bytes:
    """Export a build123d solid to clean binary STL bytes (null pole triangles
    from OCCT tessellation removed; see module docstring)."""
    return _drop_null_triangles(_export_bytes(solid, ".stl", export_stl))


def to_step_bytes(solid) -> bytes:
    """Export a build123d solid to STEP bytes (ISO-10303 header preserved)."""
    return _export_bytes(solid, ".step", export_step)
