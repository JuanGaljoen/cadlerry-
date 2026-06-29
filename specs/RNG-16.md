# Procedural module library foundation (shank / prong_setting / seat / bezel) (RNG-16)

> Type: feature. Formalize the build123d geometry modules introduced in RNG-15
> into a real composable library: a typed module interface, an archetype-keyed
> composition layer, per-module in-kernel castability self-checks, and a new
> `bezel` module. The solitaire is re-expressed purely as a composition of
> library modules. No new archetype ships here (halo/trilogy/side-stone are
> RNG-9/10/11).

## Problem

RNG-15 decomposed the solitaire into `shank` / `prong_setting` / `seat`
functions and a `build_solitaire` fuser, but the "module library" is still just
a convention: there is no enforced interface, no archetype-dispatching
composition layer, and no proof the shape generalizes beyond a prong setting.
The whole roadmap ("any ring" = compositions of modules over a shared RingSpec)
leans on this foundation. Without it, every new archetype (RNG-9/10/11) reinvents
its own assembly + castability glue, and the modules drift apart.

When this is done, a developer can add a new ring archetype by registering an
ordered list of existing modules (plus the occasional new module) against an
archetype key, and get a castable, watertight manifold for free. Before this,
they had to hand-wire module fusing and castability per archetype.

## Acceptance Criteria

- **AC1 — Typed module interface.** A module is a callable conforming to a
  `Module` `typing.Protocol` (`build(spec: RingSpec) -> Solid`, plus a
  castability self-check, see AC4). Modules are registered by name in a single
  registry (`MODULES: dict[str, Module]`). `shank`, `prong_setting`, `seat`, and
  `bezel` are all registered and all satisfy the Protocol (verified by a test
  that asserts conformance for every registered module).
- **AC2 — Archetype-keyed composition layer.** An `ARCHETYPES` map keys an
  archetype name to an ordered list of module names; a single `compose(spec)`
  function looks up `spec.archetype`, builds each module, and fuses them into one
  solid. `build_solitaire(spec)` becomes a thin wrapper over `compose(spec)` (or
  is replaced by it) so the solitaire is expressed **purely** as the composition
  `["shank", "seat", "prong_setting"]` — no bespoke fusing logic remains in the
  solitaire path.
- **AC3 — `bezel` module.** A new `bezel(spec) -> Solid` module (a closed collar
  wall around the stone seat) is implemented, registered, and exercised
  end-to-end via a test-only `bezel` composition (`shank` + `seat` + `bezel`)
  that produces a single watertight manifold. (The user-facing bezel *archetype*
  is out of scope; this proves the interface generalizes past prong settings.)
