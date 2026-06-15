"""Claude vision ring classifier (RNG-6).

Wraps a single Anthropic vision call behind `classify_ring`, which NEVER raises:
any SDK/parse/timeout failure is logged and surfaced as a result with ok=False.
The API key is read via env only; it never reaches a result body or a log line.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

import anthropic
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Casting-aware clamp bounds for the five estimable dimensions. inner_diameter
# (finger size) is deliberately absent -- it is never guessed from a photo.
CLAMP_BOUNDS = {
    "band_width": (1.6, 6.0),
    "band_thickness": (0.8, 4.0),
    "stone_diameter": (2.0, 10.0),
    "stone_height": (2.0, 6.0),
    "setting_height": (3.0, 8.0),
}

DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_NOTE = "Estimates are rough; verify before generating."

_SYSTEM = (
    "You are a jewelry classifier for solitaire engagement rings. Given a "
    "photo, identify the ring's style, shank taper, prong count, and visible "
    "features, and estimate its dimensions in millimetres. If the image does "
    "not clearly show a single ring, set ring_detected to false and leave all "
    "dimension fields null. Never guess finger size or inner diameter -- there "
    "is no field for it. All millimetre estimates are rough approximations."
)
_USER = (
    "Classify this ring and estimate its dimensions in millimetres. If it is "
    "not a clear photo of a single ring, set ring_detected to false."
)


class RingClassification(BaseModel):
    """Structured output schema for messages.parse. No inner_diameter field."""

    ring_detected: bool
    style: str = ""
    prong_count: int = 6
    shank_taper: str = ""
    features: list[str] = []
    band_width: float | None = None
    band_thickness: float | None = None
    stone_diameter: float | None = None
    stone_height: float | None = None
    setting_height: float | None = None
    note: str = ""


@dataclass(frozen=True)
class ClassifyResult:
    ok: bool
    ring_detected: bool
    style: str
    shank_taper: str
    note: str
    prong_count: int
    features: list[str]
    estimates: dict[str, float]

    def to_json(self) -> dict:
        return {
            "ring_detected": self.ring_detected,
            "style": self.style,
            "prong_count": self.prong_count,
            "shank_taper": self.shank_taper,
            "features": self.features,
            "estimates": self.estimates,
            "note": self.note,
        }


def _model() -> str:
    return os.environ.get("CLASSIFY_MODEL", DEFAULT_MODEL)


def _clamp(key: str, value) -> float:
    lo, hi = CLAMP_BOUNDS[key]
    return max(lo, min(hi, float(value)))


def _snap_prong(n: int) -> int:
    return 4 if abs(n - 4) <= abs(n - 6) else 6


def _empty(ok: bool, ring_detected: bool, note: str) -> ClassifyResult:
    return ClassifyResult(
        ok=ok,
        ring_detected=ring_detected,
        style="",
        shank_taper="",
        note=note,
        prong_count=6,
        features=[],
        estimates={},
    )


def classify_available() -> bool:
    """True iff an API key is configured. Env-only -- builds no client."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def classify_ring(image_bytes: bytes, media_type: str) -> ClassifyResult:
    """Classify a ring photo. Never raises; never leaks the key into the result."""
    try:
        client = anthropic.Anthropic()
        resp = client.with_options(timeout=30.0, max_retries=0).messages.parse(
            model=_model(),
            max_tokens=512,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64.standard_b64encode(
                                    image_bytes
                                ).decode(),
                            },
                        },
                        {"type": "text", "text": _USER},
                    ],
                }
            ],
            output_format=RingClassification,
        )
        data = resp.parsed_output
        if data is None:
            return _empty(ok=False, ring_detected=False, note="")
        if not data.ring_detected:
            return _empty(
                ok=True,
                ring_detected=False,
                note=data.note or "No ring detected in the photo.",
            )
        estimates: dict[str, float] = {
            key: _clamp(key, getattr(data, key))
            for key in CLAMP_BOUNDS
            if getattr(data, key) is not None
        }
        estimates["prong_count"] = _snap_prong(data.prong_count)
        return ClassifyResult(
            ok=True,
            ring_detected=True,
            style=data.style,
            shank_taper=data.shank_taper,
            note=data.note or DEFAULT_NOTE,
            prong_count=_snap_prong(data.prong_count),
            features=list(data.features),
            estimates=estimates,
        )
    except Exception:
        logger.error("classify_ring failed", exc_info=True)
        return _empty(ok=False, ring_detected=False, note="")
