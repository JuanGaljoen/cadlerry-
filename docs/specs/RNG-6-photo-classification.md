# RNG-6: Photo upload with Claude vision ring classification

**Type:** feature
**Ticket:** RNG-6 (Low, backend + frontend)
**Depends on:** RNG-3 (done) — form + `static/app.js`; RNG-2 (done) — app-factory + pure-validation split
**Reuses:** `ringcad.params` ranges, the `flask-wraps-render-scad-endpoint` thin-adapter pattern

## Problem

**Who:** a user who has a photo of a ring they like but doesn't know the numeric parameters to type into the form.

**What:** today the only way to drive the generator is to enter all 7 parameters by hand. There's no way to start from a reference photo.

**Why now:** RNG-3's form is the last dependency; with it done, photo-assisted pre-fill is unblocked. It's a convenience layer, not core, hence Low priority.

**Future state:** When this is done, a user can upload a ring photo and have the form pre-filled with estimated parameters they can review and adjust. Before this, they had to know and type every value. The key difference is the photo gives a starting point; the user still verifies and owns the final numbers.

## Approach

**Chosen approach:** a new `/classify-ring` endpoint that accepts an uploaded image, sends it to Claude vision (Haiku 4.5) with a structured-output schema, and returns best-effort estimates. The frontend adds a photo-upload control that downscales the image client-side, POSTs it, and pre-fills the form. The whole feature degrades gracefully when no API key is configured, so it ships and is testable today with zero account setup.

Decisions taken at planning (user-confirmed in conversation):

1. **Model: `claude-haiku-4-5`.** Classification is the canonical Haiku use case and the cheapest (~$0.003/photo). Swappable via an env var (`CLASSIFY_MODEL`, default `claude-haiku-4-5`) if accuracy proves insufficient.
2. **Server-side-only key.** `ringcad.classify` builds `anthropic.Anthropic()` which reads `ANTHROPIC_API_KEY` from the environment. The key never reaches the browser. No key is accepted from the client.
3. **Graceful no-key fallback (ships today, no admin).** A `classify_available()` helper (mirroring `openscad_available()`) reports whether the key is set. When it is not, `/classify-ring` returns `503` with a clear message and the UI tells the user to enter parameters manually. The form remains fully usable. Adding the key later is a `.env` edit with no code change.
4. **Client-side downscale.** The browser resizes the image (long edge <= 1024px) to a JPEG via a canvas before upload. Keeps image tokens (and cost) low and upload fast; full-res phone photos add cost with no classification benefit.
5. **Structured output.** Use the Anthropic structured-outputs feature (`output_config.format` / `messages.parse`) so the response is a validated JSON object, not free text to parse.
6. **Estimates are best-effort and clamped.** A photo cannot yield absolute finger size. The model estimates what it can; the endpoint clamps every numeric estimate to the documented per-parameter ranges before returning. `inner_diameter` is not estimable from a photo and is left at the form default (the UI says so).

### Classification output contract

`POST /classify-ring` (multipart/form-data, field `image`) returns `200`:

```json
{
  "ring_detected": true,
  "style": "solitaire",
  "prong_count": 6,
  "shank_taper": "tapered",
  "features": ["cathedral setting", "round brilliant stone"],
  "estimates": {
    "band_width": 2.4,
    "band_thickness": 1.9,
    "stone_diameter": 6.8,
    "stone_height": 4.2,
    "setting_height": 6.0,
    "prong_count": 6
  },
  "note": "Estimates only, verify before generating."
}
```

- `ring_detected: false` (200) when the model can't identify a ring (blurry / non-ring): `estimates` omitted or empty, `note` explains. The UI shows a graceful message and leaves the form untouched.
- `estimates` contains only the parameters estimable from a photo (NOT `inner_diameter`). All numeric values are clamped to the `docs/parameter-ranges.md` bounds. `prong_count` is snapped to 4 or 6.

### Files

