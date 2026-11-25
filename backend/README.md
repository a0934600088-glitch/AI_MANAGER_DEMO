# AI Manager Catalog API

The release version has one canonical source: `backend/VERSION`. The backend reads it at startup and returns it from `GET /health`. Frontend pages display that backend version; do not maintain separate frontend/backend version constants.

FastAPI backend for the AI Manager test release. The sole active automotive catalogue provider is TradeSoft OEM Parts.Catalogs. Provider credentials remain server-side.

## Active provider

- **TradeSoft OEM Parts.Catalogs** — VIN/FRAME lookup, vehicle-specific catalogue schemas, group navigation and OEM parts/diagram data.
- **Parts-Info** — key may be stored in Railway for a later trial, but this backend does not call it.
- **Reserved provider slots 2–10** — extension points only; no outbound calls are made to unconfigured providers.
- **SoloCatalog MCP and NHTSA vPIC** — disabled and removed from active VIN/parts lookup paths.

## TradeSoft REST API

Base URL: `https://api.parts-catalogs.com/v1`

Authentication: raw API key in the `Authorization` header (no `Bearer` prefix).

Documented flow:
1. `GET /car/info?q={VIN}` returns vehicle candidates with `catalogId`, `carId` and `criteria`.
2. `GET /catalogs/{catalogId}/groups2/` navigates vehicle-specific catalogue groups.
3. `GET /catalogs/{catalogId}/schemas` returns vehicle schemas and can be filtered by `partName`.
4. `GET /catalogs/{catalogId}/parts2` retrieves OE parts, diagram image and callout positions for a selected `groupId`.

The backend preserves the provider's `catalogId`, `carId` and `criteria` values. It caches a VIN decode in process memory for 24 hours to avoid repeating the initial VIN lookup during the same running process.

## API routes

- `GET /health` — backend process health, canonical release version and active provider state; does not prove upstream reachability.
- `GET /api/catalog/v1/providers` — active TradeSoft provider and nine reserved slots.
- `POST /api/catalog/v1/vehicles/decode` — real TradeSoft VIN decode.
- `POST /api/catalog/v1/lookup` — `groups`, `diagrams`, `parts` and `models` requests.
- `GET /api/admin/traces` — recent provider request trace; requires administrator HTTP Basic authentication.
- `GET /api/admin/analytics?days=7|30|90` — analytics aggregates; requires administrator HTTP Basic authentication.
- `GET /api/admin/conversations?days=7|30|90` — per-conversation activity; requires administrator HTTP Basic authentication.
- `POST /api/analytics/events` — customer-chat lifecycle and message events.
- `GET /docs` — interactive API documentation.

## Environment

- `TRADESOFT_API_TOKEN` — TradeSoft upstream API key, set only in Railway/backend service variables. Do not remove unless TradeSoft confirms that this account can authenticate without a key.
- `TRADESOFT_ENABLED=true` — enables the primary OEM provider.
- `CATALOG_TIMEOUT_SECONDS=25` — upstream timeout.
- `CORS_ORIGINS` — exact allowed browser origins.
- `ADMIN_USERNAME` — administrator login.
- `ADMIN_PASSWORD` — administrator password.
- `DATABASE_URL` — PostgreSQL connection string for persistent analytics.

There is no `ADMIN_API_TOKEN`, no `X-Admin-Token` header and no API-token field in either frontend. Admin endpoints use HTTP Basic authentication over HTTPS. The browser keeps the login and password only in page memory and does not save them to local/session storage.

## Verification limits

A successful health check confirms only that the FastAPI process is running. A successful provider request is required to prove the API key, network access, trial entitlement and VIN coverage. OEM fitment must come from TradeSoft's returned catalogue data; the LLM is not an authority for compatibility, price, stock or order creation.

## Analytics notes

- Analytics are persisted in PostgreSQL table `ai_manager_analytics_events`; `psycopg[binary]` is required.
- If `DATABASE_URL` is missing or PostgreSQL is unavailable, analytics endpoints return HTTP 503 and customer chat requests continue without being blocked.
- Current demo build intentionally records a single `default` tenant. Real per-company isolation must be connected to authenticated tenant identity before multi-tenant production; the API does not trust a browser-supplied tenant ID.
- A vehicle confirmation is counted separately from a successful parts selection. A confirmed compatible part must only be counted after the actual part-selection/fitment UI emits `selection_success`.
- Diagnostic traces mask VIN values, including VINs embedded in free-text details. Do not add raw customer identifiers to trace messages.
