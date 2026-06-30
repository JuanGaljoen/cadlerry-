# Watertight by construction (eliminate auto-repair reliance) (RNG-17)

> Type: feature (geometry hardening). Make the solitaire's raw, pre-repair
> geometry a single watertight manifold with zero non-manifold edges, so the
> RNG-5 auto-repair mesh gate becomes a safety net rather than a load-bearing
> crutch. Diagnosis (below) shows this is overwhelmingly a `prong_setting` fix.

## Problem

Today `/generate-ring` produces a solitaire whose RAW geometry is not watertight;
the RNG-5 `validate_and_repair` gate fills the holes on every request (QA observed
8-12 holes filled per solitaire, `X-Mesh-Repaired: true`). That is "repaired into
castability," not "built castable." Conservative repair (merge vertices, fill
holes, fix winding, no remesh) cannot be trusted to recover the many sub-0.7mm
features that the upcoming archetypes introduce (real per-accent halo settings in
RNG-9, pave beads in RNG-11). The foundation must be manifold by construction
before those land.

When this is done, the solitaire's raw STL (before any repair) is watertight with
zero non-manifold edges, and `X-Mesh-Repaired` is `false` for canonical in-range
inputs. Before this, every generation silently relied on hole-filling.

## Diagnosis (grounding — pre-build investigation, 2026-06-29)

Per-sub-solid raw (pre-repair) trimesh check on the canonical solitaire:

| Sub-solid | watertight | open (boundary) edges |
|-----------|-----------|-----------------------|
| `shank` (band loft) | yes | 0 |
| `seat` (torus) | yes | 0 |
| **`prong_setting`** | **no** | **12** |
| `compose(solitaire)` | no | 6 |

The band loft and the seat torus are already watertight by construction. The
non-manifoldness originates entirely in `prong_setting`: claws are built as
open-ended cones/cylinders (`_common.body_solid`, "no end caps") unioned with
sphere nodes at each joint; the sphere/cone tangencies leave 12 boundary edges
(≈ 2 per claw x 6 prongs). The final fuse nets 6 open edges. **Fixing
`prong_setting` is the bulk of this ticket.** A fast diagnostic loop exists
(scratchpad `rng17_diag.py`): build each sub-solid, export raw STL, count
boundary edges via trimesh; this is the build's pass/fail signal.

## Acceptance Criteria

- **AC1 — prong_setting watertight by construction.** `prong_setting(spec, c)`
  raw STL (pre-repair) is watertight with **zero boundary/non-manifold edges** and
  a single body, across the parametric range (prong_count in {4,6}, stone_diameter
  2-10mm, setting_height 3-8mm). Asserted directly on `to_stl_bytes(...)` without
  calling `validate_and_repair`.
- **AC2 — compose(solitaire) watertight by construction.** `to_stl_bytes(compose(spec))`
  is watertight, zero non-manifold edges, single body, **before** `validate_and_repair`
  runs, across the same range.
- **AC3 — repair becomes a no-op on canonical input.** `POST /generate-ring` with
  canonical in-range params returns `X-Mesh-Repaired: false` and `X-Mesh-Valid: true`.
  (Repair is still attempted/effective on genuinely degenerate input — AC5.)
- **AC4 — parity preserved.** The RNG-13 characterization parity test stays green
  (bbox within 0.5mm, volume within 5%); the visible solitaire is unchanged within
  tolerance. `tests/test_geometry_parity.py` is not weakened.
- **AC5 — repair retained as safety net.** `validate_and_repair` still runs on the
  response path and still repairs a deliberately degenerate mesh (existing RNG-5
  behavior + tests intact); the never-500 discipline holds.
- **AC6 — per-module castability self-checks still pass.** The RNG-16
  `check_*` self-checks pass on the raw (now-watertight) geometry across the range.
- **AC7 — full suite green**, including the new raw-watertight assertions.

## Approach

Diagnosis-driven and tightly scoped (chosen):

1. **Rebuild the claw/peg solids in `prong_setting` to be closed by construction.**
   Replace the open-ended-cone + sphere-node union with closed solids fused with a
   small epsilon overlap so no tangency-only contact remains. Two viable shapes for
   the architect to pick (both satisfy the ACs; choose the simpler that holds parity):
   - **(a) Swept claw:** sweep a circular profile along the claw polyline
     (base→girdle→rise→tip) as one closed solid with a rounded/hemispherical tip
     cap; the peg a closed cone. Cleanest topology, fewest booleans.
   - **(b) Capped-primitive union with epsilon overlap:** keep spheres + cones but
     give cone bodies real end caps and overlap each joint by epsilon so unions are
     volumetric, not tangent. Smaller diff from current code.
   Recommend (a) if parity holds; fall back to (b) if (a) shifts the silhouette
   beyond the parity tolerance.