| Path | Change |
|------|--------|
| `ringcad/classify.py` (new) | `classify_available() -> bool`; `classify_ring(image_bytes, media_type) -> ClassifyResult`; the Anthropic call, structured-output schema, range-clamping, snap-to-{4,6}, and "not a ring" handling. All logic lives here; never raises to the caller (returns a structured failure). Keep < 300 LOC. |
| `ringcad/app.py` | Add `POST /classify-ring`: 503 when `classify_available()` is false; validate the upload (present, jpg/png, size cap); call `classify_ring`; map the result to JSON. Thin adapter, no model logic inline. |
| `requirements.txt` | Add `anthropic` (pinned). |
| `templates/index.html` | Photo-upload control above the dimensions fieldset: `<input type="file" accept="image/jpeg,image/png">` + an "Estimate from photo" button + an aria-live status line + the "Estimates only, verify before generating" label region. |
| `static/app.js` (or a small new `static/photo.js` if app.js nears the LOC cap) | Client-side downscale (canvas, long edge <= 1024px, JPEG), POST to `/classify-ring`, pre-fill estimable fields, show the estimates label, handle 503 / not-a-ring / errors gracefully. Every field stays editable; generate flow unchanged. |
| `static/styles.css` | Styling for the upload control + estimates label. |
| `tests/test_classify.py` (new) | Unit tests for `classify_ring` clamping / snap / not-a-ring / never-raises, with the Anthropic client mocked (no network, no key needed). |
| `tests/test_backend.py` | Endpoint tests: 503 when key absent (monkeypatch `classify_available -> False`); 200 with estimates when `classify_ring` is monkeypatched; bad/missing/oversized upload -> 400. |
| `tests/test_frontend.py` | Static-shell: upload control + estimates label exist with correct labels/aria. |

`ringcad/render.py`, `ringcad/mesh_validator.py`, `ringcad/params.py` unchanged.

## Acceptance Criteria

- [ ] **AC1 — Photo upload accepts jpg and png.** The UI exposes a file input restricted to `image/jpeg` and `image/png`; other types are rejected client-side and server-side.
- [ ] **AC2 — Image sent to POST /classify-ring.** The (downscaled) image is POSTed as multipart/form-data to `/classify-ring`.
- [ ] **AC3 — Claude vision identifies style, prong count, shank taper, features.** On a clear ring photo with a configured key, the response includes `style`, `prong_count`, `shank_taper`, and `features`.
- [ ] **AC4 — Form pre-filled with estimated dimensions.** Estimable parameters are written into the form inputs, clamped to the documented ranges; `prong_count` snapped to 4 or 6. `inner_diameter` is left at its default (not estimable from a photo).
- [ ] **AC5 — Clear "Estimates only, verify before generating" label.** Shown whenever estimates are applied.
- [ ] **AC6 — User can override every pre-filled field.** All inputs remain editable after pre-fill; nothing is locked or disabled.
- [ ] **AC7 — Graceful failure on blurry / non-ring photos.** `ring_detected: false` returns 200 with an explanatory note; the UI shows a friendly message and leaves the form unchanged. No crash, no stack trace.
- [ ] **AC8 — Graceful no-key fallback.** With no `ANTHROPIC_API_KEY`, `/classify-ring` returns 503 with a clear message and the UI tells the user to enter parameters manually. The rest of the app is unaffected. (Enables shipping without account setup.)
- [ ] **AC9 — Key stays server-side.** The API key is never sent to or exposed in the browser; the client supplies only the image.
- [ ] **AC10 — Classification never 500s.** Upload/validation/model/parse failures map to a 4xx/503 with a JSON message; `classify_ring` catches its own errors. No leaked traceback.

## Edge Cases

| Case | Expected behavior |
|------|-------------------|
| No `ANTHROPIC_API_KEY` set | 503 `{"error": "Photo classification is not configured", ...}`; UI -> manual-entry message (AC8) |
| Non-image / wrong type upload | 400, names the problem (server-side type check, not just client `accept`) |
| Missing `image` field | 400 |
| Oversized upload (> cap, e.g. 8MB) | 400 with a size message (downscale should keep real uploads far under this) |
| Blurry / not a ring | 200 `ring_detected: false`, friendly UI note, form untouched (AC7) |
| Model returns out-of-range estimate | clamped to the `docs/parameter-ranges.md` bound before returning (AC4) |
| Model returns prong_count not in {4,6} | snapped to nearest of 4/6 |
| Anthropic API error / timeout | caught in `classify_ring`; endpoint returns 502/503 with a clear message (AC10) |
| Estimable subset only | `inner_diameter` never estimated; left at form default |

