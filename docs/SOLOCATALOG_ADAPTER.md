# SoloCatalog adapter — v2.1.1

## Purpose

Introduce a provider-specific server adapter without coupling the customer messenger to a catalogue vendor. The first adapter target is SoloCatalog.

## Confirmed provider contract

Based on the provider's published API documentation:

- Base URL: `https://solocatalog.com/api/v1`
- Authentication: `Authorization: Bearer <API key>`
- VIN decode: `POST /vin/decode` with `vin` and optional `lang`
- Quick lookup: `POST /lookup`
  - VIN part search: `{"vin":"...","q":"brake"}`
  - Model candidates: `{"mode":"models","brand":"...","q":"..."}`
  - Diagrams for VIN: `{"mode":"diagrams","vin":"..."}`
  - Diagram parts: `{"mode":"diagram","model":"MODEL_KEY","diagram":"FIGURE_ID"}`
- The provider documents diagram callouts, part rows and image links in its full catalogue operations.

## Adapter endpoints

The FastAPI adapter exposes stable AI Manager-owned routes:

| AI Manager route | Provider operation |
|---|---|
| `POST /api/catalog/v1/vehicles/decode` | `POST /vin/decode` |
| `POST /api/catalog/v1/lookup` | `POST /lookup` |
| `GET /health` | Local adapter configuration only |

Provider-specific model keys and figure IDs are passed through unchanged. They are opaque identifiers and must not be guessed or regenerated.

## Required next engineering steps

1. Deploy `backend/` to a server runtime; GitHub Pages cannot run FastAPI.
2. Add `SOLOCATALOG_API_KEY` to the host's secret manager, never to frontend code or Git.
3. Connect the frontend to the deployed AI Manager API origin.
4. Test a supported VIN end-to-end and inspect the real JSON for vehicle, diagram, callout, part and image fields.
5. Only then define a canonical internal schema and persist data if the provider agreement permits it.
6. Verify written permission for commercial SaaS display, multi-tenant use, retention and image delivery.

## Explicit non-goals in v2.1.1

- No live provider key is included.
- No API call is made by the GitHub Pages demo.
- No backend service is deployed by the Pages workflow.
- No real vehicle compatibility or OEM fitment is asserted.
- No catalogue bulk import or public caching is implemented.
