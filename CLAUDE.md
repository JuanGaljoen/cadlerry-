# Ring CAD App

Jewelry ring generator working toward one end goal: **upload any ring photo (or
enter parameters) and get a castable 3D model.** The app turns input into a
structured ring spec, generates a watertight 3D model, validates the mesh,
previews it in the browser, and exports a clean STL (and STEP) ready for lost-wax
casting. The solitaire is the first supported archetype, not the end goal; the
roadmap widens archetype coverage toward "any ring."

## Stack

- **Geometry kernel:** **build123d** (in-process Python, OpenCASCADE B-rep) —
  **the shipping kernel** as of RNG-15 (OpenSCAD cut over and removed). B-rep gives
  us `shell()` (real 3D wall-thickness enforcement), `fillet`/`sweep`/`loft`, curved
  surfaces, in-kernel geometry introspection, and STEP export — the capabilities
  OpenSCAD CSG cannot provide and that "any ring" requires.
- **IR / contract:** **RingSpec** — versioned, typed schema between the vision
  layer and the geometry layer; what the user edits; where castability rules
  validate (RNG-14).
- **Backend:** Python + Flask.
- **Castability gate:** Trimesh (watertight check + auto-repair) plus in-kernel
  `shell`/thickness checks on the B-rep.
- **Frontend:** Single HTML page, vanilla JS only (no frameworks).
- **3D preview:** Three.js with OrbitControls.
- **AI:** Claude API vision — photo → RingSpec (archetype, stone layout, shank
  profile, motifs, per-element dimensions, per-field confidence).

> **Migration note:** OpenSCAD (`scad/solitaire.scad`, `ringcad/render.py`,
> subprocess CLI) was removed in RNG-15 — `/generate-ring` now generates the
> solitaire in-process via build123d driven by RingSpec. The geometry lives in
> `ringcad/geometry/` (`shank`/`prong_setting`/`seat` + `build_solitaire` + STL/STEP
> export). The RNG-13 spike code under `spikes/rng13/` is retained for reference.

## Architecture (Path C: photo → castable model)

Five layers with one load-bearing artifact (RingSpec) in the middle:

1. **Vision / Understanding** — photo → RingSpec (Claude vision).
2. **RingSpec (the contract)** — versioned, typed; both sides evolve against it
   independently; carries castability validation rules.
3. **Procedural geometry** — RingSpec → geometry via a **library of composable
   modules** on build123d (`shank`, `prong_setting`, `seat`, `bezel`, …), each
   parametric and each emitting castable geometry.
4. **Castability gate** — `shell`/thickness, manifold, min-feature checks; much
   of it now in-kernel by construction.
5. **Export** — STEP (CAD interchange) + STL (print/preview).

**Core principle:** archetypes are **compositions of modules over a shared
spec, not monolithic templates.** Progress toward "any ring" = growing the
module vocabulary and composition rules, not piling up per-style templates.

## Casting Requirements (lost-wax)

These are hard manufacturing constraints, enforced in geometry, not just UI hints:

- Minimum wall thickness **0.8mm** throughout
- Minimum prong tip diameter **0.7mm**
- All modules must union into a **single watertight manifold**
- Exported STL must have **zero non-manifold edges**
- Mesh validated after every generation; auto-repair attempted if not watertight

## Solitaire Parameters (7)

These 7 parameters are the **solitaire archetype's slice of RingSpec** — the
first archetype, not the whole input model. RingSpec (RNG-14) generalizes beyond
these as archetypes are added.

| Parameter        | Notes                          |
|------------------|--------------------------------|
| `inner_diameter` | Finger size (mm)               |
| `band_width`     | Shank width (mm)               |
| `band_thickness` | Shank thickness (mm, >= 0.8)   |
| `stone_diameter` | Stone seat sizing (mm)         |
| `stone_height`   | Stone height (mm)              |
| `prong_count`    | **4 or 6 only** (dropdown)     |
| `setting_height` | Gallery/setting height (mm)    |

Modules (build123d, `ringcad/geometry/`): `shank()`, `prong_setting()`, `seat()`
composed by `build_solitaire(spec)` into a single watertight manifold.

## UI Design Specs

- **Layout:** form on the left, 3D viewer on the right (desktop); stacked
  vertically on mobile.
- **Form:** inputs for all 7 parameters with sensible defaults; `prong_count`
  is a dropdown limited to 4 or 6.
- **Actions:** Generate button POSTs JSON to `/generate-ring`; Download STL
  button appears on success and keeps working after the viewer is added.
- **Viewer:** Three.js canvas, OrbitControls (orbit/zoom/pan), ambient + two
  directional lights, wireframe toggle button; re-renders on each new STL.
- **Mesh status:** indicator above the Download button - green "valid" /
  red "invalid". Download works regardless of validation status.
- **Errors:** error message displayed on generation failure.
- **Photo flow:** upload (jpg/png) -> `/classify-ring` -> form pre-filled with
  estimates. Show clear "Estimates only, verify before generating" label; every
  pre-filled field stays user-overridable. Fail gracefully on blurry/non-ring
  photos.
