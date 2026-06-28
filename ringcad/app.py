"""Flask app exposing the ring generation endpoint (RNG-2, RNG-15).

`/generate-ring` builds the solitaire in-process via build123d driven by
RingSpec. The geometry/export functions are imported into this module's
namespace so tests can patch them at `ringcad.app.*` (where they are looked up).
"""
from __future__ import annotations

from flask import Flask, Response, jsonify, render_template, request

from ringcad.classify import classify_available, classify_ring
from ringcad.geometry import build_solitaire, to_step_bytes, to_stl_bytes
from ringcad.mesh_validator import validate_and_repair
from ringcad.params import ValidationError, validate_params
from ringcad.ringspec import from_params, validate_castability

_SUPPORTED_FORMATS = ("stl", "step")


def _validation_response(error: str, detail: str = "", field=None):
    return jsonify({"error": error, "detail": detail, "field": field}), 400


def _sniff_media_type(b: bytes):
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:4] == b"\x89PNG":
        return "image/png"
    return None


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.post("/generate-ring")
    def generate_ring():
        body = request.get_json(silent=True)
        if not request.is_json or body is None:
            return _validation_response(
                "Invalid request body", "expected a JSON object"
            )

        try:
            params = validate_params(body)
        except ValidationError as exc:
            return _validation_response(exc.error, exc.detail, exc.field)

        spec = from_params(params)

        violations = validate_castability(spec)
        if violations:
            first = violations[0]
            return (
                jsonify(
                    {
                        "error": "Not castable",
                        "detail": first.message,
                        "field": first.field,
                        "violations": [v.model_dump() for v in violations],
                    }
                ),
                400,
            )

        fmt = request.args.get("format", "stl").lower()
        if fmt not in _SUPPORTED_FORMATS:
            return _validation_response(
                "Unsupported format",
                f"format must be one of: {', '.join(_SUPPORTED_FORMATS)}",
                "format",
            )

        try:
            solid = build_solitaire(spec)
        except Exception as exc:  # noqa: BLE001 — surface any kernel failure as 400
            return (
                jsonify(
                    {
                        "error": "Geometry generation failed",
                        "detail": str(exc),
                    }
                ),
                400,
            )

        if fmt == "step":
            data = to_step_bytes(solid)
            return Response(
                data,
                mimetype="model/step",
                headers={
                    "Content-Disposition": 'attachment; filename="ring.step"',
                },
            )

        raw = to_stl_bytes(solid)
        outcome = validate_and_repair(raw)
        return Response(
            outcome.stl_bytes,
            mimetype="model/stl",
            headers={
                "Content-Disposition": 'attachment; filename="ring.stl"',
                "X-Mesh-Valid": "true" if outcome.mesh_valid else "false",
                "X-Mesh-Repaired": (
                    "true" if outcome.mesh_repaired else "false"
                ),
                "X-Mesh-Repair-Detail": outcome.detail,
            },
        )

    @app.post("/classify-ring")
    def classify_ring_route():
        file = request.files.get("image")
        if file is None:
            return _validation_response(
                "Missing image", "field 'image' is required", "image"
            )
        image_bytes = file.read()
        if not image_bytes:
            return _validation_response(
                "Empty image", "uploaded file was empty", "image"
            )
        if len(image_bytes) > 8 * 1024 * 1024:
            return _validation_response(
                "Image too large", "maximum size is 8 MB", "image"
            )
        media_type = _sniff_media_type(image_bytes)
        if media_type is None:
            return _validation_response(
                "Unsupported image type",
                "only JPEG and PNG are accepted",
                "image",
            )
        if not classify_available():
            return (
                jsonify(
                    {
                        "error": "Photo classification is not configured",
                        "detail": "set ANTHROPIC_API_KEY to enable",
                    }
                ),
                503,
            )
        result = classify_ring(image_bytes, media_type)
        if not result.ok:
            return (
                jsonify(
                    {
                        "error": "Classification failed",
                        "detail": (
                            "the vision service could not process this image"
                        ),
                    }
                ),
                502,
            )
        return jsonify(result.to_json()), 200

    return app


app = create_app()
