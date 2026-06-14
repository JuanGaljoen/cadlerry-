"""Reusable mesh validator — the single source of truth for "is this mesh
castable" (lost-wax).

RNG-1 only *detects*; RNG-5 will extend this with auto-repair. Keep the checks
here, not buried in tests, so the backend can call the same logic before
returning an STL.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Union

import numpy as np
import trimesh

# Lost-wax casting constraints (mm). Hard manufacturing limits, not UI hints.
MIN_WALL_MM = 0.8
MIN_PRONG_TIP_MM = 0.7

MeshLike = Union[trimesh.Trimesh, str, Path]

logger = logging.getLogger(__name__)

# X-Mesh-Repair-Detail is an HTTP header; keep it short and header-safe.
_DETAIL_CAP = 200


@dataclass(frozen=True)
class ValidationResult:
    is_watertight: bool
    non_manifold_edges: int
    body_count: int
    volume_mm3: float
    bounds: Tuple[Tuple[float, float, float], Tuple[float, float, float]]

    @property
    def is_castable(self) -> bool:
        """A castable mesh is a single watertight manifold body."""
        return (
            self.is_watertight
            and self.non_manifold_edges == 0
            and self.body_count == 1
        )


def _as_mesh(obj: MeshLike) -> trimesh.Trimesh:
    if isinstance(obj, trimesh.Trimesh):
        return obj
    mesh = trimesh.load(str(obj), force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"could not load a single mesh from {obj!r}")
    return mesh


def count_non_manifold_edges(mesh: trimesh.Trimesh) -> int:
    """Edges not shared by exactly two faces (holes = 1, non-manifold > 2)."""
    if len(mesh.faces) == 0:
        return 0
    edges = np.sort(mesh.edges, axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int(np.count_nonzero(counts != 2))


def count_bodies(mesh: trimesh.Trimesh) -> int:
    """Number of connected components (distinct solids)."""
    if len(mesh.faces) == 0:
        return 0
    components = trimesh.graph.connected_components(
        mesh.face_adjacency, nodes=np.arange(len(mesh.faces))
    )
    return len(components)


def validate_mesh(obj: MeshLike) -> ValidationResult:
    mesh = _as_mesh(obj)
    return ValidationResult(
        is_watertight=bool(mesh.is_watertight),
        non_manifold_edges=count_non_manifold_edges(mesh),
        body_count=count_bodies(mesh),
        volume_mm3=float(abs(mesh.volume)),
        bounds=(tuple(mesh.bounds[0]), tuple(mesh.bounds[1])),
    )


# ===========================================================================
# RNG-5: auto-repair
# ===========================================================================


@dataclass(frozen=True)
class RepairOutcome:
    """Result of a validate-then-repair pass over raw STL bytes.

    `stl_bytes` is what the backend should return: the repaired bytes when a
    repair pass ran and produced usable geometry, otherwise the raw input.
    """

    mesh_valid: bool
    mesh_repaired: bool
    detail: str
    stl_bytes: bytes


def _load_mesh_from_bytes(stl_bytes: bytes) -> trimesh.Trimesh:
    """Load STL bytes into a single Trimesh (force='mesh' so multi-solid STLs
    concatenate into one mesh with body_count > 1). Raises on failure."""
    mesh = trimesh.load(
        io.BytesIO(stl_bytes), file_type="stl", force="mesh"
    )
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError("empty mesh")
    return mesh


def repair_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Conservative, in-place cleanup. Never reshapes the solid (no voxel
    remesh, no convex hull, no mesh.process)."""
    mesh.merge_vertices()
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_winding(mesh)
    trimesh.repair.fix_normals(mesh)
    trimesh.repair.fill_holes(mesh)
    return mesh


def _build_detail(
    before: ValidationResult, after: ValidationResult
) -> str:
    """Compose a header-safe, fixed-vocabulary detail string. Never
    interpolates exception text or filesystem paths (AC9)."""
    parts = []
    if after.is_castable:
        if before.non_manifold_edges > 0:
            parts.append(f"filled {before.non_manifold_edges} holes")
        else:
            parts.append("merged duplicate geometry")
    else:
        if after.body_count > 1:
            parts.append(
                f"{after.body_count} disjoint bodies, not auto-repairable"
            )
        if not after.is_watertight:
            parts.append("mesh not watertight after repair")
    if not parts:
        parts.append("merged duplicate geometry")
    detail = "; ".join(parts)
    return (
        detail.encode("ascii", "ignore")
        .decode()
        .replace("\n", " ")
        .replace("\r", " ")[:_DETAIL_CAP]
    )


def validate_and_repair(stl_bytes: bytes) -> RepairOutcome:
    """Validate raw STL bytes and attempt conservative auto-repair if not
    castable. NEVER raises — the backend relies on this to avoid 500s."""
    try:
        mesh = _load_mesh_from_bytes(stl_bytes)
        before = validate_mesh(mesh)
        if before.is_castable:
            return RepairOutcome(True, False, "", stl_bytes)

        repair_mesh(mesh)
        if len(mesh.faces) == 0:
            logger.error(
                "mesh became empty after cleanup (before=%s)", before
            )
            return RepairOutcome(
                False, True, "mesh became empty after cleanup", stl_bytes
            )

        repaired_bytes = mesh.export(file_type="stl")
        after = validate_mesh(mesh)
        detail = _build_detail(before, after)
        if after.is_castable:
            logger.warning(
                "mesh repaired: %s (before=%s after=%s)",
                detail,
                before,
                after,
            )
        else:
            logger.error(
                "repair insufficient: %s (before=%s after=%s)",
                detail,
                before,
                after,
            )
        return RepairOutcome(after.is_castable, True, detail, repaired_bytes)
    except ValueError:
        logger.error("could not load mesh (empty)", exc_info=True)
        return RepairOutcome(False, False, "empty mesh", stl_bytes)
    except Exception:
        logger.error("mesh validation/repair failed", exc_info=True)
        return RepairOutcome(False, False, "could not load mesh", stl_bytes)
