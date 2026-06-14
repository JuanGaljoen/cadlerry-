# RNG-2: Flask backend with STL generation endpoint

**Type:** feature
**Ticket:** RNG-2 (Highest, backend)
**Depends on:** RNG-1 (done) — `scad/solitaire.scad`, `ringcad.render`, `ringcad.mesh_validator`
**Blocks:** RNG-3 (frontend form), RNG-5 (mesh validation + auto-repair)

## Problem

The parametric ring geometry (RNG-1) can only be rendered from the command line
today. There is no way for a UI, or any HTTP client, to turn ring parameters
into an STL. Without a backend, RNG-3's form has nothing to POST to and the app
cannot produce a downloadable model.

When this is done, an HTTP client can POST the 7 ring parameters as JSON to
`/generate-ring` and receive a binary STL rendered from `solitaire.scad`. Before
this, the only way to render was a manual `openscad` CLI invocation.

## Approach

A small Python + Flask server that wraps the existing RNG-1 toolchain. The
endpoint validates input, calls `ringcad.render.render_scad` (single source of
truth for the OpenSCAD subprocess), and streams the resulting STL back.

Decisions taken at planning (see Validation note below for rationale):

1. **Synchronous request/response, lower `$fn`.** The endpoint blocks until the
   STL is ready. Render at a reduced `$fn` (default 24, env-overridable) to keep
   latency toward the low end of the documented range. No async job queue in
   RNG-2.
2. **No mesh validation in RNG-2.** The endpoint renders and returns the STL.
   Watertightness checks, auto-repair, and the `mesh_valid` / `mesh_repaired`
   response flags are RNG-5's scope.
3. **Whitelist + type-check input, pass values through to the SCAD.** Accept only
   the 7 known parameter names; reject unknown keys (prevents `-D` injection);
   require all 7; coerce to numeric; 400 on missing or non-numeric. Out-of-range
   values are NOT rejected — the SCAD clamps them by construction. `prong_count`
   is passed through; the SCAD snaps non-{4,6} values to 4 and warns on stderr.
4. **Reuse `ringcad.render` as-is.** No new subprocess code. `OPENSCAD_BIN` is
   resolved from env by `render.py` (already supported).

### Files

| Path | Change |
|------|--------|
| `app.py` (or `ringcad/app.py`) | New Flask app: `/generate-ring`, `/health`, app factory. |
| `ringcad/params.py` (new) | Parameter whitelist, required-set, type coercion, validation errors. Keeps `app.py` under the 300 LOC cap. |
| `requirements.txt` | Add `flask` (pinned). |
| `tests/test_backend.py` (new) | Endpoint tests (see Test Plan). |
| `conftest.py` | Flask test client fixture if not already present. |

`render.py` and `mesh_validator.py` are unchanged.

## Acceptance Criteria

1. **AC1 — POST /generate-ring accepts all 7 params as JSON.** A POST with a JSON
   body containing `inner_diameter`, `band_width`, `band_thickness`,
   `stone_diameter`, `stone_height`, `prong_count`, `setting_height` (all numeric)
   is accepted and triggers a render.
2. **AC2 — Renders via solitaire.scad through render.py.** The endpoint calls
   `ringcad.render.render_scad` against `scad/solitaire.scad`, injecting the 7
   params via `-D`. No inline subprocess call.
3. **AC3 — Returns binary STL on success.** On `RenderResult.ok`, responds `200`
   with the STL bytes, `Content-Type: model/stl`, and
   `Content-Disposition: attachment; filename="ring.stl"`. Response body is a
   valid STL loadable by trimesh.
4. **AC4 — Returns OpenSCAD stderr on failure with 400.** When the render fails
   (`returncode != 0` or zero-byte output), responds `400` with a JSON body
   `{"error": "...", "openscad_stderr": "<stderr>"}` containing the captured
   OpenSCAD stderr.
5. **AC5 — GET /health returns {"status": "ok"}.** `200`, JSON body exactly
   `{"status": "ok"}`.
6. **AC6 — Missing or invalid params handled gracefully.** Missing required
   param, non-numeric value, unknown key, malformed/empty JSON, or wrong
   content-type each return `400` with a JSON `{"error": "...", "detail": "..."}`
   naming the offending field. No 500, no stack trace leaked to the client.
7. **AC7 — Render timeout handled.** A render exceeding the configured timeout
   (default 120s) returns `400` with a JSON body indicating a timeout, not a
   hung connection or 500.
8. **AC8 — OpenSCAD-unavailable handled.** If the OpenSCAD binary is not
   resolvable (`openscad_available()` is false), `/generate-ring` returns `400`
   (or `503`) with a clear JSON message; `/health` still returns `200`.

## Edge Cases

