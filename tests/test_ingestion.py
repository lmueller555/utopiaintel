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
        allowed_origins=("https://utopia-game.com", "https://www.utopia-game.com"),
    )


def test_health_endpoint(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "database": "connected",
        "database_backend": "sqlite",
        "submissions": 0,
    }


def test_health_endpoint_counts_stored_submissions(tmp_path):
    settings = make_settings(tmp_path)
    client = create_app(settings).test_client()
    response = client.post(
        "/api/v1/intel-submissions",
        headers={"Authorization": "Bearer test-secret"},
        json={
            "url": "https://utopia-game.com/shared/",
            "prov": "Friendly Province",
            "data_simple": "Survey for The Province of Target (1:2)",
        },
    )
    assert response.status_code == 200

    assert client.get("/health").get_json()["submissions"] == 1


def test_root_redirects_to_dashboard(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_api_index_describes_api_routes(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.get("/api/v1")
    assert response.status_code == 200
    assert response.get_json()["submissions"] == "/api/v1/intel-submissions"


def test_dashboard_is_publicly_accessible(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Kingdom dashboard" in response.data


def test_login_route_is_removed(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    assert client.get("/login").status_code == 404


def test_manual_submission_route_is_removed(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    assert client.post("/submissions").status_code == 404
    assert b"Manual entry" not in client.get("/dashboard").data


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

    assert response.status_code == 200
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
    assert response.status_code == 200
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
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]


def test_www_capture_client_preflight_is_supported(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.options(
        "/api/v1/intel-submissions",
        headers={"Origin": "https://www.utopia-game.com"},
    )
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "*"


def test_native_transfer_response_allows_unknown_utopia_origin(tmp_path):
    client = create_app(make_settings(tmp_path)).test_client()
    response = client.post(
        "/api/v1/intel-submissions",
        headers={"Origin": "https://game.example"},
        data={
            "key": "test-secret",
            "url": "https://utopia-game.com/",
            "prov": "Friendly Province",
            "data_simple": "Spy on Throne\nThe Province of Target (1:2)",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert response.headers["Access-Control-Allow-Origin"] == "*"


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
