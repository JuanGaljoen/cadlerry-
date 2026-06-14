# RNG-5: Trimesh mesh validation and auto-repair

**Type:** feature
**Ticket:** RNG-5 (Medium, backend + frontend)
**Depends on:** RNG-2 (done) — `/generate-ring`, `ringcad.app`, `ringcad.render`
**Reuses:** RNG-1 (done) — `ringcad.mesh_validator` (`validate_mesh`, `ValidationResult`)
**Touches frontend:** RNG-3 (`static/app.js`, `templates/index.html`)

## Problem

**Who:** anyone generating a ring to cast via lost-wax, plus the app itself,
which today returns whatever OpenSCAD produced with no manufacturing check.

**What:** `/generate-ring` (RNG-2) renders an STL and streams it back with zero
validation. RNG-1's `mesh_validator` can *detect* whether a mesh is a single
watertight manifold, but nothing calls it on the response path, nothing attempts
repair when a mesh fails, and the client has no signal about castability. A
non-watertight or multi-body STL fails silently at the casting house.

**Why now:** the casting constraints in `CLAUDE.md` (single watertight manifold,
zero non-manifold edges) are declared "enforced in geometry, not just UI hints"
but are currently unenforced at the API boundary. RNG-2 explicitly deferred this
to RNG-5. The frontend (RNG-3) already has a place for a mesh-status indicator in
its design but no data to drive it.

**Future state:** When this is done, a user gets every generated STL back *with*
a castability verdict, and an auto-repair pass has already tried to fix common
topology faults before they ever download. Before this, they downloaded an
unvalidated STL and discovered defects only at the caster. The key difference is
the mesh is checked and best-effort-repaired on every generation, and the result
is surfaced honestly in the UI.

## Approach

**Chosen approach:** extend `ringcad.mesh_validator` with a conservative repair
pass, call validate -> repair -> re-validate inside `/generate-ring` after a
successful render, and ship the verdict as **response headers** on the existing
binary STL body. The frontend reads the headers and renders a green/red status
indicator above the download button. Download always works.

Decisions taken at planning:

1. **Verdict travels as response headers, not a JSON envelope.** Keep RNG-2's
   binary `model/stl` body untouched. Add `X-Mesh-Valid`, `X-Mesh-Repaired`, and
   `X-Mesh-Repair-Detail` headers. This preserves the streaming contract, avoids
   ~33% base64 bloat, and keeps the frontend's `res.blob()` path intact (it just
   reads two headers first). Rejected: JSON `{mesh_valid, mesh_repaired,
   stl_base64}` envelope — breaks the RNG-2 contract and bloats the payload.
2. **`mesh_valid` means fully castable, not merely watertight.** Reuse
   `ValidationResult.is_castable` = `is_watertight AND non_manifold_edges == 0 AND
   body_count == 1`. This matches the lost-wax constraints in `CLAUDE.md`.
   Reporting "valid" for a watertight-but-multi-body mesh would be a manufacturing
   lie. Rejected: watertight-only (the literal AC wording) as too loose.
3. **Auto-repair is conservative topology cleanup only — it never reshapes the
   part.** Apply, in order: `merge_vertices`, remove duplicate faces, remove
   degenerate faces, fix winding / normals, `fill_holes`. Then re-validate. No
   voxel remesh, no convex-hull fallback: those force watertightness at the cost
   of altered dimensions, which is unacceptable for a casting where 0.8mm walls
   and 0.7mm prong tips are load-bearing. Rejected: voxel remesh fallback.
4. **Validation/repair must never break the endpoint.** The whole pass is wrapped
   so that any trimesh failure (unloadable/corrupt STL, repair exception) is
   logged and degrades to `mesh_valid=false, mesh_repaired=false` with the raw
   STL bytes still returned. Generation never turns into a 500 because of
   validation.

### Repair / response flow

```
render OK -> load STL with trimesh
  load fails            -> valid=false, repaired=false, log ERROR(detail), return raw bytes
  load OK -> validate (is_castable?)
    castable            -> valid=true,  repaired=false, return raw bytes
    not castable        -> repair() -> re-validate
        now castable    -> valid=true,  repaired=true,  log WARNING(what was fixed), return repaired bytes
        still not       -> valid=false, repaired=true,  log ERROR(detail), return repaired bytes
```

`mesh_repaired=true` means a repair pass was applied to the bytes being returned
(the mesh was not castable as rendered). Because repair is non-reshaping, the
repaired bytes are always >= the raw bytes in quality, so we return them even
when the mesh is still not castable (best effort). `X-Mesh-Repair-Detail` carries
a short sanitized summary (e.g. `"filled 2 holes; 1 body remains"` or
`"2 disjoint bodies, not auto-repairable"`).

### Files

