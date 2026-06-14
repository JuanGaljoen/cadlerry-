"""Frontend structure tests for the served ring parameter page (RNG-3).

TDD RED: these tests define the static HTML the Flask app must serve at
`GET /`. Today the app has NO `/` route (only /health + /generate-ring), so
`GET /` returns 404 and every structure assertion fails -> correct RED signal.
The implementer lands the `GET /` route + templates/index.html to turn these
GREEN.

SCOPE: these tests assert the served HTML STRUCTURE only. The Flask test client
runs NO JavaScript, so behavioral ACs (AC4 POST shape, AC5 loading state, AC6
blob/download, AC7 error rendering, AC9 runtime focus/keyboard/contrast) are
verified in the browser QA phase, NOT here. We only assert the static shell
(elements/regions/attributes) that the JS will later drive.

Element ids/names are the authoritative contract from .claude/logs/active_plan.md
and spec.md "## Autonomous Assumptions".
"""
import re

import pytest

from ringcad.app import create_app

# The 7 form keys. Six are number inputs; prong_count is a <select>.
NUMBER_KEYS = [
    "inner_diameter",
    "band_width",
    "band_thickness",
    "stone_diameter",
    "stone_height",
    "setting_height",
]
ALL_KEYS = NUMBER_KEYS + ["prong_count"]

# Defaults from docs/parameter-ranges.md (spec AC2). prong_count default (6)
# is asserted via the <select> option in its own test.
NUMBER_DEFAULTS = {
    "inner_diameter": "16.5",
    "band_width": "2.2",
    "band_thickness": "1.9",
    "stone_diameter": "6.5",
    "stone_height": "4",
    "setting_height": "6",
}


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def body(client):
    """The served HTML at GET /. Today this 404s (no `/` route) -> RED."""
    resp = client.get("/")
    assert resp.status_code == 200, (
        f"GET / returned {resp.status_code}, expected 200 (no `/` route yet?)"
    )
    return resp.get_data(as_text=True)


def _input_tag_with(html: str, **attrs) -> bool:
    """True if some <input ...> tag carries every name=value attr (any order).

    Tolerant of attribute ordering: matches a single <input> tag whose text
    contains each `name="value"` pair. Avoids brittle exact-string matching.
    """
    for tag in re.findall(r"<input\b[^>]*>", html, re.IGNORECASE):
        if all(
            re.search(rf'{re.escape(k)}\s*=\s*"{re.escape(v)}"', tag, re.IGNORECASE)
            for k, v in attrs.items()
        ):
            return True
    return False


