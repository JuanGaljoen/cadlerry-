"""Photo-upload static-shell tests for the served page (RNG-6).

TDD RED: these tests define the photo-upload markup + photo.js reference the
served HTML at GET / must carry. They FAIL today because that markup does not
exist yet.

SCOPE: static shell only. The Flask test client runs NO JavaScript, so the
upload / canvas-downscale / form-prefill behavior is verified in browser QA,
NOT here. We only assert the static elements/attributes the JS will drive.

Element ids/attributes are the authoritative contract from
.claude/logs/active_plan.md.
"""
import re

import pytest

from ringcad.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def body(client):
    resp = client.get("/")
    assert resp.status_code == 200, (
        f"GET / returned {resp.status_code}, expected 200"
    )
    return resp.get_data(as_text=True)


def _input_tag_with(html: str, **attrs) -> bool:
    for tag in re.findall(r"<input\b[^>]*>", html, re.IGNORECASE):
        if all(
            re.search(rf'{re.escape(k)}\s*=\s*"{re.escape(v)}"', tag, re.IGNORECASE)
            for k, v in attrs.items()
        ):
            return True
    return False


# ---- AC1: file input accepts only JPEG/PNG, with a label[for] --------------
def test_photo_input_present_with_accept_and_label(body):
    assert _input_tag_with(body, id="ring-photo", type="file"), (
        "no <input type=file id=ring-photo>"
    )
    assert _input_tag_with(
        body, id="ring-photo", accept="image/jpeg,image/png"
    ), 'ring-photo input must carry accept="image/jpeg,image/png"'
    assert re.search(
        r'<label\b[^>]*for\s*=\s*"ring-photo"', body, re.IGNORECASE
    ), "no <label for=ring-photo>"


# ---- AC5: 'estimates only' label present with exact reassurance text --------
def test_estimates_label_present_with_text(body):
    label = re.search(
        r'<[^>]*id\s*=\s*"estimates-label"[^>]*>(.*?)</', body,
        re.IGNORECASE | re.DOTALL,
    )
    assert label, "no element with id=estimates-label"
    assert "Estimates only, verify before generating" in label.group(1), (
        "estimates-label must contain "
        "'Estimates only, verify before generating'"
    )


# ---- estimate button is a non-submitting button ---------------------------
def test_estimate_button_is_type_button(body):
    btn = re.search(
        r'<button\b[^>]*id\s*=\s*"estimate-btn"[^>]*>', body, re.IGNORECASE
    )
    assert btn, "no <button id=estimate-btn>"
    assert re.search(r'type\s*=\s*"button"', btn.group(0), re.IGNORECASE), (
        "#estimate-btn must carry type=button (must not submit the form)"
    )


# ---- AC9 a11y: photo status is a polite live region ------------------------
def test_photo_status_is_polite_live_region(body):
    status = re.search(
        r'<[^>]*id\s*=\s*"photo-status"[^>]*>', body, re.IGNORECASE
    )
    assert status, "no element with id=photo-status"
    assert re.search(
        r'aria-live\s*=\s*"polite"', status.group(0), re.IGNORECASE
    ), "#photo-status must carry aria-live=polite"


# ---- AC8 wiring: photo.js loaded as a plain (non-module) defer script -------
def test_photo_js_referenced_as_plain_defer_script(body):
    tag = re.search(
        r'<script\b[^>]*\bsrc\s*=\s*"[^"]*photo\.js"[^>]*>', body,
        re.IGNORECASE,
    )
    assert tag, "no <script src=...photo.js>"
    tag_text = tag.group(0)
    assert "defer" in tag_text.lower(), "photo.js script must be defer"
    assert not re.search(r'type\s*=\s*"module"', tag_text, re.IGNORECASE), (
        "photo.js must NOT be a module script"
    )
    im = re.search(
        r'<script\b[^>]*type\s*=\s*"importmap"[^>]*>(.*?)</script>',
        body, re.IGNORECASE | re.DOTALL,
    )
    if im:
        assert "photo.js" not in im.group(1), (
            "photo.js must not appear in the import map"
        )
