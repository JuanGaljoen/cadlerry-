# Geometry kernel migration: OpenSCAD → build123d (solitaire cutover) (RNG-15)

> The architectural pivot. Route `/generate-ring` through an in-process build123d
> B-rep generator driven by RingSpec, decompose the solitaire into modules, expose
> STEP, and retire the OpenSCAD subprocess path. Type: migration (strangler-fig).
> Depends on RNG-13 (build123d GO — done) and RNG-14 (RingSpec v1 — done).

## Problem

`/generate-ring` shells out to the `openscad` CLI to render `scad/solitaire.scad`
(`ringcad/app.py:86`, `ringcad/render.py`). That subprocess boundary blocks the
"any ring" roadmap: no real 3D wall-thickness (`shell`), no first-class
fillet/sweep/loft, no B-rep curved surfaces, no in-kernel introspection, STL-only
export. RNG-13 proved build123d reproduces the solitaire within tolerance and adds
`shell()` + STEP. RNG-14 gave us the typed RingSpec contract. This ticket cuts the
live endpoint over to the new kernel and removes the old one.

When this is done: `/generate-ring` builds the solitaire in-process via build123d
from a RingSpec, validates castability *before* geometry, returns STL or STEP, and
the OpenSCAD CLI dependency is gone. Validation is unified on Pydantic (RingSpec);
the hand-rolled `params.py` validator is retired.

## Acceptance Criteria

1. **build123d-backed endpoint.** `/generate-ring` produces the solitaire via an
   in-process build123d generator (no `openscad` subprocess). The request is
   validated and adapted through RingSpec (`from_params` → `validate_castability`
   → build), not the legacy `validate_params`.
2. **Characterization parity green.** A parity test pins the OpenSCAD reference
   metrics (bbox, volume, manifold, min-thickness) and asserts the build123d
   output matches within the RNG-13 tolerances (bbox ≤ 0.5mm/axis, volume ≤ 5%).
   The test compares both generators directly on identical params.
3. **Decomposed, not monolithic.** The solitaire is expressed as a composition of
   discrete module functions — `shank()`, `prong_setting()`, `seat()` — in
   `ringcad/geometry/`, unioned into one solid by a `build_solitaire(spec)`
   composer. (Formalizing a generic RingSpec-slice module *interface* + bezel +
   composition registry is RNG-16.)
