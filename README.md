# Utopia Intel

A small, deployable foundation for collecting Utopia intel and reviewing it in a
Streamlit dashboard. The repository contains:

- a **Streamlit app** for manually submitting and visualizing captured intel;
- a **Flask ingestion API** for browser extensions or userscripts;
- a shared **SQLAlchemy persistence layer** that supports SQLite locally and
  PostgreSQL in a deployed environment; and
- tests for authentication, validation, persistence, and parsing.

The application stores every accepted submission before displaying parsed
metadata. It is intentionally limited to ingestion and visibility; wave planning
and combat calculations can be added on top of the same database later.

`capture/utopia_intel.user.js` is an optional, user-triggered userscript that adds
a **Send intel** button to game pages. Install it in a userscript manager, click
the button, and enter the deployed Flask endpoint, ingestion key, and your
province. Shift-click the button to change those settings. Review the game's
current rules before distributing it to kingdom members.

## Architecture

```text
Browser extension/userscript ──POST──> Flask API ──> Database
                                                    ▲
                                                    │
Kingdom member ───────────────> Streamlit dashboard ┘
```

Streamlit Community Cloud runs the dashboard. It does not expose arbitrary Flask
routes, so automated game submissions require deploying `api.app:create_app()`
as a second web service. Both processes use the same `DATABASE_URL` and Python
domain code. The dashboard also includes a manual capture form so a Streamlit-only
deployment can be evaluated immediately.

## Local setup

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Export the settings in `.env` (or load them with your preferred environment
manager), then start the dashboard:

```bash
streamlit run streamlit_app.py
```

In another terminal, start the ingestion endpoint:

```bash
flask --app api.app:create_app run --port 8000
```

The local default database is `utopiaintel.db`. For a shared or production
deployment, set `DATABASE_URL` to a PostgreSQL connection string.

## Submit game data

The API accepts both JSON and the legacy form fields documented by the original
`example.php`. Authenticate with a bearer token:

```bash
curl -X POST http://localhost:8000/api/v1/intel-submissions \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "data_html": "<div>Province of Example</div>",
    "data_simple": "The Province of Example (1:2)\nNetworth: 123,456",
    "url": "https://utopia-game.com/shared/",
    "prov": "Our Province",
    "intel_type": "survey",
    "target_province": "Example",
    "target_kingdom": "1:2"
  }'
```

Legacy form clients may send the token as the `key` form field. A successful
request returns HTTP 201 and a stable submission ID. The API also provides
`GET /health` for deployment health checks.

## Deploy the Streamlit dashboard

1. Push this repository to GitHub.
2. In Streamlit Community Cloud, create an app from the repository.
3. Select `streamlit_app.py` as the entry point.
4. Add secrets based on `.streamlit/secrets.toml.example`.
5. Deploy the app.

For a disposable demonstration, omit `DATABASE_URL` and the app will use SQLite.
Hosted filesystems may be ephemeral, so configure a managed PostgreSQL database
before collecting real kingdom intel.

Example Streamlit secrets:

```toml
DATABASE_URL = "postgresql+psycopg://user:password@host:5432/database"
INGESTION_API_KEY = "a-long-random-secret"
```

## Deploy the ingestion API

Deploy the same repository to any Python web-service host that supports the
included `Procfile` or `Dockerfile`. Use this start command if it is requested:

```bash
gunicorn 'api.app:create_app()'
```

Configure the exact same `DATABASE_URL` as the Streamlit app and set the same
`INGESTION_API_KEY`. Point the game capture tool at:

```text
https://your-api-host.example/api/v1/intel-submissions
```

After deployment, verify the service and its database connection:

```bash
curl --fail https://your-api-host.example/health
```

The response should be `{"database":"connected","status":"ok"}`. Opening the
API's root URL also returns a short index of the available routes. See
[`docs/API_DEPLOYMENT.md`](docs/API_DEPLOYMENT.md) for the complete deployment,
capture-client configuration, and end-to-end verification checklist.

Do not put database credentials in a browser extension. The capture client only
receives a revocable ingestion key.

## Configuration

| Variable | Required | Purpose |
|---|---:|---|
| `DATABASE_URL` | Production | Shared PostgreSQL connection; defaults to local SQLite |
| `INGESTION_API_KEY` | Yes | Secret accepted by the API and manual capture form |
| `MAX_PAYLOAD_BYTES` | No | Maximum combined HTML/text size; defaults to 1 MiB |
| `ALLOWED_ORIGINS` | No | Comma-separated browser origins allowed to submit intel; both Utopia hostnames are allowed by default |

## Tests

```bash
pytest
```

## Security notes

- Use a long random ingestion key and rotate it if it is exposed.
- Restrict access to the Streamlit dashboard before storing sensitive intel.
- The service treats captured HTML as untrusted and displays it only as text.
- Review the game's current rules before installing or distributing an automated
  capture client.
