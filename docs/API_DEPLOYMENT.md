# Deploying the ingestion API

The ingestion API receives an explicitly triggered capture from the Utopia
userscript, authenticates it, and stores it in the same database read by the
Streamlit dashboard.

## 1. Provision shared storage

Create a managed PostgreSQL database. Copy its connection string and configure
the **same value** on both the Streamlit app and the API service:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

Do not use the default SQLite URL for two separately deployed services. Each
service would otherwise write to its own local file, and hosted local files may
not be durable.

## 2. Deploy the API

Create a Python web service from this repository on a host that supports a
`Procfile`, Dockerfile, or custom start command. Use:

```bash
gunicorn 'api.app:create_app()'
```

Configure these environment variables on the API service:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
INGESTION_API_KEY=YOUR_LONG_RANDOM_SECRET
ALLOWED_ORIGINS=https://utopia-game.com,https://www.utopia-game.com
MAX_PAYLOAD_BYTES=1048576
```

`DATABASE_URL` and `INGESTION_API_KEY` must exactly match the values configured
for Streamlit. Never put `DATABASE_URL` in a browser script.

## 3. Verify the deployment

Replace `API_HOST` in the commands below with the public API hostname. Confirm
that the process is running and can reach PostgreSQL:

```bash
curl --fail https://API_HOST/health
```

Expected response:

```json
{"database":"connected","status":"ok"}
```

Then make a test submission:

```bash
curl --fail-with-body \
  -X POST https://API_HOST/api/v1/intel-submissions \
  -H "Authorization: Bearer YOUR_LONG_RANDOM_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://utopia-game.com/",
    "prov": "Your Province",
    "data_simple": "Survey for The Province of Example (1:2)"
  }'
```

A successful request has HTTP status `201` and returns a `submission_id`. Reload
the Streamlit dashboard and confirm that the test record appears under **Recent
submissions**. If the API accepts the record but the dashboard does not show it,
the two deployments are almost certainly using different `DATABASE_URL` values.

## 4. Configure game capture

1. Install `capture/utopia_intel.user.js` in a userscript manager.
2. Visit Utopia Game and click **Send intel**.
3. Enter `https://API_HOST/api/v1/intel-submissions` as the Intel API URL.
4. Enter the same ingestion key configured on the API.
5. Enter the submitting province name.
6. Visit an intel page and click **Send intel** again.

Shift-click **Send intel** at any time to replace the saved API URL, key, or
province.

## Troubleshooting

- **`401 Invalid ingestion key`**: the userscript and API keys do not match.
- **Browser CORS error**: confirm `ALLOWED_ORIGINS` contains the exact Utopia
  origin shown in the browser, including the optional `www` hostname.
- **`413` response**: increase `MAX_PAYLOAD_BYTES` on the API if the captured page
  is legitimately larger than the current limit.
- **`503` from `/health`**: verify the API's `DATABASE_URL`, database firewall,
  credentials, and TLS requirements.
- **Submission succeeds but is absent in Streamlit**: configure the exact same
  PostgreSQL `DATABASE_URL` on both services and restart them.

Keep the ingestion endpoint private by possession of the key, rotate an exposed
key promptly, and review the game's current rules before distributing the capture
client.