- **AC4 — Per-module in-kernel castability self-check.** Each module exposes a
  castability self-check that inspects its **own** solid in-kernel (build123d
  section / bounding-box probes at the module's critical planes) and returns
  structured `Violation`s when min wall (0.8mm) or min feature/prong-tip (0.7mm)
  is breached. Constants are imported from `ringcad.mesh_validator` (single
  source, per the RNG-14 decision), never re-declared. The post-geometry
  `validate_and_repair` mesh gate is retained as the watertight runtime
  guarantee — the self-checks add per-module coverage, they do not replace it.
- **AC5 — Watertight composition.** `compose(spec)` for the solitaire (and the
  bezel test composition) produces a single watertight manifold; the shipped STL
  has **zero non-manifold edges** (asserted via the existing trimesh validation
  on the golden solitaire and the bezel test composition).
- **AC6 — Independence / extensibility.** Adding a new module or recomposing
  existing modules into a new archetype does not require editing unrelated
  modules. Demonstrated by a test that registers a throwaway stub module + a new
  archetype entry and composes it, touching no existing module file.
- **AC7 — Suite green + parity preserved.** The full existing test suite stays
  green, and the solitaire characterization parity test (RNG-13 tolerances:
  bbox / volume / manifold / min-thickness) still passes after the refactor —
  the composition refactor is behavior-preserving for the solitaire.

## Approach

Selected (confirmed during planning):

1. **Module interface = lightweight `typing.Protocol` + registry.** A `Module`
   Protocol declares `build(spec: RingSpec) -> Solid` and a castability
   self-check method/callable. Existing functions adapt to it with minimal
   ceremony. A `MODULES` dict registers each by name; an `ARCHETYPES` dict maps
   archetype -> ordered module-name list. Rejected: ABC base class (more
   boilerplate per module, no real benefit at 4 modules); plain-functions-only
   (leaves "interface" unenforced, fails AC1's conformance test).

2. **The "slice" is which fields a module reads, not a separate passed object.**
   Modules receive the whole `RingSpec` and read their relevant sub-model
   (`spec.shank` for `shank`; `spec.setting` + `spec.stones` for
   `seat`/`prong_setting`/`bezel`). Rationale: placement/clamps couple shank
   head-radius + stone + setting (a prong's position depends on the shank's head
   radius), so a pure per-module slice would leak. Shared derived values are
   computed once via the existing `ringcad/geometry/_common.py`
   `clamps()`/`placement()` helpers; the composition layer computes clamps once
   and modules reuse it (eliminates today's per-module `clamps(spec)` recompute).
   **Flag for architect:** decide whether `compose` passes the cached clamps dict
   into each module (signature `build(spec, clamps)`) or modules keep calling the
   shared `clamps(spec)` (memoized). Either satisfies AC1/AC6; pick the simpler.

3. **Castability by construction = per-module in-kernel self-check + retained
   mesh gate.** Each module probes its own solid (section thickness at the band
   mid-plane for `shank`; tip radius for `prong_setting`; collar wall for
   `seat`/`bezel`) and emits `Violation`s. The watertight guarantee stays with
   the existing `validate_and_repair` gate. Rejected: full `shell()`/offset
   reconstruction (build123d `shell()` on fused claw geometry is the riskiest,
   highest-effort path — deferred until an archetype actually needs it);
   deferring all castability work (punts the ticket's self-check clause).

4. **`bezel` built now**, even though no archetype consumes it until later, to
   prove the interface generalizes beyond prong settings and de-risk RNG-9/10/11.
   Exercised via a test-only `bezel` composition.

5. **`archetype` literal unchanged.** RingSpec keeps `archetype:
   Literal["solitaire"]`; the composition layer is keyed on archetype but has one
   live entry. Widening the literal to a discriminated union happens in the first
   archetype ticket (RNG-9), as `models.py:79` already notes.

## Edge Cases

- **`prong_count` not in {4,6}:** already clamped to 4 in `_common.clamps()`;
  preserve that behavior.
- **Unknown / unregistered archetype in `compose`:** raise a clear, named error
  (not a KeyError) identifying the unsupported archetype.
- **Unregistered module name in an `ARCHETYPES` entry:** fail fast at composition
  with a named error.
- **Epsilon overlap before fuse:** modules must overlap by a small epsilon before
  union (no coplanar contact) so the B-rep fuse yields a clean manifold — relevant
  for `bezel`/`seat` collar meeting the shank (per the RNG-10 trilogy note).
- **Bezel at small stone diameters:** collar wall must not thin below 0.8mm; the
  self-check (AC4) must catch it across the parametric range.
- **Module returns an empty/degenerate solid:** composition surfaces a clear
  error rather than producing a silently invalid mesh.

## Constraints

- **Casting (non-negotiable):** min wall 0.8mm, min prong/feature tip 0.7mm,
  single watertight manifold, zero non-manifold edges on exported STL.
- **Single source of truth:** casting constants imported from
  `ringcad.mesh_validator`; never duplicated (RNG-14 decision).
- **Behavior-preserving for the solitaire:** parity test (RNG-13 tolerances) must
  still pass; `/generate-ring` output for the solitaire is unchanged.
- **File size:** max 300 non-blank LOC per source file (hook-enforced); split
  modules/helpers as needed (current `_common.py` is 113 LOC).
- **No new runtime dependencies.**
- **TDD:** RED -> GREEN -> REFACTOR; each module gets failing tests first.
- **Performance:** generation time for the solitaire must not regress materially
  vs RNG-15 (the composition layer adds dispatch, not geometry).

## Scope Boundaries

**In scope:**
- `Module` Protocol + `MODULES` registry + `ARCHETYPES` map + `compose(spec)`.
- `bezel` module + its test-only composition.
- Per-module in-kernel castability self-checks.
- Solitaire re-expressed as a pure composition; `build_solitaire` becomes a
  wrapper over `compose`.
- Per-module test suites (parametric range, castability, manifold output) +
  conformance + extensibility tests.

**Out of scope (deferred):**
- New user-facing archetypes (halo RNG-9, trilogy RNG-10, side-stone RNG-11).
- Widening `RingSpec.archetype` to a discriminated union (first archetype ticket).
- Full `shell()`/offset by-construction reconstruction (until an archetype needs
  it).
- Frontend changes (no new archetype fields to expose yet).
- Vision -> RingSpec archetype dispatch (RNG-12).

## Success Metrics

- Solitaire path contains zero bespoke fusing logic (all via `compose`).
- A new archetype can be added by editing only the `ARCHETYPES` map (+ any new
  module file) — proven by the AC6 extensibility test.
- Zero non-manifold edges on the golden solitaire and the bezel test composition.
- Every registered module has its own test file covering parametric range,
  castability self-check, and manifold output.
- Full suite green; parity test green.

## Design Notes + Dependencies

- **Files (anticipated):** `ringcad/geometry/module.py` (Protocol + `MODULES` +
  `ARCHETYPES` + `compose`), `ringcad/geometry/bezel.py`, castability self-check
  helpers in `_common.py` (or a new `_castability.py` if `_common` nears the LOC
  cap), `ringcad/geometry/__init__.py` (export `compose`/registry). Tests:
  `tests/test_geometry_modules.py` (extend), new per-module + composition tests.
- **Depends on:** RNG-15 (kernel cutover, Done), RNG-14 (RingSpec, Done).
- **Unblocks:** RNG-9 / RNG-10 / RNG-11 (archetypes), and the modules RNG-12 can
  populate.
- **Module signature decision** (slice-passing vs memoized clamps) is the one
  open item left to the architect; both options satisfy the ACs.