4. **In-kernel castability + clean export.** Castability is enforced before/within
   geometry (RingSpec `validate_castability` gate + `shell`/`offset` min-wall by
   construction where the spike proved it). The **shipped** STL has zero
   non-manifold edges (via the existing `validate_and_repair` gate, which welds the
   spike's boolean-tangency seams with zero volume change). STEP export is
   available via `/generate-ring?format=step`.
5. **OpenSCAD removed.** `scad/solitaire.scad`, `ringcad/render.py` (the subprocess
   wrapper), and the `openscad`-availability checks/branches in `app.py` are
   deleted. No code path invokes `openscad`.
6. **Suite green.** The full existing test suite passes after cutover, including
   `tests/test_backend.py` rewired to the new generator seam (no `render_scad`/
   `openscad_stderr` coupling) and `tests/test_geometry.py` retargeted at build123d.

## Approach (strangler-fig, direct cutover)

Parity is already proven (RNG-13), so we skip a runtime kernel flag: the
characterization parity test (AC2) is the gate, and git is the rollback. Phases:

1. **Add (new path beside old).** Promote the spike generator into the package:
   `ringcad/geometry/{shank,prong_setting,seat}.py` + `solitaire.py`
   (`build_solitaire(spec: RingSpec) -> Solid`) + `export.py` (`to_stl_bytes`,
   `to_step_bytes`). Lift the spike's `_band` → `shank()`, `_setting_solids` →
   `prong_setting()` + `seat()`. Constants imported from `ringcad.mesh_validator`.
   Old OpenSCAD path still live; nothing in `app.py` changes yet.
2. **Characterize.** Parity test (AC2) compares `build_solitaire` STL vs the
   OpenSCAD render on identical params within RNG-13 tolerances. Pin reference
   metrics so the test is deterministic without re-rendering OpenSCAD every run.
3. **Cut over.** Rewire `/generate-ring`: `from_params(body)` → RingSpec →
   `validate_castability` (400 with structured violations if non-castable) →
   `build_solitaire` → export STL or STEP per `?format=` → `validate_and_repair`
   → `Response`. Make the 7-param `validate_params` a thin shim over RingSpec
   (`from_params`) so all validation is Pydantic; preserve the existing 400 error
   contract shape where tests/clients depend on it (map Pydantic errors → the
   `{error, detail, field}` JSON). Update `test_backend.py` to the new seam.
4. **Remove.** Delete `scad/solitaire.scad`, `ringcad/render.py`, the
   `openscad_available` import/branches, and retire the hand-rolled validation in
   `ringcad/params.py` (keep a thin `validate_params` adapter only if callers need
   it; otherwise delete and update imports). Drop `RENDER_FN`/OpenSCAD env plumbing.

## Edge Cases

| Case | Expected behavior |
|------|-------------------|
| Non-castable params (e.g. band_thickness 0.6) | 400 with structured `validate_castability` violations (named field) — caught *before* geometry |
| `prong_count ∉ {4,6}` | 400 at RingSpec schema validation (RNG-14 already rejects) |
| `?format=step` | STEP bytes, `model/step` mimetype, `ring.step` filename |
| `?format` absent or `stl` | STL bytes (current behavior), mesh headers preserved |
| build123d raises / degenerate solid | 400 JSON with a generic geometry-failure message (no subprocess stderr to surface) |
| Mesh not watertight after build | `validate_and_repair` welds seams; `X-Mesh-*` headers reflect repair, as today |
| OpenSCAD not installed | No longer relevant — the 503 openscad pre-check is removed |

## Constraints

- No new top-level dependencies (build123d, trimesh, pydantic all present).
- ≤300 LOC per file — split `ringcad/geometry/` per module.
- Casting constants referenced from `ringcad.mesh_validator`, never duplicated.
- mm units, floats throughout.
- Preserve the `/generate-ring` success response shape (binary body + `X-Mesh-*`
  headers) and the 400 `{error, detail, field}` error shape for STL requests.
- The frontend (form + Three.js viewer) must keep working unchanged for STL; STEP
  is additive (a later "Download STEP" button is out of scope here).

## Scope Boundaries

**In scope:** in-process build123d solitaire generator decomposed into
shank/prong_setting/seat module functions; RingSpec-driven endpoint; castability
gate; STL+STEP export; characterization parity test; OpenSCAD removal; params.py
retirement; test suite rewire.

**Out of scope (with reason):**
- Generic module *interface* (RingSpec-slice contract), bezel module, composition
  registry, by-construction zero-nme manifold → RNG-16.
- Other archetypes (halo/trilogy/side-stone) → RNG-9/10/11 via RNG-16.
- Vision populating RingSpec; confidence consumption → RNG-12.
- Frontend "Download STEP" button / viewer changes → follow-up.

## Success Metrics

- `/generate-ring` returns a build123d-generated solitaire; zero `openscad`
  invocations anywhere in the codebase (grep-clean).
- Characterization parity test green within RNG-13 tolerances.
- Shipped STL has zero non-manifold edges; STEP downloads and re-imports as a
  positive-volume solid.
- Full existing test suite green after cutover.

## Dependencies

- RNG-13 (build123d GO) — done. Spike source at `spikes/rng13/` is the geometry
  starting point (`b123d_solitaire.py`, construction lessons in `FINDINGS.md`).
- RNG-14 (RingSpec v1) — done. Endpoint consumes `from_params` /
  `validate_castability` / `to_params` from `ringcad.ringspec`.

## Build sizing

5 ACs, ~8–10 files touched (new `ringcad/geometry/` package + `app.py` rewire +
params.py retirement + 2–3 test files + deletions), 2–3 codebase areas (geometry,
endpoint, tests). **Two signals at the worker threshold (files ≥5, ACs ≥4) →
candidate for worker mode**, but the work is tightly sequential (strangler-fig
phases gate each other), so direct mode with disciplined phasing is reasonable.
Decide at build time.

## Open follow-ups (RNG-16)

- By-construction manifold (guaranteed junction overlaps / fillets) to drop the
  raw 12 non-manifold edges before the repair gate.
- Pin the `min_prong_tip` castability proxy (`pi*stone_diameter/prong_count*0.25`)
  against the real build123d prong geometry — the one approximate number from RNG-14.
