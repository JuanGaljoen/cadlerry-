"""Pure request validation for the ring generation endpoint (RNG-2).

No Flask or render imports — this module stays import-light so it can be unit
tested and reused. The caller (ringcad.app) translates ValidationError into a
400 JSON response.
"""
from __future__ import annotations

from numbers import Real
from typing import Optional


class ValidationError(Exception):
    """Raised when a request body fails validation.

    Carries the user-facing `error`, an optional `detail`, and the offending
    `field` (None when the failure is not tied to a single field).
    """

    def __init__(self, error: str, detail: str = "", field: Optional[str] = None):
        super().__init__(error)
        self.error = error
        self.detail = detail
        self.field = field


PARAM_TYPES: dict[str, type] = {
    "inner_diameter": float,
    "band_width": float,
    "band_thickness": float,
    "stone_diameter": float,
    "stone_height": float,
    "prong_count": int,
    "setting_height": float,
}

REQUIRED = frozenset(PARAM_TYPES)


def _coerce(field: str, target: type, value: object) -> object:
    # bool is an int subclass; reject explicitly so True/False can't sneak in.
    if type(value) is bool:
        raise ValidationError(
            "Invalid parameter", f"{field} must be a number", field=field
        )
    if value is None or not isinstance(value, Real):
        raise ValidationError(
            "Invalid parameter", f"{field} must be a number", field=field
        )
    if target is int:
        if value != int(value):
            raise ValidationError(
                "Invalid parameter",
                f"{field} must be a whole number",
                field=field,
            )
        return int(value)
    return float(value)


def validate_params(body: object) -> dict:
    """Validate and coerce a request body into a clean params dict.

    Raises ValidationError on any problem. Unknown keys are checked before
    missing keys so injection attempts surface clearly.
    """
    if not isinstance(body, dict):
        raise ValidationError(
            "Invalid request body", "expected a JSON object", field=None
        )

    unknown = set(body) - REQUIRED
    if unknown:
        key = sorted(unknown)[0]
        raise ValidationError(
            "Unknown parameter", f"unexpected key: {key}", field=key
        )

    missing = REQUIRED - set(body)
    if missing:
        field = sorted(missing)[0]
        raise ValidationError(
            "Missing parameter", f"required: {field}", field=field
        )

    coerced: dict = {}
    for field, target in PARAM_TYPES.items():
        coerced[field] = _coerce(field, target, body[field])
    return coerced
