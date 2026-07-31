"""Flask API used by external intel capture clients."""

from __future__ import annotations

import hmac

from flask import Flask, jsonify, make_response, request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.database import initialize_database, make_engine, make_session_factory, session_scope
from app.ingestion import IngestionError, SubmissionPayload, ingest


def _provided_key(data) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return str(data.get("key") or "")


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.load()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_payload_bytes + 64 * 1024
    engine = make_engine(settings.database_url)
    initialize_database(engine)
    session_factory = make_session_factory(engine)

    @app.get("/")
    def index():
        return jsonify(
            {
                "service": "Utopia Intel ingestion API",
                "health": "/health",
                "submissions": "/api/v1/intel-submissions",
            }
        )

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin and ("*" in settings.allowed_origins or origin in settings.allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response.headers["Vary"] = "Origin"
        return response

    @app.get("/health")
    def health():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return jsonify({"status": "unavailable", "database": "disconnected"}), 503
        return jsonify({"status": "ok", "database": "connected"})

    @app.errorhandler(413)
    def payload_too_large(_error):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "The request exceeds the configured payload size limit.",
                }
            ),
            413,
        )

    @app.route("/api/v1/intel-submissions", methods=["POST", "OPTIONS"])
    def create_submission():
        if request.method == "OPTIONS":
            return make_response("", 204)
        data = request.get_json(silent=True) if request.is_json else request.form
        data = data or {}
        if not hmac.compare_digest(_provided_key(data), settings.ingestion_api_key):
            return jsonify({"success": False, "error": "Invalid ingestion key."}), 401

        try:
            payload = SubmissionPayload.from_mapping(data)
            with session_scope(session_factory) as session:
                submission = ingest(session, payload, settings.max_payload_bytes)
                result = {
                    "success": True,
                    "submission_id": submission.id,
                    "parser_status": submission.parser_status,
                    "intel_type": submission.intel_type,
                    "target_province": submission.target_province,
                    "target_kingdom": submission.target_kingdom,
                }
        except IngestionError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        return jsonify(result), 201

    return app
