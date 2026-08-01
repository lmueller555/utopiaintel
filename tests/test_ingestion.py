from sqlalchemy import select

from app.config import Settings
from app.database import IntelSubmission, make_engine, make_session_factory, session_scope
from api.app import create_app


def make_settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        ingestion_api_key="test-secret",
        max_payload_bytes=1024,
        secret_key="test-session-secret",
        dashboard_password="dashboard-secret",
        allowed_origins=("https://utopia-game.com", "https://www.utopia-game.com"),
    )


def test_health_endpoint(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "connected"}


def test_root_redirects_to_authenticated_dashboard(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_api_index_describes_api_routes(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.get("/api/v1")
    assert response.status_code == 200
    assert response.get_json()["submissions"] == "/api/v1/intel-submissions"


def test_dashboard_requires_login(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_dashboard_login_and_logout_are_csrf_protected(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    client.get("/login")
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["csrf_token"]

    response = client.post(
        "/login",
        data={"password": "dashboard-secret", "csrf_token": csrf_token},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    assert b"Kingdom dashboard" in client.get("/dashboard").data

    response = client.post("/logout", data={"csrf_token": "invalid"})
    assert response.status_code == 400


def test_manual_submission_uses_shared_dashboard_database(tmp_path):
    settings = make_settings(tmp_path)
    client = create_app(settings).test_client()
    with client.session_transaction() as browser_session:
        browser_session["authenticated"] = True
        browser_session["csrf_token"] = "csrf-secret"

    response = client.post(
        "/submissions",
        data={
            "csrf_token": "csrf-secret",
            "url": "https://utopia-game.com/",
            "prov": "Dashboard Province",
            "data_simple": "Survey for The Province of Web Target (3:4)",
        },
    )
    assert response.status_code == 302
    dashboard = client.get("/dashboard")
    assert b"Web Target" in dashboard.data
    assert b"Dashboard Province" in dashboard.data

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as db_session:
        submission = db_session.scalar(select(IntelSubmission))
        assert submission is not None
        detail = client.get(f"/submissions/{submission.id}")
    assert detail.status_code == 200
    assert b"Survey for The Province of Web Target" in detail.data


def test_json_submission_is_authenticated_and_persisted(tmp_path):
    settings = make_settings(tmp_path)
    client = create_app(settings).test_client()
    response = client.post(
        "/api/v1/intel-submissions",
        headers={"Authorization": "Bearer test-secret"},
        json={
            "url": "https://utopia-game.com/shared/",
            "prov": "Friendly Province",
            "data_simple": "Spy on Throne\nThe Province of Target Province (4:5)",
            "data_html": "<div>captured</div>",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["intel_type"] == "spy on throne"
    assert response.get_json()["target_province"] == "Target Province"
    assert response.get_json()["target_kingdom"] == "4:5"

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        submission = session.scalar(select(IntelSubmission))
        assert submission is not None
        assert submission.submitter_province == "Friendly Province"
        assert submission.raw_html == "<div>captured</div>"


def test_legacy_form_key_is_supported(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.post(
        "/api/v1/intel-submissions",
        data={
            "key": "test-secret",
            "url": "https://utopia-game.com/",
            "prov": "Friendly Province",
            "data_simple": "Survey for The Province of Target (1:2)",
        },
    )
    assert response.status_code == 201
    assert response.get_json()["intel_type"] == "survey"


def test_invalid_key_is_rejected(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.post(
        "/api/v1/intel-submissions",
        headers={"Authorization": "Bearer incorrect"},
        json={"url": "https://utopia-game.com/"},
    )
    assert response.status_code == 401


def test_invalid_payload_returns_helpful_error(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.post(
        "/api/v1/intel-submissions",
        headers={"Authorization": "Bearer test-secret"},
        json={"url": "not-a-url", "prov": "Friendly", "data_simple": "intel"},
    )
    assert response.status_code == 400
    assert "absolute HTTP(S) URL" in response.get_json()["error"]


def test_capture_client_preflight_is_supported(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.options(
        "/api/v1/intel-submissions",
        headers={"Origin": "https://utopia-game.com"},
    )
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "https://utopia-game.com"
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]


def test_www_capture_client_preflight_is_supported(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.options(
        "/api/v1/intel-submissions",
        headers={"Origin": "https://www.utopia-game.com"},
    )
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "https://www.utopia-game.com"


def test_oversized_request_returns_json_error(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.post(
        "/api/v1/intel-submissions",
        headers={
            "Authorization": "Bearer test-secret",
            "Content-Type": "application/json",
        },
        data=b'{' + b'"padding":"' + (b"x" * (70 * 1024)) + b'"}',
    )
    assert response.status_code == 413
    assert response.is_json
    assert response.get_json()["success"] is False