2. **Keep `shank` and `seat` unchanged** — they are already watertight (diagnosis).
   No shell/offset work needed there; scope creep avoided.
3. **Ensure the final compose fuse is clean** — epsilon overlap between
   prong_setting/seat/shank at the head so the union has no coplanar contact.
4. **Leave `validate_and_repair` and the endpoint flow intact** — once raw geometry
   is watertight, `repaired` naturally reports `false` (nothing to fix). No mesh-gate
   logic change required.

Rejected: a blanket `shell()`/`offset` rebuild of every module (unnecessary — band
and seat are already manifold; would risk parity and add cost for no benefit).

## Edge Cases

- **prong_count 4 vs 6:** both must be watertight raw (claw count changes the joint
  count; the fix must hold for both).
- **Small stone_diameter (2mm):** claws are tighter/smaller; tip cap must stay
  >= 0.7mm and closed.
- **Large setting_height (8mm):** longer claw rise; sweep/segments must remain
  closed over the longer path.
- **Degenerate input (e.g. forced thin/zero feature):** AC5 — repair still engages;
  no 500.
- **Parity boundary:** if the new claw shape moves bbox/volume beyond RNG-13
  tolerance, that is a fail to resolve (tune profile), not a tolerance loosening.

## Constraints

- Casting invariants unchanged: min wall 0.8mm, min prong tip 0.7mm; single
  watertight manifold; zero non-manifold edges on the shipped STL.
- Casting constants imported from `ringcad.mesh_validator` (single source).
- Behavior-preserving within RNG-13 parity tolerances; `/generate-ring` output for
  the solitaire is visually unchanged.
- Max 300 non-blank LOC per source file (hook-enforced). `prong_setting.py` is ~39
  LOC, `_common.py` ~87 — room to grow, but split helpers if needed.
- No new runtime dependencies. TDD: RED -> GREEN -> REFACTOR.
- Performance: generation time must not materially regress (a sweep may add kernel
  work; keep it within ~20% of current solitaire generation time).

## Scope Boundaries

**In scope:**
- Rebuilding `prong_setting` claw/peg geometry to be watertight by construction.
- Clean epsilon-overlap fuse in `compose` for the solitaire.
- New tests asserting RAW (pre-repair) watertightness + zero non-manifold edges for
  `prong_setting` and `compose(solitaire)`.
- A reusable raw-watertight test helper (build123d solid -> trimesh -> boundary-edge
  count) other modules/archetypes can use.

**Out of scope (deferred):**
- New archetypes/modules (RNG-9/10/11) — but they inherit the by-construction bar.
- `bezel` raw-watertight hardening — bezel has no production archetype yet; harden it
  when RNG-9 (or a later ticket) makes it user-reachable. (Note if trivial to include.)
- Removing `validate_and_repair` (it stays as the safety net).
- Aggressive remeshing (voxel/marching-cubes) — forbidden by casting fidelity (RNG-5).

## Success Metrics

- `prong_setting` and `compose(solitaire)` raw STL: 0 non-manifold edges, watertight,
  single body, for 100% of in-range inputs tested.
- `X-Mesh-Repaired: false` on canonical `/generate-ring` requests (was `true`).
- Parity test green; full suite green.
- Generation time within ~20% of pre-change baseline.

## Design Notes + Dependencies

- **Files (anticipated):** `ringcad/geometry/prong_setting.py` (claw/peg rebuild),
  `ringcad/geometry/_common.py` (sweep/closed-primitive helpers; possibly retire or
  cap `body_solid`), `ringcad/geometry/module.py`/`solitaire.py` (epsilon fuse if
  needed), tests: `tests/test_geometry_watertight.py` (new, raw-watertight per module
  + compose), reuse the diagnostic from scratchpad `rng17_diag.py` as the seam.
- **Depends on:** RNG-16 (module library + per-module self-checks) — Done.
- **Blocks:** RNG-9 (real per-accent halo settings build on this), and RNG-11 (pave).
- **Build's pass/fail loop:** the boundary-edge count on raw geometry (deterministic,
  fast). Treat this as a castability "bug" with a loop, per the Fix discipline.
