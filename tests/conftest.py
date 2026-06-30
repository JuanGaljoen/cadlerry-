"""Shared test helpers for the geometry suite (RNG-17).

`raw_validate` is the watertight-by-construction probe: it exports a build123d
solid to STL bytes and validates the RAW mesh — deliberately WITHOUT
`validate_and_repair`, which would weld open edges shut and hide the very
non-manifoldness RNG-17 fixes. It returns the project's own `ValidationResult`,
which already exposes `.is_watertight`, `.non_manifold_edges`, and `.body_count`.
"""
from __future__ import annotations

from io import BytesIO

import pytest
import trimesh

from ringcad.geometry.export import to_stl_bytes
from ringcad.mesh_validator import ValidationResult, validate_mesh


def validate_raw_solid(solid) -> ValidationResult:
    """build123d solid -> raw STL -> trimesh -> validate_mesh (no repair)."""
    data = to_stl_bytes(solid)
    mesh = trimesh.load(BytesIO(data), file_type="stl", force="mesh")
    return validate_mesh(mesh)


@pytest.fixture
def raw_validate():
    """Expose `validate_raw_solid` to tests as an injectable callable."""
    return validate_raw_solid