## Constraints

- **Cost:** one Haiku 4.5 call per upload (~$0.003); image downscaled to <=1024px long edge to bound image tokens. No retries by default. No agent loop.
- **Security:** key server-side only (AC9); image content-type validated server-side; size cap enforced; SDK call uses a timeout. No key or PII echoed in responses.
- **Accessibility:** WCAG 2.1 AA — labelled file input, keyboard-operable button, aria-live status for classification progress and results, the estimates label conveyed as text (not colour alone), focus handling consistent with RNG-3.
- **Patterns to follow:** `flask-wraps-render-scad-endpoint` (thin app.py adapter, pure logic module, `*_available()` gate before the external call, never-500 discipline). Frontend follows RNG-3's vanilla-JS structure; no frameworks.
- **LOC:** max 300 non-blank LOC per source file. Split into `ringcad/classify.py` (and `static/photo.js` if `static/app.js` would exceed the cap).

## Scope

**In scope:** `/classify-ring` endpoint, `ringcad.classify` module, photo-upload UI with client-side downscale, form pre-fill with the estimates label, graceful no-key + not-a-ring + error handling, the `anthropic` dependency, tests.

**Out of scope (deferred):**
- Estimating `inner_diameter` / true scale from a reference object in the photo (not reliably possible; left at default).
- Multi-image or multi-angle classification (single image only).
- Caching / rate-limiting classification calls (single-user personal app).
- Storing or logging uploaded images (processed in-memory, not persisted).
- Streaming or progress beyond a simple aria-live "classifying..." state.
- Any change to `/generate-ring`, the viewer, or mesh validation.

## Success Metrics

| Metric | Target | Measure After |
|--------|--------|---------------|
| App usable with no key configured | 100% (form + generate work; classify returns 503 + UI message) | Build |
| Classification 500s | 0 (all failure modes -> 4xx/503 + JSON) | Build |
| Estimates within documented ranges | 100% (clamped) | Build (unit test) |
| Per-photo cost (key configured) | < $0.01 (Haiku, <=1024px) | Manual, once a key is added |

## Test Plan

TDD, RED first. The unit and endpoint tests mock the Anthropic client, so the suite runs with **no key and no network**.

- **`tests/test_classify.py` (no key, mocked client):** clamping (out-of-range -> bound); prong snap to {4,6}; `inner_diameter` never present in estimates; `ring_detected: false` path; `classify_ring` never raises on a mocked API exception (returns a structured failure).
- **`tests/test_backend.py`:** 503 when `classify_available()` is False; 200 + estimates when `classify_ring` is monkeypatched to a known result; missing `image` -> 400; wrong content-type -> 400; oversized -> 400. No 500 on any path.
- **`tests/test_frontend.py` (static shell):** file input with `accept="image/jpeg,image/png"`, the "Estimate from photo" control, and the estimates-label region exist with proper labels/aria. (Header-driven pre-fill behaviour is browser-QA, per the RNG-3/RNG-4 testing split.)
- **Browser QA:** upload control renders; with no key, the manual-entry message shows and generate still works (the shippable-today path). With a key (optional, manual), a real photo pre-fills the form and the estimates label appears.

## Dependencies

- RNG-3 form + `static/app.js`; RNG-2 app-factory + `ringcad.params` ranges.
- New runtime dep: `anthropic` (pinned in `requirements.txt`).
- Optional at runtime: `ANTHROPIC_API_KEY` (feature degrades gracefully without it). Optional `CLASSIFY_MODEL` (default `claude-haiku-4-5`).

## Validation (planning decisions, user-confirmed)

- **Model = Haiku 4.5:** cheapest, ideal for classification; env-swappable.
- **Server-side-only key + graceful no-key fallback:** lets the whole feature build, test, and ship today with zero Anthropic account setup; the key becomes a later `.env` edit with no code change.
- **Client-side downscale to <=1024px:** bounds cost/tokens; full-res adds cost with no benefit.
- **Estimates clamped + `inner_diameter` excluded:** a photo can't give absolute finger size; honesty over false precision, reinforced by the "estimates only" label.
