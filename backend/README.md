# AI Manager — v2.4.25

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
1. `GET /car/info?q={VIN}` returns vehicle candidates with `catalogId`, `carId`, `criteria` and any parameters included in CarInfo.
2. For one unambiguous match, `GET /catalogs/{catalogId}/cars2/{carId}?criteria={criteria}` retrieves the detailed selected vehicle record and its parameter collection.
3. The backend preserves both raw responses and normalizes named parameter/value rows into the stable `vehicle_attributes` contract used by the customer card.
4. `GET /catalogs/{catalogId}/groups2/` navigates vehicle-specific catalogue groups.
5. `GET /catalogs/{catalogId}/schemas` returns vehicle schemas and can be filtered by `partName`.
6. `GET /catalogs/{catalogId}/parts2` retrieves OE parts, diagram image and callout positions for a selected `groupId`.

The backend preserves the provider's `catalogId`, `carId` and `criteria` values. If the detailed Car2 request is unavailable, the base VIN identity remains available and the response marks `vehicle_details_status=unavailable`; no missing characteristics are fabricated. The enriched VIN result is cached in process memory for 24 hours.

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


## Tenant authentication foundation (feature branch)

The `feature/tenant-auth-rbac` branch introduces database-backed identities and session endpoints:
- `POST /api/auth/login` — verifies a configured/bootstrap administrator or a provisioned tenant user and returns an opaque bearer token.
- `GET /api/auth/me` — returns the authenticated account and role.
- `POST /api/auth/logout` — revokes the presented session.
- `POST /api/admin/tenants` — super-admin-only tenant creation.
- `POST /api/admin/tenants/{tenant_id}/users` — creates shop-admin, manager, or observer accounts, with tenant binding enforced server-side.

On first successful login, the backend creates the initial `super_admin` account from the existing server-only `ADMIN_USERNAME` and `ADMIN_PASSWORD` variables. The password is hashed with scrypt; only a SHA-256 digest of each random session token is stored. Tenant users require passwords of at least 12 characters.

**This is an implementation stage, not a production-ready release yet.** Existing analytics and conversation APIs still use the legacy demo tenant and have not yet been migrated to authenticated tenant scoping. The frontend login/manager console, tenant-aware customer event ingestion, admin tenant listing, session rate limiting, and end-to-end isolation tests remain required before merge and deployment. Do not create manager accounts for production use until those controls are complete.
