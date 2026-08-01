# Deploying Utopia Intel on Heroku

The unified Flask process serves the dashboard and ingestion API and connects to
a PostgreSQL resource attached to the same Heroku application.

## 1. Create the application

Push this repository to GitHub, create a Heroku application, and connect the
repository and intended deployment branch. The included `Procfile` starts the
application with Gunicorn:

```text
web: gunicorn 'api.app:create_app()'
```

## 2. Attach PostgreSQL

Open the Heroku application's **Resources** tab, find Heroku Postgres in the
add-on catalog, and select an appropriate currently available plan. Attaching the
resource supplies `DATABASE_URL` to the web process. Do not copy that value into
the userscript or source code.

The application accepts Heroku-style `postgres://` and standard `postgresql://`
URLs and normalizes them for psycopg. It creates the current schema on startup.

## 3. Configure application secrets

Generate two independent secrets locally:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

In **Settings → Config Vars**, configure:

```text
INGESTION_API_KEY=FIRST_RANDOM_VALUE
SECRET_KEY=SECOND_RANDOM_VALUE
ALLOWED_ORIGINS=https://utopia-game.com,https://www.utopia-game.com
MAX_PAYLOAD_BYTES=1048576
```

`INGESTION_API_KEY` authenticates browser captures. `SECRET_KEY` signs the
CSRF-protection session used by the public manual submission form. Do not reuse
one value for both purposes.

## 4. Deploy and verify

After deploying, replace `APP_HOST` below with the assigned Heroku hostname:

```bash
curl --fail https://APP_HOST/health
```

Expected response:

```json
{"database":"connected","database_backend":"postgresql","status":"ok","submissions":0}
```

The `submissions` count increases as captures arrive. If `database_backend` is
`sqlite`, the application is not using the attached Heroku Postgres resource;
confirm that the add-on supplies `DATABASE_URL` to this app and restart it.

With an authenticated Heroku CLI, you can also verify the attachment without
printing its credentials:

```bash
heroku pg:info --app YOUR-HEROKU-APP
heroku config:get DATABASE_URL --app YOUR-HEROKU-APP >/dev/null \
  && echo "DATABASE_URL is configured"
```

Open `https://APP_HOST/` and confirm the public dashboard loads. Then submit a
controlled capture:

```bash
curl --fail-with-body \
  -X POST https://APP_HOST/api/v1/intel-submissions \
  -H "Authorization: Bearer YOUR_INGESTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://utopia-game.com/",
    "prov": "Your Province",
    "data_simple": "Survey for The Province of Example (1:2)"
  }'
```

A successful response has status 200 and contains `submission_id`. Reload the
dashboard and inspect the new record.

## 5. Configure Utopia capture

1. Install `capture/utopia_intel.user.js` in a userscript manager.
2. Visit Utopia and click **Send intel**.
3. Enter `https://APP_HOST/api/v1/intel-submissions` as the Intel API URL.
4. Enter `INGESTION_API_KEY`, never `DATABASE_URL` or `SECRET_KEY`.
5. Enter the submitting province.
6. Navigate to an intel report and click **Send intel** again.
7. Confirm **Intel stored ✓** and check the dashboard.

Shift-click **Send intel** to replace the stored URL, key, or province.

## Operations and troubleshooting

- **401 Invalid ingestion key:** the capture client and Heroku config values do
  not match. Shift-click the capture button and reconfigure it.
- **Browser CORS error:** ensure `ALLOWED_ORIGINS` contains the exact Utopia
  origin, including the optional `www` hostname, then restart the web process.
- **413 response:** increase `MAX_PAYLOAD_BYTES` only for legitimate captures.
- **503 from `/health`:** inspect the PostgreSQL resource, credentials, and
  application logs.
- **Database warning appears:** the process did not receive a PostgreSQL
  `DATABASE_URL` and fell back to local SQLite; verify the resource attachment.

Back up production data, rotate exposed secrets, and review the game's current
rules before distributing the capture client.
