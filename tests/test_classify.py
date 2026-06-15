"""Unit tests for the Claude vision ring classifier (RNG-6).

TDD RED: these tests define ringcad.classify, which does not exist yet. They
MUST fail at collection (ModuleNotFoundError on ringcad.classify) until the
implementer lands the module.

NO NETWORK, NO API KEY. The only thing mocked is the Anthropic client itself,
patched where classify.py looks it up: `ringcad.classify.anthropic.Anthropic`.
The fake's `.with_options(...).messages.parse(...)` returns an object whose
`.parsed_output` is a real `ringcad.classify.RingClassification` instance (or
None for the parse-failure case), or `.messages.parse` raises for the
never-raises case. classify_available() is driven via monkeypatch.setenv /
delenv on ANTHROPIC_API_KEY.
"""
import pytest

import ringcad.classify as classify
from ringcad.classify import (
    CLAMP_BOUNDS,
    RingClassification,
    classify_available,
    classify_ring,
)

JPEG = "image/jpeg"
IMG = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


class _FakeMessages:
    """Stands in for client.messages. parse() returns a preset response or
    raises a preset exception."""

    def __init__(self, parsed_output=None, raises=None):
        self._parsed_output = parsed_output
        self._raises = raises

    def parse(self, *args, **kwargs):
        if self._raises is not None:
            raise self._raises
        return type("Resp", (), {"parsed_output": self._parsed_output})()


class _FakeClient:
    def __init__(self, messages):
        self.messages = messages

    def with_options(self, *args, **kwargs):
        return self


def _install_client(monkeypatch, *, parsed_output=None, raises=None):
    """Patch ringcad.classify.anthropic.Anthropic to build a fake client that
    yields the given parsed_output / raises. Returns a dict recording whether
    the constructor was called."""
    rec = {"constructed": 0}
    messages = _FakeMessages(parsed_output=parsed_output, raises=raises)

    def fake_ctor(*args, **kwargs):
        rec["constructed"] += 1
        return _FakeClient(messages)

    monkeypatch.setattr(classify.anthropic, "Anthropic", fake_ctor)
    return rec


def _ring(**overrides):
    """A RingClassification for a detected ring, with field overrides."""
    base = dict(
        ring_detected=True, style="solitaire", prong_count=6,
        shank_taper="straight", features=["polished"],
        band_width=2.2, band_thickness=1.9, stone_diameter=6.5,
        stone_height=4.0, setting_height=6.0, note="rough estimate",
    )
    base.update(overrides)
    return RingClassification(**base)


# ---- AC4: estimates clamped to CLAMP_BOUNDS --------------------------------
def test_estimates_clamped_to_bounds(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    _install_client(
        monkeypatch,
        parsed_output=_ring(band_width=99.0, band_thickness=0.1),
    )
    result = classify_ring(IMG, JPEG)
    assert result.ok is True
    # band_width clamped to its upper bound, band_thickness to its lower bound
    assert result.estimates["band_width"] == CLAMP_BOUNDS["band_width"][1]
    assert result.estimates["band_thickness"] == CLAMP_BOUNDS["band_thickness"][0]


# ---- AC4: prong_count snapped to {4, 6} ------------------------------------
@pytest.mark.parametrize("raw,snapped", [(5, 4), (7, 6), (4, 4), (6, 6)])
def test_prong_count_snapped(monkeypatch, raw, snapped):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    _install_client(monkeypatch, parsed_output=_ring(prong_count=raw))
    result = classify_ring(IMG, JPEG)
    assert result.ok is True
    assert result.estimates["prong_count"] == snapped


# ---- AC4: inner_diameter is never estimated --------------------------------
def test_inner_diameter_never_in_estimates(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    _install_client(monkeypatch, parsed_output=_ring())
    result = classify_ring(IMG, JPEG)
    assert "inner_diameter" not in result.estimates


def test_clamp_bounds_are_the_five_estimables(monkeypatch):
    expected = {
        "band_width", "band_thickness", "stone_diameter",
        "stone_height", "setting_height",
    }
    assert set(CLAMP_BOUNDS.keys()) == expected
    assert "inner_diameter" not in CLAMP_BOUNDS
    assert "prong_count" not in CLAMP_BOUNDS


# ---- AC7: not-a-ring -> ok True, ring_detected False, estimates {} ----------
def test_not_a_ring_returns_empty_estimates(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    _install_client(
        monkeypatch,
        parsed_output=RingClassification(ring_detected=False),
    )
    result = classify_ring(IMG, JPEG)
    assert result.ok is True
    assert result.ring_detected is False
    assert result.estimates == {}


# ---- AC10: never raises -- API exception -> ok=False ------------------------
def test_api_timeout_returns_ok_false_not_raise(monkeypatch):
    import anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    timeout = anthropic.APITimeoutError(request=None)
    _install_client(monkeypatch, raises=timeout)
    result = classify_ring(IMG, JPEG)  # must NOT raise
    assert result.ok is False


def test_arbitrary_exception_returns_ok_false_not_raise(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    _install_client(monkeypatch, raises=RuntimeError("boom"))
    result = classify_ring(IMG, JPEG)  # must NOT raise
    assert result.ok is False


# ---- AC10: parsed_output None (refusal/truncation) -> ok=False --------------
def test_parse_failure_returns_ok_false(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    _install_client(monkeypatch, parsed_output=None)
    result = classify_ring(IMG, JPEG)
    assert result.ok is False


# ---- AC8: classify_available reflects ANTHROPIC_API_KEY only ----------------
def test_classify_available_true_when_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert classify_available() is True


def test_classify_available_false_when_key_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert classify_available() is False


def test_classify_available_builds_no_client(monkeypatch):
    """classify_available is env-only -- it must not construct a client."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rec = _install_client(monkeypatch, parsed_output=_ring())
    classify_available()
    assert rec["constructed"] == 0


# ---- to_json carries the AC response body fields ---------------------------
def test_to_json_includes_response_fields(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    _install_client(monkeypatch, parsed_output=_ring())
    body = classify_ring(IMG, JPEG).to_json()
    for key in ("ring_detected", "style", "prong_count",
                "shank_taper", "features", "estimates", "note"):
        assert key in body