| Path | Change |
|------|--------|
| `ringcad/mesh_validator.py` | Add `repair_mesh(mesh) -> (mesh, repaired: bool, detail: str)` and a `validate_and_repair(obj) -> RepairOutcome` helper. Keep under 300 LOC (currently 79). |
| `ringcad/app.py` | After successful render, run `validate_and_repair`; set `X-Mesh-Valid` / `X-Mesh-Repaired` / `X-Mesh-Repair-Detail` headers; write repaired bytes when repaired; module logger for WARNING/ERROR. |
| `templates/index.html` | Add `#mesh-status` element above `#download-btn` (role=status, aria-live=polite). |
| `static/app.js` | On 200, read the three headers, render the status indicator (text + color, not color alone), then proceed with existing blob/download/viewer path. Watch 300 LOC cap. |
| `static/styles.css` | `.mesh-status--valid` (green) / `.mesh-status--invalid` (red) styles. CSS is exempt from the LOC cap. |
| `tests/test_mesh_validator.py` | Repair unit tests (RED): holed box repairs to castable; two disjoint boxes stay invalid + detail; already-castable box untouched. |
| `tests/test_backend.py` | Header tests: castable mesh -> `X-Mesh-Valid: true`, no repair; invalid mesh -> repaired header + 200 + body present; unloadable bytes -> valid=false, 200, raw bytes. |
| `tests/test_frontend.py` | Indicator renders valid/invalid from headers; download button shown and working when `mesh_valid=false`. |

`ringcad/render.py` and `ringcad/params.py` are unchanged.

## Acceptance Criteria

- [ ] **AC1 — Validate every successful generation.** After a successful render,
  `/generate-ring` loads the STL and evaluates castability via
  `mesh_validator` (`is_castable`: watertight, zero non-manifold edges, single
  body) before responding. No success response skips validation.
- [ ] **AC2 — Auto-repair attempted when not castable.** When the rendered mesh
  is not castable, a conservative repair pass (`merge_vertices`, remove
  duplicate/degenerate faces, fix winding/normals, `fill_holes`) runs and the
  mesh is re-validated. Repair never voxel-remeshes or otherwise reshapes the
  part.
- [ ] **AC3 — Response carries `mesh_valid` and `mesh_repaired`.** A 200 response
  includes `X-Mesh-Valid` (`true`/`false`, reflecting castability after any
  repair) and `X-Mesh-Repaired` (`true`/`false`, whether a repair pass was
  applied to the returned bytes). `X-Mesh-Repair-Detail` carries a short summary
  when relevant.
- [ ] **AC4 — UI shows green valid / red invalid above the download button.** On
  a successful generation the frontend renders a mesh-status indicator above
  `#download-btn`: green for valid, red for invalid, conveyed by text/icon as
  well as color (WCAG 1.4.1, not color alone).
- [ ] **AC5 — Download works regardless of validation status.** The Download STL
  button appears and functions on every 200 response, whether `mesh_valid` is
  true or false. Validation never blocks or hides the download.
- [ ] **AC6 — Repair failure logged with detail.** When repair runs but the mesh
  is still not castable (or the STL cannot be loaded/repaired), the server logs
  at ERROR with detail: which checks failed and the relevant counts
  (`is_watertight`, `non_manifold_edges`, `body_count`) before and after. A
  successful repair logs at WARNING with what was fixed.
- [ ] **AC7 — Validation never breaks generation.** Any trimesh load/repair
  exception is caught and logged; the endpoint still returns 200 with the raw STL
  bytes and `X-Mesh-Valid: false`. No 500 from the validation path.

## Edge Cases

| Case | Expected behavior |
|------|-------------------|
| Mesh castable as rendered (the golden default ring) | 200, `X-Mesh-Valid: true`, `X-Mesh-Repaired: false`, raw bytes returned |
| Mesh has surface holes / open boundary | repair `fill_holes` -> re-validate; if castable, `valid=true`, `repaired=true`, repaired bytes returned |
| Mesh has non-manifold edges from coincident geometry | `merge_vertices` / remove-duplicate may resolve; re-validate decides `valid` |
| Mesh is two or more disjoint bodies | conservative repair cannot merge bodies; `valid=false`, `repaired=true`, detail `"N disjoint bodies, not auto-repairable"`, ERROR logged, 200 + download |
| STL bytes unloadable / corrupt / zero-length | `valid=false`, `repaired=false`, detail names the load failure, ERROR logged, raw bytes still returned, 200 |
| Repair raises an exception | caught, ERROR logged, `valid=false`, `repaired=false`, raw bytes returned, 200 (AC7) |
| Render itself failed (RNG-2 path) | unchanged: 400 with `openscad_stderr`; no validation runs |
| Concurrent requests | validator/repair are pure functions over a per-request mesh; no shared state |

## Constraints

- **Performance:** validation + repair on a ring mesh (a few thousand faces at
  `$fn` 24) is sub-second; budget < 2s added on top of the OpenSCAD render
  (~20-50s, dominated by the union). Record the actual added latency in the build
  report. No async work introduced.
- **Accessibility:** WCAG 2.1 AA. The status indicator must not rely on color
  alone (1.4.1): pair green/red with text and/or an icon. `#mesh-status` uses
  `role="status"` + `aria-live="polite"` so the verdict is announced on
  generation without stealing focus from the download button.