def _select_block(html: str, select_id: str) -> str:
    """Return the <select id=...>...</select> block, or '' if absent."""
    m = re.search(
        rf'<select\b[^>]*id\s*=\s*"{re.escape(select_id)}"[^>]*>(.*?)</select>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    return m.group(0) if m else ""


# ---- AC1: page served at / ------------------------------------------------
def test_root_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/html")
    body = resp.get_data(as_text=True)
    assert 'id="ring-form"' in body


# ---- AC2: all 7 inputs present with defaults -------------------------------
def test_all_seven_inputs_present_with_defaults(body):
    for key in ALL_KEYS:
        assert f'name="{key}"' in body, f"missing control name={key}"
    for key, default in NUMBER_DEFAULTS.items():
        assert _input_tag_with(body, name=key, value=default), (
            f"input name={key} missing default value={default}"
        )


# ---- AC2: number input bounds (representative sample) ----------------------
def test_number_input_bounds(body):
    assert _input_tag_with(body, name="inner_diameter", min="14", max="23"), (
        "inner_diameter must carry min=14 max=23"
    )
    assert _input_tag_with(body, name="band_thickness", min="0.8"), (
        "band_thickness must carry min=0.8 (casting floor)"
    )
    # at least one number input declares step=0.1
    assert any(
        _input_tag_with(body, name=key, step="0.1") for key in NUMBER_KEYS
    ), "no number input declared step=0.1"


# ---- AC3: prong_count is a <select> of exactly 4 and 6 (6 selected) --------
def test_prong_count_is_select_4_and_6(body):
    block = _select_block(body, "prong_count")
    assert block, "no <select id=prong_count> found"
    assert re.search(r'name\s*=\s*"prong_count"', block, re.IGNORECASE), (
        "prong_count <select> must carry name=prong_count"
    )
    assert re.search(r'<option\b[^>]*value\s*=\s*"4"', block, re.IGNORECASE)
    assert re.search(r'<option\b[^>]*value\s*=\s*"6"', block, re.IGNORECASE)
    # option value=6 is the selected default
    opt6 = re.search(
        r'<option\b[^>]*value\s*=\s*"6"[^>]*>', block, re.IGNORECASE
    )
    assert opt6 and "selected" in opt6.group(0).lower(), (
        "option value=6 must be selected by default"
    )
    # prong_count must NOT be a free-text input
    assert not _input_tag_with(body, name="prong_count"), (
        "prong_count must be a <select>, not an <input>"
    )


# ---- AC8 wiring: static assets referenced ----------------------------------
def test_static_assets_referenced(body):
    assert "/static/app.js" in body, "page must reference /static/app.js"
    assert "/static/styles.css" in body, "page must reference /static/styles.css"


# ---- AC5/AC6/AC7 shells: result regions present ----------------------------
def test_result_regions_present(body):
    for region_id in ("status", "error", "download-btn", "stderr-details", "viewer"):
        assert f'id="{region_id}"' in body, f"missing region id={region_id}"


# ---- AC9 structural: aria-live regions -------------------------------------
def test_aria_live_regions(body):
    status = re.search(r'<[^>]*id\s*=\s*"status"[^>]*>', body, re.IGNORECASE)
    assert status, "no element with id=status"
    assert re.search(
        r'aria-live\s*=\s*"polite"', status.group(0), re.IGNORECASE
    ), "#status must carry aria-live=polite"

    error = re.search(r'<[^>]*id\s*=\s*"error"[^>]*>', body, re.IGNORECASE)
    assert error, "no element with id=error"
    err_tag = error.group(0)
    assert re.search(
        r'aria-live\s*=\s*"assertive"', err_tag, re.IGNORECASE
    ) or re.search(r'role\s*=\s*"alert"', err_tag, re.IGNORECASE), (
        "#error must carry aria-live=assertive or role=alert"
    )


# ---- AC9 structural: every input has a matching label[for] ------------------
def test_every_input_has_label_for(body):
    for key in ALL_KEYS:
        assert f'id="{key}"' in body, f"control id={key} missing"
        assert re.search(
            rf'<label\b[^>]*for\s*=\s*"{re.escape(key)}"', body, re.IGNORECASE
        ), f"no <label for={key}>"


# ---- AC8/AC10: no JS framework / CDN bundle; only local first-party + vendor
def test_no_js_framework(body):
    """All script srcs must be first-party (app.js / viewer.js) or locally
    vendored three; the inline import map must point only at /static/ URLs.

    Rewritten for RNG-4: app.js is no longer the *only* script src — viewer.js
    (ES module) and the vendored three files are also referenced. The rule is
    no framework/CDN, all local. Tolerant of attribute ordering.
    """
    forbidden = ("react", "vue", "angular", "svelte", "cdn", "unpkg", "jsdelivr")

    srcs = re.findall(
        r'<script\b[^>]*\bsrc\s*=\s*"([^"]*)"', body, re.IGNORECASE
    )
    assert srcs, "no <script src> at all (expected at least app.js + viewer.js)"
    for src in srcs:
        low = src.lower()
        assert not any(tok in low for tok in forbidden), (
            f"forbidden framework/CDN script src: {src}"
        )
        allowed = (
            low.endswith("app.js")
            or low.endswith("viewer.js")
            or "/static/vendor/three/" in low
        )
        assert allowed, (
            f"unexpected script src (not app.js/viewer.js/vendored three): {src}"
        )

    # The inline import map must reference only local /static/ URLs.
    im = re.search(
        r'<script\b[^>]*type\s*=\s*"importmap"[^>]*>(.*?)</script>',
        body,
        re.IGNORECASE | re.DOTALL,
    )
    assert im, "no inline <script type=importmap> found"
    import_urls = re.findall(r'"([^"]*)"\s*:\s*"([^"]*)"', im.group(1))
    mapped = [target for _, target in import_urls if "/" in target or "." in target]
    assert mapped, "import map declares no target URLs"
    for url in mapped:
        low = url.lower()
        assert low.startswith("/static/"), (
            f"import map target must be /static/-local: {url}"
        )
        assert not any(
            tok in low for tok in ("cdn", "unpkg", "jsdelivr", "http")
        ), f"forbidden CDN/remote import map target: {url}"


# ---- RNG-4 AC4/AC1/AC9 shell: viewer markup --------------------------------
def test_viewer_structure(body):
    """The #viewer region must expose the canvas, wireframe toggle, and message
    placeholder the viewer JS drives — with their accessibility attributes."""
    canvas = re.search(
        r'<canvas\b[^>]*id\s*=\s*"viewer-canvas"[^>]*>', body, re.IGNORECASE
    )
    assert canvas, "no <canvas id=viewer-canvas>"
    assert re.search(r"aria-label\s*=", canvas.group(0), re.IGNORECASE), (
        "#viewer-canvas must carry an aria-label"
    )

    toggle = re.search(
        r'<button\b[^>]*id\s*=\s*"wireframe-toggle"[^>]*>', body, re.IGNORECASE
    )
    assert toggle, "no <button id=wireframe-toggle>"
    assert re.search(r"aria-pressed\s*=", toggle.group(0), re.IGNORECASE), (
        "#wireframe-toggle must carry aria-pressed"
    )

    assert 'id="viewer-message"' in body, "missing element id=viewer-message"


# ---- RNG-4 AC1 wiring: viewer ES module referenced -------------------------
def test_viewer_module_script(body):
    module_scripts = re.findall(
        r'<script\b[^>]*type\s*=\s*"module"[^>]*>', body, re.IGNORECASE
    )
    assert any("viewer.js" in tag for tag in module_scripts), (
        "no <script type=module> referencing viewer.js"
    )


# ---- RNG-4 AC10 static: import map maps three specifiers to local vendor ----
def test_import_map_specifiers(body):
    im = re.search(
        r'<script\b[^>]*type\s*=\s*"importmap"[^>]*>(.*?)</script>',
        body,
        re.IGNORECASE | re.DOTALL,
    )
    assert im, "no inline <script type=importmap> found"
    block = im.group(1)
    assert re.search(
        r'"three"\s*:\s*"/static/vendor/three/three\.module\.js"',
        block,
    ), '"three" must map to /static/vendor/three/three.module.js'
    assert re.search(
        r'"three/addons/"\s*:\s*"/static/vendor/three/addons/"',
        block,
    ), '"three/addons/" must map to /static/vendor/three/addons/'


# ---- RNG-5 AC4 structural: mesh-status indicator above the download button -
def test_mesh_status_above_download(body):
    """The #mesh-status indicator must exist as a live region and sit ABOVE
    #download-btn in source order.

    SCOPE: static shell only. The header-driven green/red rendering and the
    'download still works when mesh is invalid' behavior are JS-runtime
    concerns verified in the browser-QA phase, NOT here (no JS runs in the
    Flask test client).
    """
    status = re.search(r'<[^>]*id\s*=\s*"mesh-status"[^>]*>', body, re.IGNORECASE)
    assert status, "no element with id=mesh-status"
    tag = status.group(0)
    assert re.search(r'role\s*=\s*"status"', tag, re.IGNORECASE), (
        "#mesh-status must carry role=status"
    )
    assert re.search(r'aria-live\s*=\s*"polite"', tag, re.IGNORECASE), (
        "#mesh-status must carry aria-live=polite"
    )
    # source order: mesh-status appears before the download button
    assert body.index('id="mesh-status"') < body.index('id="download-btn"'), (
        "#mesh-status must appear ABOVE #download-btn"
    )


# ---- RNG-4 AC10 static: vendored three files are actually served -----------
def test_vendored_three_served(client):
    for path in (
        "/static/vendor/three/three.module.js",
        "/static/vendor/three/addons/controls/OrbitControls.js",
        "/static/vendor/three/addons/loaders/STLLoader.js",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, (
            f"vendored three file not served (got {resp.status_code}): {path}"
        )
