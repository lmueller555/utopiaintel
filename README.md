# Utopia Intel

Utopia Intel is a unified Flask application for collecting and reviewing
explicitly captured Utopia game intel. One Gunicorn process serves the public
HTML dashboard, manual capture form, ingestion API, and health check; SQLAlchemy
stores every accepted report in SQLite for local development or Heroku Postgres
in production.

`capture/utopia_intel.user.js` is an optional, user-triggered userscript. It adds
a **Send intel** button to Utopia pages and sends the visible page to the deployed
API only when the member clicks it. Review the game's current rules before
installing or distributing the capture client.

## Architecture

```text
Utopia page + userscript ──POST /api/v1/intel-submissions──┐
                                                           ▼
Kingdom member ──HTTPS──> Flask dashboard/API ──> PostgreSQL
```

The dashboard and API share one process, hostname, release, configuration, and
database. Dashboard pages are publicly accessible; capture clients use an
ingestion key to prevent unauthorized submissions.

## Local setup

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Replace the example secrets, export the file, and run Flask:

```bash
set -a
source .env
set +a
flask --app api.app:create_app run --port 8000
```

Open <http://127.0.0.1:8000> and use the manual form or API. Local development
defaults to `utopiaintel.db`.

Generate independent production secrets with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

## Submit game data

Capture clients authenticate with the ingestion key:

```bash
curl --fail-with-body \
  -X POST http://127.0.0.1:8000/api/v1/intel-submissions \
  -H "Authorization: Bearer YOUR_INGESTION_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "data_simple": "Survey for The Province of Example (1:2)",
    "url": "https://utopia-game.com/",
    "prov": "Our Province"
  }'
```

Legacy form clients may provide the token in the `key` field. A successful
request returns HTTP 201 and a stable submission ID. `GET /health` checks the
web process, database connection, and application table, and reports the active
database backend and number of stored submissions. `GET /api/v1` lists API
routes.

## Deploy to Heroku

The repository includes the Heroku-compatible `Procfile`:

```text
web: gunicorn 'api.app:create_app()'
```

1. Create a Heroku application from this repository and branch.
2. In the application's **Resources** tab, add a Heroku Postgres resource using
   an appropriate currently available plan. Heroku supplies `DATABASE_URL`.
3. In **Settings → Config Vars**, add:

   ```text
   INGESTION_API_KEY=<independent random secret>
   SECRET_KEY=<independent random secret>
   ALLOWED_ORIGINS=https://utopia-game.com,https://www.utopia-game.com
   MAX_PAYLOAD_BYTES=1048576
   ```

4. Deploy the application. The database schema is initialized when the web
   process starts.
5. Verify `https://YOUR-HEROKU-APP.herokuapp.com/health` reports
   `"database":"connected"` and `"database_backend":"postgresql"`.
6. Open the public application root and repeat the test submission against the
   HTTPS endpoint.
7. Install `capture/utopia_intel.user.js`. Enter
   `https://YOUR-HEROKU-APP.herokuapp.com/api/v1/intel-submissions`, the
   ingestion key, and your province when prompted. Shift-click **Send intel** to
   replace saved settings.

See [`docs/HEROKU_DEPLOYMENT.md`](docs/HEROKU_DEPLOYMENT.md) for the complete
deployment and verification checklist.

## Configuration

| Variable | Required in production | Purpose |
|---|---:|---|
| `DATABASE_URL` | Yes | Heroku Postgres connection; local default is SQLite |
| `INGESTION_API_KEY` | Yes | Bearer token accepted by capture clients |
| `SECRET_KEY` | Yes | Signs CSRF-protection sessions for the manual submission form |
| `MAX_PAYLOAD_BYTES` | No | Maximum combined HTML/text size; defaults to 1 MiB |
| `ALLOWED_ORIGINS` | No | Browser origins allowed to call the ingestion API |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Security notes

- Use independent random values for `INGESTION_API_KEY` and `SECRET_KEY`.
- Rotate the ingestion key promptly if it is exposed.
- Keep PostgreSQL credentials in Heroku config; never put `DATABASE_URL` in a
  browser client.
- Captured HTML is untrusted. The dashboard renders only escaped plain text.
- Dashboard pages and stored intel are public. Do not submit data that should not
  be publicly visible.
- Review the game's current rules before distributing the capture client.
