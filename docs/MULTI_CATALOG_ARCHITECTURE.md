# Multi-catalog architecture — up to 10 providers

## Decision

AI Manager supports up to **10 catalog provider connections per tenant**. A provider is an independent adapter; credentials and provider-specific request formats stay on the backend. The browser never receives provider secrets.

The first test adapter is **SoloCatalog**. Its official API documentation currently states that an account includes 100 free API requests; API requests require an API key sent in the server-side `Authorization: Bearer ...` header. This is a limited evaluation allowance, not an unlimited free production API.

## Important distinction

- **SoloCatalog**: parts-catalog API with VIN/frame lookup, model candidates, parts search, diagrams and diagram positions. This is the initial parts-catalog test provider.
- **NHTSA vPIC**: free public VIN decoder for manufacturer-reported vehicle data. It is useful as an additional vehicle-identification source, but it is **not** an OEM parts catalog and does not provide the original parts diagrams or OEM parts lookup required by the AI Manager workflow.

## Provider slots

The platform limit is 10 configured provider connections. Each connection has:
- internal provider ID and display name;
- adapter type and enabled/disabled state;
- credentials stored only as backend secrets;
- priority and timeout;
- supported capabilities (VIN decode, vehicle search, diagrams, diagram positions, OEM lookup, aftermarket cross-references);
- health and last-error state.

A slot is not considered operational merely because it is configured. It becomes operational only after a successful provider health/authentication check.

## Search and reconciliation

1. Normalize the customer's VIN, part query and language once.
2. Query enabled providers in parallel, subject to per-provider timeouts and rate limits.
3. Preserve the source/provider ID on every vehicle, diagram, OEM number and cross-reference.
4. Deduplicate exact matches, but do not merge conflicting fitment claims.
5. Rank results using explicit evidence: VIN/vehicle match, catalog modification, OEM number, production dates and provider confidence.
6. If catalogs disagree, show the conflict and ask for vehicle/part-position confirmation. Never let the language model guess compatibility.
7. Return partial results when one provider is unavailable; record provider errors separately.
8. Cache only where provider terms permit it and apply tenant quotas/audit logging before production.

## Rollout

- Phase 1: SoloCatalog live test adapter (100 free API requests available per account according to its documentation).
- Phase 2: NHTSA vPIC as a separate free VIN-decoding source, not a parts-catalog substitute.
- Phase 3: Parts-Catalogs / Tradesoft adapter after its exact API contract and account credentials are confirmed.
- Phase 4: add further catalog adapters one by one, up to 10 connections.

## Current repository state

The repository already contains an initial SoloCatalog FastAPI adapter in `backend/app/main.py`. The static GitHub Pages demo does not call that backend yet. The Railway workspace previously checked for this project had no deployed project/service, so there is no live backend URL to configure in the browser. The API key must be entered directly into the backend host's secret-variable settings; never commit it or paste it into chat.

## Required next implementation steps

1. Convert the current single-provider proxy into a provider registry and aggregation service.
2. Add per-tenant provider configuration with a hard maximum of 10 connections.
3. Add provider health/authentication checks and partial-result/error reporting.
4. Deploy the backend and set the SoloCatalog key securely.
5. Connect the chat VIN and diagram-selection flow to the backend and test a real VIN.
