# AI Manager — v2.4.28

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
- `GET /api/admin/traces` — recent provider request trace; requires a valid bearer session for the `super_admin` role.
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

- `ADMIN_USERNAME` / `ADMIN_PASSWORD` — server-side bootstrap credentials for the first platform administrator. The password is hashed before storage.
- `ADMIN_API_TOKEN` — retained only for a legacy helper; the current trace route uses bearer-session authorization.
- `CORS_ORIGINS` — comma-separated exact origins. Set `TENANT_CORS_ENABLED=true` only when tenant widgets must run on external shop domains; tenant-key requests are separately checked against the configured domain allowlist. Wildcard entries are ignored; when unset, the backend uses the published GitHub Pages origin, the Railway origin, and local development origins.
- Diagnostic traces mask VIN values, including VINs embedded in free-text details. Do not add raw customer identifiers to trace messages.
- The browser's diagnostic panel cannot read protected traces without an authenticated admin client. This is intentional; public customer traffic must not receive operator diagnostics.


## Tenant data attribution and public widget identity (v2.4.28)

- Every tenant receives a random public widget key; only its SHA-256 digest is stored.
- Customer widget requests send `X-Tenant-Key`. The API resolves the tenant server-side and verifies that the HTTPS `Origin` host is in that tenant's allowed-domain list.
- Analytics events, request telemetry, VIN decode telemetry and OEM lookup telemetry are written with the resolved tenant ID. The browser cannot choose a tenant ID.
- Store administrators can rotate the public key and update their own store's allowed domains; platform administrators can configure any store.
- The widget accepts `window.AI_MANAGER_TENANT_KEY` before its main script executes. For external store domains, set `TENANT_CORS_ENABLED=true` on the backend; actual requests are still checked against the tenant's configured domain.
- Existing events with `tenant_id='default'` remain in the legacy demo scope; they are not reassigned to a new store.
- This release does not yet contain a durable customer profile/transcript store. Conversation reporting is based on tenant-scoped analytics events only. Do not interpret this as complete CRM history isolation.



## Authentication and authorization

- Bearer sessions are database-backed, opaque, expire after seven days, and are revocable.
- Roles are `super_admin`, `shop_admin`, `manager`, and `observer`.
- Tenant staff are bound to one tenant in the database. Shop administrators can manage staff only in their own shop and cannot create another shop administrator. Managers and observers cannot manage staff or platform tenants.
- Analytics and conversation summaries always query using the server-derived tenant scope for shop users. The super administrator's legacy overview remains scoped to the legacy `default` demo data.

## OEM diagram identity safeguard (v2.4.28)

When a part-name search returns a selected original schema, the adapter verifies that the `parts2` diagram image is the same image. If TradeSoft returns a complete but different diagram, the adapter maps the selected schema image to a VIN-specific `groups2` leaf and accepts only a matching complete `parts2` response. If no exact match exists, the lookup fails closed instead of presenting a different diagram.

## VIN group-tree fallback (v2.4.28)

When the likely category root does not contain the selected schema image, the adapter searches the remaining VIN-specific group roots. Provider `hasParts` metadata is treated as advisory; a candidate is accepted only if its `parts2` response is complete and the returned image exactly matches the selected schema.

## Release limitations

- PostgreSQL integration tests run in CI against an ephemeral PostgreSQL 16 service and verify two-tenant event/conversation isolation plus tenant-key/domain binding.
- Production migration rehearsal, backup/restore validation and post-deployment smoke tests have not yet been performed.
- Session rate limiting, lockout, invitation email flow, durable customer profiles and full chat transcripts are not implemented.
- This release isolates existing analytics and request telemetry; it is not a complete CRM/customer-history implementation.
