# AI Manager Catalog API — v2.4.10

FastAPI backend for the AI Manager test release. The sole active automotive catalogue provider is TradeSoft OEM Parts.Catalogs. All provider credentials remain server-side.

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

- `GET /health` — backend process health and active provider state; does not prove upstream reachability.
- `GET /api/catalog/v1/providers` — active TradeSoft provider and nine reserved slots.
- `POST /api/catalog/v1/vehicles/decode` — real TradeSoft VIN decode.
- `POST /api/catalog/v1/lookup` — `groups`, `diagrams`, `parts` and `models` requests. For `parts`, send `group_id` after selecting a group to retrieve OE part numbers and diagram callouts; without `group_id`, `q` searches schemas by part name.
- `GET /api/admin/traces` — recent provider request trace; requires the `X-Admin-Token` header and a server-side `ADMIN_API_TOKEN`.
- `GET /docs` — interactive API documentation.

## Request examples

```json
POST /api/catalog/v1/vehicles/decode
{"vin":"WVWZZZAUZJP594600","lang":"ru"}
```

```json
POST /api/catalog/v1/lookup
{"mode":"groups","vin":"WVWZZZAUZJP594600","lang":"ru"}
```

```json
POST /api/catalog/v1/lookup
{"mode":"diagrams","vin":"WVWZZZAUZJP594600","lang":"ru"}
```

```json
POST /api/catalog/v1/lookup
{"mode":"parts","vin":"WVWZZZAUZJP594600","q":"brake pads","lang":"en"}
```

```json
POST /api/catalog/v1/lookup
{"mode":"parts","vin":"WVWZZZAUZJP594600","group_id":"<selected-group-id>","lang":"ru"}
```

## Environment

- `TRADESOFT_API_TOKEN` — required API key, set only in Railway service variables.
- `TRADESOFT_ENABLED=true` — enables the primary OEM provider.
- `CATALOG_TIMEOUT_SECONDS=25` — upstream timeout.
- `CORS_ORIGINS` — allowed browser origins.

The Parts-Info key is not read by this backend and is not used for catalogue lookup.

## Verification limits

A successful health check confirms only that the FastAPI process is running. A successful provider request is required to prove the API key, network access, trial entitlement and VIN coverage. OEM fitment must come from TradeSoft's returned catalogue data; the LLM is not an authority for compatibility, price, stock or order creation.


## Security configuration

- `ADMIN_API_TOKEN` — required server-side secret for the diagnostic trace endpoint. Without it, the endpoint is disabled; never place this token in frontend JavaScript or commit it to Git.
- `CORS_ORIGINS` — comma-separated exact origins. Wildcard entries are ignored; when unset, the backend uses the published GitHub Pages origin, the Railway origin, and local development origins.
- Diagnostic traces mask VIN values, including VINs embedded in free-text details. Do not add raw customer identifiers to trace messages.
- The browser's diagnostic panel cannot read protected traces without an authenticated admin client. This is intentional; public customer traffic must not receive operator diagnostics.


## Admin analytics (demo)

- `GET /api/admin/analytics?days=7|30|90` — request, conversation, message, VIN decode, lookup, error and latency aggregates.
- `GET /api/admin/conversations?days=7|30|90` — per-conversation activity and elapsed duration.
- `POST /api/analytics/events` — customer-chat lifecycle and message events; the browser sends a non-sensitive conversation ID.
- `admin.html` — separate static administrator dashboard. It calls the Railway API and requires the server-side `ADMIN_API_TOKEN`.
- Analytics are persisted in PostgreSQL table `ai_manager_analytics_events`; `psycopg[binary]` is required.
- If `DATABASE_URL` is missing or PostgreSQL is unavailable, analytics endpoints return HTTP 503 and customer chat requests continue without being blocked.
- Current demo build intentionally records a single `default` tenant. Real per-company isolation must be connected to authenticated tenant identity before multi-tenant production; the API does not trust a browser-supplied tenant ID.
- A vehicle confirmation is counted separately from a successful parts selection. A confirmed compatible part must only be counted after the actual part-selection/fitment UI emits `selection_success`.
