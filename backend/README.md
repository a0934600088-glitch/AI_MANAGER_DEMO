# AI Manager Catalog API — v2.2.0

FastAPI backend for the live AI Manager test release. Railway serves the customer interface and API from the same origin.

## Live providers

- **SoloCatalog MCP**: `https://solocatalog.com/mcp`, Streamable HTTP. Light use has a small free daily allowance without a key. Higher volume requires a provider API key; do not put it in frontend code or Git.
- **NHTSA vPIC**: public VIN decoder without a key. It is not an OEM parts catalogue and does not provide parts diagrams.

The API calls SoloCatalog and NHTSA in parallel for VIN decoding. Parts search, diagrams and diagram-part requests are sent to SoloCatalog. Provider results and failures remain separate; synthetic fixtures are not a fallback.

## Deploy

The Railway project `AI Manager v2.1.2` is connected to `a0934600088-glitch/AI_MANAGER_DEMO` and builds from the repository root using the root Dockerfile. The service listens on Railway's `PORT` (currently routed to 8080).

- `GET /health` — process health and provider configuration. This does not prove upstream catalogue reachability.
- `GET /api/catalog/v1/providers` — configured providers and capabilities.
- `POST /api/catalog/v1/vehicles/decode` — real VIN decode via SoloCatalog MCP + NHTSA.
- `POST /api/catalog/v1/lookup` — `parts`, `diagrams`, `diagram`, or `models` lookup via SoloCatalog MCP.
- `GET /docs` — interactive API documentation.

## Request examples

```json
POST /api/catalog/v1/vehicles/decode
{"vin":"WVWZZZAUZJP594600","lang":"ru"}
```

```json
POST /api/catalog/v1/lookup
{"mode":"diagrams","vin":"WVWZZZAUZJP594600","lang":"ru"}
```

```json
POST /api/catalog/v1/lookup
{"mode":"parts","vin":"WVWZZZAUZJP594600","q":"front brake pads","lang":"en"}
```

## Important limits

- A successful health check means only that this FastAPI process is running. Upstream provider reachability is proven only by an actual request.
- NHTSA VIN data must never be presented as OEM fitment confirmation.
- A vehicle decode does not guarantee that a diagram exists for that vehicle. The catalogue response must contain the original diagram/image URL and source callouts before the UI labels it as an OEM diagram.
- No generated or synthetic diagram is used as a fallback.
- The architecture reserves up to 10 provider slots; only SoloCatalog and NHTSA are currently enabled. RockAuto and Tradesoft are not connected.
- SoloCatalog coverage varies by make, market and source release. Its light no-key allowance is limited and subject to provider terms/rate limits.
- Verify commercial display, storage and multi-tenant usage rights before commercial rollout. The provider's terms prohibit automated scraping, bulk extraction and unauthorized reuse.

## Local development

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

No API key is required for the documented light-use MCP allowance. For higher volume, configure `SOLOCATALOG_API_KEY` server-side and pass it as a Bearer header in the MCP client. Never commit secrets.


## Language and translation
- `GET /api/language/v1/languages` — core UI languages and languages available in the Argos model index.
- `POST /api/language/v1/translate` — batch translation using `source`, `target`, and `domain` (`general` or `automotive`).
- Uses self-hosted open-source Argos Translate models. Models download on first use and are cached in the container.
- Automotive mode protects VINs, OE/OEM-style references, part identifiers, engine/gearbox codes and measurements; common workshop terms are normalized through the automotive glossary.
- No public third-party translation endpoint receives customer text. Runtime hosting and compute are still infrastructure costs.
