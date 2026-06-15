"""Flask app exposing the STL generation endpoint (RNG-2).

`render_scad`/`openscad_available` are imported into this module's namespace so
tests can patch them at `ringcad.app.*` (where they are looked up).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from ringcad.classify import classify_available, classify_ring
from ringcad.mesh_validator import validate_and_repair
from ringcad.params import ValidationError, validate_params
from ringcad.render import openscad_available, render_scad

SCAD_PATH = Path(__file__).resolve().parents[1] / "scad" / "solitaire.scad"


def _render_fn() -> int:
    return int(os.environ.get("RENDER_FN", "24"))


def _render_timeout() -> float:
    return float(os.environ.get("RENDER_TIMEOUT", "120"))


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

        if not openscad_available():
            return (
                jsonify(
                    {
                        "error": "OpenSCAD is not available",
                        "detail": "openscad binary not found on PATH",
                    }
                ),
                503,
            )

        timeout = _render_timeout()
        with tempfile.TemporaryDirectory() as td:
            stl_path = Path(td) / "ring.stl"
            try:
                result = render_scad(
                    SCAD_PATH,
                    stl_path,
                    params=params,
                    fn=_render_fn(),
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return (
                    jsonify(
                        {
                            "error": "Render timed out",
                            "detail": f"exceeded {timeout}s",
                        }
                    ),
                    400,
                )

            if not result.ok:
                return (
                    jsonify(
                        {
                            "error": "OpenSCAD render failed",
                            "openscad_stderr": result.stderr,
                        }
                    ),
                    400,
                )

            stl_bytes = stl_path.read_bytes()
            outcome = validate_and_repair(stl_bytes)

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