| Case | Expected behavior |
|------|-------------------|
| Body missing one of the 7 params | 400, `error` names the missing field |
| Param present but non-numeric (`"abc"`, `null`) | 400, `error` names the field |
| Unknown extra key (e.g. `"$fn"`, `"cmd"`) | 400, rejected (no pass-through to `-D`) |
| `prong_count` = 5 (not in {4,6}) | 200; SCAD snaps to 4, warns on stderr (not surfaced as an error) |
| Oversized stone (e.g. `stone_diameter` 20) | 200; SCAD warns but renders a castable mesh |
| Empty body / not JSON / wrong content-type | 400, `error` explains expected JSON |
| OpenSCAD returns non-zero | 400 with `openscad_stderr` |
| OpenSCAD exceeds timeout | 400 timeout message (AC7) |
| OpenSCAD binary missing | 400/503 clear message (AC8) |
| Concurrent requests | Each renders to a unique temp STL path; no cross-request file collision; temp file removed after response |

## Constraints

- **Latency:** synchronous; render dominated by OpenSCAD (~20-50s depending on
  `$fn` and the basket union). `$fn` default 24 via `RENDER_FN` env. Subprocess
  timeout default 120s via env. The basket boolean union is the documented
  bottleneck; lowering `$fn` yields only modest gains. Further latency reduction
  is explicitly deferred.
- **Security:** parameter names are whitelisted before reaching `render_scad`, so
  no caller-controlled `-D` flag can be injected. `render.py` already uses
  `subprocess.run` with an argument list (no shell). No filesystem paths accepted
  from the client. Errors return sanitized JSON, never a Python traceback.
- **Patterns to follow:** `ringcad.render.RenderResult` (`.ok`, `.stderr`) is the
  success/failure contract. Mirror RNG-1's "return even on failure so the caller
  can read stderr" design.
- **LOC:** max 300 non-blank LOC per file (hook-enforced). Split param validation
  into `ringcad/params.py`.
- **No JS frameworks / no frontend in this ticket** (RNG-3).

## Scope Boundaries

**In scope:** `/generate-ring`, `/health`, input validation, OpenSCAD invocation
via `render.py`, binary STL response, error handling, backend tests.

**Out of scope (deferred):**
- Mesh validation, auto-repair, `mesh_valid`/`mesh_repaired` flags → **RNG-5**.
- Frontend form, Three.js viewer, download button → **RNG-3 / RNG-4**.
- Photo classification (`/classify-ring`) → **RNG-6**.
- Async job queue / progress polling → deferred; revisit if synchronous latency
  becomes a UX problem.
- Exposing `shank_taper` or other non-canonical shaping params → not in the
  7-param contract; uses SCAD default.
- Production WSGI server / deployment hardening → later.

## Success Metrics

- `/generate-ring` returns a trimesh-loadable STL for the golden default ring in
  a single request (functional).
- 400 (not 500) for every malformed-input case in the Edge Cases table.
- End-to-end render latency recorded in the build report for the default ring at
  the chosen `$fn` (baseline for any future RNG perf work).

## Test Plan

Backend tests in `tests/test_backend.py` using Flask's test client. Tests that
invoke OpenSCAD are gated on `openscad_available()` (skip if absent) so the suite
runs in CI without the binary; validation/error-path tests run unconditionally
with no OpenSCAD dependency.

- `/health` returns 200 + `{"status": "ok"}` (no OpenSCAD needed).
- Valid 7-param POST → 200, `model/stl` content-type, attachment disposition,
  body loads in trimesh (OpenSCAD-gated).
- Missing param / non-numeric / unknown key / empty body / wrong content-type →
  400 each, error names the field (no OpenSCAD needed; validation happens first).
- Render failure path → 400 with `openscad_stderr` (simulate via a deliberately
  bad param or by monkeypatching `render_scad` to return a failing `RenderResult`).
- OpenSCAD-unavailable path → 400/503 (monkeypatch `openscad_available`).
- `prong_count=5` accepted (200) and warning appears in captured stderr
  (OpenSCAD-gated).

## Dependencies

- RNG-1 artifacts: `scad/solitaire.scad`, `ringcad.render`, `ringcad.mesh_validator`.
- New runtime dep: `flask` (pinned in `requirements.txt`).
- OpenSCAD binary resolved via `OPENSCAD_BIN` (env, default `openscad` on PATH).

## Validation (planning decisions)

- **Sync vs async:** synchronous + lower `$fn`. Personal single-user app; an async
  job queue is disproportionate complexity for RNG-2's ACs. Revisit if latency
  hurts UX.
- **Mesh validation:** deferred fully to RNG-5 to keep RNG-2 matched to its ACs.
- **Input strictness:** whitelist + type-check, pass through; the SCAD already
  clamps out-of-range values by construction, so range enforcement at the API
  would be redundant and would reject inputs the geometry handles safely.
- **Render config:** reuse `render.py` so the OpenSCAD contract has a single
  source of truth shared with RNG-1's tests and RNG-5.
