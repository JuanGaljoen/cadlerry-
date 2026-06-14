"""Unit tests for the reusable mesh validator (no OpenSCAD required).

The validator is the single source of truth for "is this mesh castable" and is
reused by RNG-2 (backend) and extended by RNG-5 (auto-repair), so it is tested
in isolation with synthetic trimesh primitives.

RNG-5 TDD RED: the `validate_and_repair` / `RepairOutcome` import below does not
exist yet, so the whole module fails at collection (ImportError) -> correct RED
signal. The implementer lands `validate_and_repair` + `RepairOutcome` in
ringcad.mesh_validator to turn the RNG-5 tests GREEN. The existing RNG-1 tests
above the divider keep passing once the import resolves.
"""
import io

import numpy as np
import trimesh

from ringcad.mesh_validator import (
    RepairOutcome,
    validate_and_repair,
    validate_mesh,
)


def _stl_bytes(mesh: trimesh.Trimesh) -> bytes:
    """Export a trimesh to binary STL bytes (the wire format the backend
    reads off disk and hands to validate_and_repair)."""
    return mesh.export(file_type="stl")


def _reload(stl_bytes: bytes) -> trimesh.Trimesh:
    """Round-trip STL bytes back into a single Trimesh (force='mesh' so
    multi-solid STLs concatenate into one mesh with body_count > 1)."""
    return trimesh.load(io.BytesIO(stl_bytes), file_type="stl", force="mesh")


def _holed_box() -> trimesh.Trimesh:
    """A box with a multi-face opening cut into it (not a single triangle).

    Dropping a contiguous run of faces leaves an open region with several
    boundary edges; fill_holes in trimesh 4.5.3 can close a multi-edge hole
    far more reliably than a lone-triangle gap. RED asserts the contract
    'holed input becomes castable after repair'; the implementer is free to
    pick whatever fixture fill_holes actually closes if this one is marginal.
    """
    mesh = trimesh.creation.box(extents=(4, 4, 4))
    keep = np.ones(len(mesh.faces), dtype=bool)
    # drop the two triangles that make up one full face of the box
    keep[0] = False
    keep[1] = False
    mesh.update_faces(keep)
    mesh.remove_unreferenced_vertices()
    return mesh


def test_watertight_box_is_castable():
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    result = validate_mesh(mesh)
    assert result.is_watertight
    assert result.non_manifold_edges == 0
    assert result.body_count == 1
    assert result.is_castable


def test_two_disjoint_boxes_report_two_bodies_and_not_castable():
    a = trimesh.creation.box(extents=(1, 1, 1))
    b = trimesh.creation.box(extents=(1, 1, 1))
    b.apply_translation([5, 0, 0])
    mesh = trimesh.util.concatenate([a, b])
    result = validate_mesh(mesh)
    assert result.body_count == 2
    assert not result.is_castable


def test_open_mesh_is_not_watertight_and_not_castable():
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    keep = np.ones(len(mesh.faces), dtype=bool)
    keep[0] = False  # drop a face -> open hole
    mesh.update_faces(keep)
    result = validate_mesh(mesh)
    assert not result.is_watertight
    assert not result.is_castable


# ===========================================================================
# RNG-5: validate_and_repair / RepairOutcome (auto-repair)
# ===========================================================================


# ---- AC2/AC8: already-castable input is returned untouched -----------------
def test_castable_box_passes_through_unrepaired():
    mesh = trimesh.creation.box(extents=(3, 3, 3))
    stl = _stl_bytes(mesh)

    outcome = validate_and_repair(stl)

    assert isinstance(outcome, RepairOutcome)
    assert outcome.mesh_valid is True
    assert outcome.mesh_repaired is False
    # AC8: returned bytes reload to a watertight single body
    reloaded = validate_mesh(_reload(outcome.stl_bytes))
    assert reloaded.is_watertight
    assert reloaded.body_count == 1
    assert reloaded.is_castable


# ---- AC2/AC8: a holed mesh becomes castable after auto-repair --------------
def test_holed_box_is_repaired_to_castable():
    stl = _stl_bytes(_holed_box())

    outcome = validate_and_repair(stl)

    # Contract: a closable open mesh comes back castable AND flagged repaired.
    assert outcome.mesh_repaired is True
    assert outcome.mesh_valid is True
    assert outcome.detail != ""  # repaired outcomes carry a non-empty detail
    # AC8: the *repaired* bytes round-trip to a castable mesh.
    reloaded = validate_mesh(_reload(outcome.stl_bytes))
    assert reloaded.is_castable


# ---- AC2: disjoint bodies cannot be auto-repaired into one solid -----------
def test_two_disjoint_boxes_stay_invalid_after_repair():
    a = trimesh.creation.box(extents=(1, 1, 1))
    b = trimesh.creation.box(extents=(1, 1, 1))
    b.apply_translation([5, 0, 0])
    stl = _stl_bytes(trimesh.util.concatenate([a, b]))

    outcome = validate_and_repair(stl)

    assert outcome.mesh_repaired is True
    assert outcome.mesh_valid is False
    # returned bytes still describe two separate solids
    reloaded = validate_mesh(_reload(outcome.stl_bytes))
    assert reloaded.body_count == 2
    assert "disjoint bodies" in outcome.detail.lower()


# ---- AC8: any repaired bytes are non-empty and reloadable ------------------
def test_repaired_bytes_are_non_empty_and_loadable():
    stl = _stl_bytes(_holed_box())

    outcome = validate_and_repair(stl)

    assert outcome.mesh_repaired is True
    assert len(outcome.stl_bytes) > 0
    mesh = _reload(outcome.stl_bytes)
    assert len(mesh.faces) > 0


# ---- AC9: detail is header-safe (ascii, no CR/LF, capped, no leakage) ------
def test_repair_detail_is_header_safe():
    # exercise both a repaired-valid and a repaired-invalid outcome
    cases = [
        _stl_bytes(_holed_box()),
        _stl_bytes(
            trimesh.util.concatenate([
                trimesh.creation.box(extents=(1, 1, 1)),
                trimesh.creation.box(extents=(1, 1, 1)).apply_translation(
                    [5, 0, 0]
                ),
            ])
        ),
    ]
    for stl in cases:
        detail = validate_and_repair(stl).detail
        assert detail.isascii(), f"non-ascii detail: {detail!r}"
        assert "\n" not in detail and "\r" not in detail
        assert len(detail) <= 200
        # fixed vocabulary only — never a path or a traceback fragment
        assert "/" not in detail
        assert "Traceback" not in detail


# ---- AC7: never raises on garbage / empty input; raw passthrough -----------
def test_validate_and_repair_never_raises_on_garbage():
    raw = b"this is definitely not an stl file"
    outcome = validate_and_repair(raw)  # must not raise
    assert outcome.mesh_valid is False
    assert outcome.mesh_repaired is False
    assert outcome.stl_bytes == raw  # raw passthrough
    assert outcome.detail.isascii()


def test_validate_and_repair_never_raises_on_empty():
    outcome = validate_and_repair(b"")  # must not raise
    assert outcome.mesh_valid is False
    assert outcome.mesh_repaired is False
    assert outcome.stl_bytes == b""
