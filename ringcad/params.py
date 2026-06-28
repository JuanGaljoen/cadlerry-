"""Request validation for the ring generation endpoint — a thin view over
RingSpec (RNG-15).

Validation is unified on Pydantic: the flat 7-key request body is validated by
constructing a RingSpec (`from_params`), and the canonical 7-key dict is read
back with `to_params`. This module only owns the *flat-API* concerns the nested
schema doesn't express — dict shape, the exact 7-key set, and bool rejection
(pydantic v2 lax mode coerces True -> 1.0, so an explicit guard preserves the
historical "bool is not a number" contract). Type/range failures are delegated
to RingSpec and mapped back to the `{error, detail, field}` envelope callers
(ringcad.app) depend on.

No Flask import — stays import-light and unit-testable.
"""
from __future__ import annotations

from typing import Optional

from pydantic import ValidationError as PydanticValidationError

from ringcad.ringspec import PARAM_KEYS, from_params, to_params


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


REQUIRED = frozenset(PARAM_KEYS)


def _flat_field(loc: tuple) -> Optional[str]:
    """Map a pydantic error location to a flat 7-key field name, or None.

    RingSpec nests params under shank/setting/stones, but the offending key is
    always the last loc element. Only return it if it's one of the 7 flat keys.
    """
    if not loc:
        return None
    candidate = str(loc[-1])
    return candidate if candidate in REQUIRED else None


def validate_params(body: object) -> dict:
    """Validate a flat request body and return the canonical 7-param dict.

    Raises ValidationError on any problem. Unknown keys are checked before
    missing keys so injection attempts surface clearly. Type/range checks are
    delegated to RingSpec; bool values are rejected explicitly.
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

    # bool is an int subclass; pydantic v2 lax mode would coerce True -> 1.0,
    # so reject it here to preserve the "must be a number" contract.
    for field in PARAM_KEYS:
        if type(body[field]) is bool:
            raise ValidationError(
                "Invalid parameter", f"{field} must be a number", field=field
            )

    try:
        spec = from_params(body)
    except PydanticValidationError as exc:
        err = exc.errors()[0]
        field = _flat_field(tuple(err["loc"]))
        raise ValidationError(
            "Invalid parameter", str(err["msg"]), field=field
        )

    return to_params(spec)
