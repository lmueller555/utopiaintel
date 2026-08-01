"""Unified Flask application for capturing and reviewing Utopia intel."""

from __future__ import annotations

import hmac
import secrets

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Settings
from app.database import (
    IntelSubmission,
    initialize_database,
    make_engine,
    make_session_factory,
    session_scope,
)
from app.ingestion import IngestionError, SubmissionPayload, ingest


def _provided_key(data) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return str(data.get("key") or "")


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _valid_csrf() -> bool:
    provided = str(request.form.get("csrf_token") or "")
    expected = str(session.get("csrf_token") or "")
    return bool(expected) and hmac.compare_digest(provided, expected)


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.load()
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.update(
        MAX_CONTENT_LENGTH=settings.max_payload_bytes + 64 * 1024,
        SECRET_KEY=settings.secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.database_url.startswith("postgresql"),
    )
    engine = make_engine(settings.database_url)
    initialize_database(engine)
    session_factory = make_session_factory(engine)
    app.extensions["utopia_settings"] = settings
    app.extensions["utopia_session_factory"] = session_factory
    app.jinja_env.globals["csrf_token"] = _csrf_token

    @app.get("/")
    def index():
        return redirect(url_for("dashboard"))

    @app.get("/dashboard")
    def dashboard():
        with session_scope(session_factory) as db_session:
            total = db_session.scalar(select(func.count()).select_from(IntelSubmission)) or 0
            targets = db_session.scalar(
                select(func.count(func.distinct(IntelSubmission.target_province))).where(
                    IntelSubmission.target_province != "Unknown"
                )
            ) or 0
            submitters = db_session.scalar(
                select(func.count(func.distinct(IntelSubmission.submitter_province)))
            ) or 0
            rows = list(
                db_session.scalars(
                    select(IntelSubmission)
                    .order_by(IntelSubmission.received_at.desc())
                    .limit(100)
                )
            )
            counts = db_session.execute(
                select(IntelSubmission.intel_type, func.count(IntelSubmission.id))
                .group_by(IntelSubmission.intel_type)
                .order_by(func.count(IntelSubmission.id).desc())
            ).all()
        maximum_count = max((count for _, count in counts), default=0)
        return render_template(
            "dashboard.html",
            total=total,
            targets=targets,
            submitters=submitters,
            rows=rows,
            counts=counts,
            maximum_count=maximum_count,
            insecure_key=settings.ingestion_api_key == "change-me",
            sqlite_database=settings.database_url.startswith("sqlite"),
        )

    @app.post("/submissions")
    def manual_submission():
        if not _valid_csrf():
            abort(400, "Invalid CSRF token.")
        try:
            payload = SubmissionPayload.from_mapping(request.form)
            with session_scope(session_factory) as db_session:
                submission = ingest(db_session, payload, settings.max_payload_bytes)
            flash(f"Stored submission {submission.id[:8]}…", "success")
        except IngestionError as exc:
            flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.get("/submissions/<submission_id>")
    def submission_detail(submission_id: str):
        with session_scope(session_factory) as db_session:
            submission = db_session.get(IntelSubmission, submission_id)
        if submission is None:
            abort(404)
        return render_template("submission_detail.html", submission=submission)

    @app.get("/api/v1")
    def api_index():
        return jsonify(
            {
                "service": "Utopia Intel",
                "health": "/health",
                "submissions": "/api/v1/intel-submissions",
            }
        )

    @app.after_request
    def add_security_and_cors_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if settings.database_url.startswith("postgresql"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
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
            with session_scope(session_factory) as db_session:
                # Query the application table, rather than only issuing SELECT 1,
                # so this check also verifies that the schema is ready for captures.
                submissions = (
                    db_session.scalar(select(func.count()).select_from(IntelSubmission))
                    or 0
                )
        except SQLAlchemyError:
            return jsonify({"status": "unavailable", "database": "disconnected"}), 503
        return jsonify(
            {
                "status": "ok",
                "database": "connected",
                "database_backend": engine.dialect.name,
                "submissions": submissions,
            }
        )

    @app.errorhandler(413)
    def payload_too_large(_error):
        message = "The request exceeds the configured payload size limit."
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": message}), 413
        flash(message, "error")
        return redirect(url_for("dashboard")), 303

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
            with session_scope(session_factory) as db_session:
                submission = ingest(db_session, payload, settings.max_payload_bytes)
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
