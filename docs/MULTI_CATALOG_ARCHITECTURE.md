# Multi-catalog architecture — AI Manager 2.4.11

## Active provider integrations

AI Manager queries independent OEM sources in parallel where the operation is supported.

1. **TradeSoft OEM Parts.Catalogs** — primary provider when `TRADESOFT_ENABLED=true` and `TRADESOFT_API_TOKEN` is configured. Supports VIN decoding, catalogue identity, vehicle groups, diagrams/schemas, group parts, OE numbers and diagram callouts. Credentials remain server-side. TradeSoft's API key is sent in the documented raw `Authorization` header.
2. **SoloCatalog MCP** — secondary OEM parts catalogue. Uses the documented Streamable HTTP MCP endpoint `https://solocatalog.com/mcp` and tool discovery. Light-use allowance works without a key; an optional `SOLOCATALOG_API_KEY` is sent as Bearer authentication. Supports VIN decode, parts search, diagrams and diagram parts. TradeSoft group IDs are not passed to SoloCatalog because they are provider-specific.
3. **NHTSA vPIC** — free public VIN decoder used only as a vehicle-data cross-check/fallback. It is not a parts catalogue, does not prove OEM fitment, and never authorizes parts search by itself.

## Selection safety

- TradeSoft is preferred when it returns exactly one vehicle with `catalogId` and `carId`.
- If TradeSoft returns multiple vehicle candidates, AI Manager stops and asks for clarification. It does not choose a candidate using another decoder.
- If TradeSoft is unavailable, SoloCatalog can be used only when its response contains a verifiable catalogue identity.
- NHTSA data can display basic vehicle identity, but the UI blocks parts search unless an OEM catalogue has verified the vehicle.
- Parts lookups call TradeSoft and SoloCatalog in parallel where both support the requested operation. Each provider result, status and duration is retained separately.
- TradeSoft group IDs are opaque and are never reused against another provider.
- No LLM-generated fitment, OEM number, stock or price is treated as authoritative.
- Empty or failed provider responses are not replaced with synthetic fixtures.

## Limits and current scope

- Architectural maximum: 10 provider connections per tenant.
- Currently implemented: 2 parts catalogues (TradeSoft and SoloCatalog) plus 1 VIN-only decoder (NHTSA).
- This does **not** mean 10 parts catalogues are already connected. Additional providers require a real adapter, credentials/permission where needed, contract tests and live verification.
- SoloCatalog's no-key MCP allowance is intended for light use and has provider rate/usage limits. For sustained commercial traffic, obtain and configure a provider API key/plan and confirm commercial-use terms.
- The demo currently uses one `default` tenant; this is not production multi-tenant isolation.

## API

- `GET /health` — process, configured-provider and PostgreSQL readiness status
- `GET /api/catalog/v1/providers` — configured provider list and capabilities
- `POST /api/catalog/v1/vehicles/decode` — parallel VIN decoding/cross-check
- `POST /api/catalog/v1/lookup` — parallel parts/diagram lookup where supported
- `GET /api/admin/analytics` — authenticated PostgreSQL analytics
- `GET /api/admin/conversations` — authenticated conversation history
- `GET /docs` — OpenAPI docs

The FastAPI backend serves the customer chat and admin assets from the same Railway origin. GitHub Pages remains a static demo surface; use the Railway app URL for backend-connected testing.
