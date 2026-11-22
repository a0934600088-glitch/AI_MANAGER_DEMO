# AI Manager Catalog Adapter (SoloCatalog)

This is server-side source code. It is not deployed by GitHub Pages and is not called by the static demo yet.

## Requirements

- Python 3.11+
- A SoloCatalog API key created in the provider account
- Provider access within its free-request or paid subscription allowance

## Run locally

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, set `SOLOCATALOG_API_KEY` in your local environment, then run:

```bash
uvicorn app.main:app --reload --port 8000
```

For a quick local setup, export the variables from `.env` using your shell or configure them in your IDE. Do not commit `.env`.

## Adapter endpoints

- `GET /health` — reports whether a provider key is configured; it does not call the provider.
- `POST /api/catalog/v1/vehicles/decode` — proxies the documented VIN decode operation.
- `POST /api/catalog/v1/lookup` — proxies the documented quick lookup modes: models, diagrams, diagram parts, and text/part search.

Interactive API documentation is available at `/docs` when the local server is running.

## Security and current limits

- The provider key is read only from the backend environment variable `SOLOCATALOG_API_KEY`.
- The key is never sent to the browser or returned by `/health`.
- CORS defaults to local development origins. Set `CORS_ORIGINS` to the exact trusted frontend origins before deployment.
- The adapter forwards provider JSON without inventing a normalized fitment schema.
- Provider HTTP errors are converted to controlled API errors; upstream response bodies are not exposed.
- No provider response is persisted, cached, or bulk-imported.
- This repository's GitHub Pages workflow publishes static files only. It does not deploy this FastAPI service.

Before production use, confirm commercial display/storage rights, test coverage for target vehicle makes, configure secrets on a real backend host, and add tenant-level quotas, audit logging, retries and integration tests.
