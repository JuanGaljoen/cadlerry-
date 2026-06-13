"""Flask app exposing the STL generation endpoint (RNG-2).

`render_scad`/`openscad_available` are imported into this module's namespace so
tests can patch them at `ringcad.app.*` (where they are looked up).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, Response, jsonify, request

from ringcad.params import ValidationError, validate_params
from ringcad.render import openscad_available, render_scad

SCAD_PATH = Path(__file__).resolve().parents[1] / "scad" / "solitaire.scad"


def _render_fn() -> int:
    return int(os.environ.get("RENDER_FN", "24"))


def _render_timeout() -> float:
    return float(os.environ.get("RENDER_TIMEOUT", "120"))


def _validation_response(error: str, detail: str = "", field=None):
    return jsonify({"error": error, "detail": detail, "field": field}), 400


def create_app() -> Flask:
    app = Flask(__name__)

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

        return Response(
            stl_bytes,
            mimetype="model/stl",
            headers={"Content-Disposition": 'attachment; filename="ring.stl"'},
        )

    return app


app = create_app()