- **Security:** `X-Mesh-Repair-Detail` is a fixed-vocabulary summary built from
  counts, never raw exception text or file paths, so no internals leak via the
  header. No new input surface.
- **Compatibility:** RNG-2's success contract is preserved exactly (200,
  `model/stl`, `attachment; filename="ring.stl"`, binary body). The headers are
  purely additive; an HTTP client that ignores them still gets a valid STL.
- **Patterns to follow:** `ValidationResult` / `is_castable` stay the single
  source of truth for castability (do not re-derive checks in `app.py`). Mirror
  RNG-2's "never 500 on the response path" discipline. Module-level `logging`
  logger, not prints.
- **LOC:** max 300 non-blank LOC per source file (hook-enforced). `app.js` is
  near the budget — keep the header-reading + indicator logic tight or extract a
  helper.

## Scope

**In scope:**
- `repair_mesh` + `validate_and_repair` in `ringcad.mesh_validator`.
- Validation + repair wired into `/generate-ring`, with the three response
  headers and structured logging.
- Frontend mesh-status indicator driven by the headers; download works regardless.
- Unit tests (repair), backend tests (headers/flow), frontend tests (indicator +
  download-regardless).

**Out of scope (deferred):**
- Exposing full mesh metrics (volume, bounds, exact non-manifold-edge count) to
  the UI — only valid/invalid + a short repair detail are surfaced. The richer
  `ValidationResult` stays server-side.
- Re-rendering at higher `$fn` or changing SCAD geometry to improve castability —
  RNG-5 validates and repairs the produced mesh, it does not change generation.
- Aggressive remeshing (voxel / marching-cubes / convex hull) — explicitly
  rejected for casting fidelity (see Approach decision 3).
- Async job queue / progress for the (small) added validation time — not needed.
- Photo classification (`/classify-ring`) — RNG-6.

## Success Metrics

| Metric | Target | Measure After |
|--------|--------|---------------|
| Golden default ring castability on first pass (no repair) | `mesh_valid=true`, `mesh_repaired=false` | Build (validates SCAD is castable by construction) |
| Holed-mesh fixture after repair | `mesh_valid=true`, `mesh_repaired=true` | Build (repair unit test) |
| Validation-path 500s | 0 (every malformed/unloadable mesh still returns 200 + download) | Build |
| Added latency (validate + repair) for default ring | < 2s on top of render | Build (recorded in report) |

## Test Plan

TDD, RED first. Tests that need OpenSCAD are gated on `openscad_available()`;
validator/repair and frontend tests run with no binary.

- **`tests/test_mesh_validator.py` (no OpenSCAD):**
  - Already-castable box -> `validate_and_repair` returns `repaired=false`,
    `is_castable=true`, geometry unchanged.
  - Box with a dropped face (open hole) -> `repaired=true`, re-validates to
    castable, detail mentions holes filled.
  - Two disjoint boxes -> `repaired=true` but still not castable, `body_count==2`,
    detail names disjoint bodies.
- **`tests/test_backend.py` (mostly no OpenSCAD via monkeypatch):**
  - Monkeypatch the render to drop in a known castable STL -> 200,
    `X-Mesh-Valid: true`, `X-Mesh-Repaired: false`, body is a loadable STL.
  - Monkeypatch render to drop in an invalid (multi-body) STL -> 200,
    `X-Mesh-Repaired: true`, `X-Mesh-Valid: false`, body present, download usable.
  - Unloadable bytes -> 200, `X-Mesh-Valid: false`, raw bytes returned, no 500.
  - OpenSCAD-gated: real default-ring render -> `X-Mesh-Valid: true`.
- **`tests/test_frontend.py`:**
  - 200 with `X-Mesh-Valid: true` -> green status text rendered above download,
    download button visible.
  - 200 with `X-Mesh-Valid: false` -> red status text, download button still
    visible and href set (AC5).

## Dependencies

- RNG-2 endpoint and app factory (`ringcad.app.create_app`).
- RNG-1 `ringcad.mesh_validator` (`validate_mesh`, `ValidationResult`,
  `count_non_manifold_edges`, `count_bodies`).
- `trimesh` + `numpy` (already pinned via RNG-1).
- No new runtime dependencies.

## Validation (planning decisions)

- **Header transport vs JSON envelope:** headers. Preserves the RNG-2 binary
  contract, no base64 bloat, minimal frontend change. (User-confirmed.)
- **`mesh_valid` = full castable vs watertight-only:** full `is_castable`. Matches
  the lost-wax constraints; watertight-only would mislabel uncastable meshes as
  valid. (User-confirmed.)
- **Repair aggressiveness:** conservative topology repair only, no voxel remesh.
  Casting fidelity (0.8mm walls, 0.7mm prong tips) forbids silent reshaping.
  (User-confirmed.)
- **Return repaired bytes even when still invalid:** yes — non-reshaping repair is
  never worse than the raw mesh, so best-effort bytes go back with an honest
  `mesh_valid=false`.