- **Accessibility:** WCAG 2.1 AA mandatory.

## API Endpoints

- `POST /generate-ring` - accepts the 7 solitaire params as JSON (validated +
  adapted through RingSpec), returns binary STL on success with `X-Mesh-*` headers;
  `?format=step` returns STEP (`model/step`). Castability violations and malformed
  input return a 400 JSON error naming the field. Geometry built in-process via
  build123d.
- `GET /health` - returns `{"status": "ok"}`.
- `POST /classify-ring` - accepts an image, returns Claude vision estimates
  toward a RingSpec (style/archetype, prong count, shank taper, features) +
  estimated dimensions.

## Commands

Workspace pipeline commands (see `~/projects/personal/.claude/CLAUDE.md`):

- `/plan-feature`   - interactive planning, produces a spec file
- `/build-feature`  - full TDD pipeline with review, reflect, persist
- `/review-impl`    - standalone five-pillar code review
- `/ship`           - branch, commit, push, PR
- `/audit-security` - OWASP Top 10 audit
- `/freeze`         - lock scope to specific files

## Rules

- TDD: RED -> GREEN -> REFACTOR. No production code without a failing test.
- Never rewrite working code to fix broken code; fix only the broken module.
- Max 300 LOC per file; split if larger.
- Zero `console.log` in committed code.
- WCAG 2.1 AA mandatory for all UI work.
- No JS frameworks; vanilla only.
- Casting constraints (above) are non-negotiable.
- Never force push.

## Tickets (Jira project: RNG)

**Done (base app, OpenSCAD path):**

- **RNG-1** OpenSCAD parametric solitaire ring template [Done]
- **RNG-2** Flask backend with STL generation endpoint [Done]
- **RNG-3** Vanilla JS frontend with ring parameter form [Done]
- **RNG-4** Three.js STL viewer with orbit controls [Done]
- **RNG-5** Trimesh mesh validation and auto-repair [Done]
- **RNG-6** Photo upload with Claude vision ring classification [Done]

**Foundation (build123d + RingSpec pivot — dependency-ordered):**

- **RNG-13** Spike: build123d proof-of-parity for the solitaire [Done]
- **RNG-14** RingSpec v1: structured ring IR / schema [Done]
- **RNG-15** Geometry kernel migration OpenSCAD -> build123d (solitaire cutover) [In Review] - needs RNG-13, RNG-14
- **RNG-16** Procedural module library foundation (shank/prong_setting/seat/bezel) [High] - needs RNG-15

**Archetypes + vision (module compositions over RingSpec):**

- **RNG-9** Halo ring style [Medium] - needs RNG-16
- **RNG-10** Three-stone (Trilogy) ring style [Medium] - needs RNG-16
- **RNG-11** Side-stone band (channel/pave) [Medium] - needs RNG-16
- **RNG-12** Vision -> RingSpec population (photo populates structured spec) [High] - needs RNG-14, RNG-16

> Removed in the pivot: RNG-7 (cathedral shoulders, OpenSCAD-specific) and RNG-8
> (style registry over OpenSCAD) were deleted — both are superseded by the
> RingSpec + module-library foundation.

## Current Phase

**RNG-15 - Geometry kernel cutover OpenSCAD -> build123d (In Review).**

The foundation is in: RNG-13 (spike, GO) and RNG-14 (RingSpec v1) are Done.
RNG-15 routed `/generate-ring` through an in-process build123d generator driven by
RingSpec, decomposed the solitaire into `shank`/`prong_setting`/`seat` modules
(`ringcad/geometry/`), exposed STEP via `?format=step`, and removed the OpenSCAD
subprocess path (`scad/`, `ringcad/render.py`) plus `params.py`'s hand-rolled
validation. Parity held within RNG-13 tolerances; full suite green.

**Next: RNG-16** - formalize the generic module interface (each module consumes its
RingSpec slice), add the `bezel` module + composition layer, and drive raw
non-manifold edges to zero by construction. Then archetypes (RNG-9/10/11) +
vision->RingSpec population (RNG-12).

## Jira Ticket Lifecycle (orchestrator-run, Stop-verified)
- When starting /plan-feature or /build-feature: move the ticket to "In Progress" in Jira, then set `jira_in_progress: true` in `.claude/logs/build_session.json`.
- When running /ship and PR is created: move the ticket to "In Review" in Jira.
- When PR is merged or build is complete and shipped: move the ticket to "Done" in Jira.
- Always use the Jira MCP to update ticket status at each transition.
- Enforcement: the Stop hook's `check_jira_transition` soft-warns (stderr `[JIRA]`) when a build_session.json has a `ticket` but no `jira_in_progress` flag. The hook only *verifies* — it cannot perform the transition (Jira is network/auth/MCP; merge -> Done is an external GitHub event). The doing stays with the orchestrator via MCP; the flag is the receipt. Same pattern as `reflection_persisted`.
