# SoloCatalog secondary OEM adapter — AI Manager 2.4.11

## Connection

- Streamable HTTP MCP endpoint: `https://solocatalog.com/mcp`
- Protocol: MCP 2025-03-26
- Light-use allowance works without a key.
- Optional API key: `SOLOCATALOG_API_KEY`, sent only from the backend as `Authorization: Bearer <key>`.
- The API key must never be stored in frontend code, browser storage, query strings or Git.

The adapter performs `initialize`, `tools/list` and `tools/call` per request, reads the live tool schema and sends only arguments accepted by the provider. It supports `decode_vin`, `search_parts`, `find_models`, `list_diagrams` and `get_diagram_parts`.

## AI Manager routes

| AI Manager route | SoloCatalog MCP tool |
|---|---|
| `POST /api/catalog/v1/vehicles/decode` | `decode_vin` |
| `POST /api/catalog/v1/lookup` with `mode=parts` | `search_parts` |
| `POST /api/catalog/v1/lookup` with `mode=models` | `find_models` |
| `POST /api/catalog/v1/lookup` with `mode=diagrams` | `list_diagrams` |
| `POST /api/catalog/v1/lookup` with `mode=diagram` | `get_diagram_parts` |

SoloCatalog does not receive TradeSoft `groupId` values: provider identifiers are not interchangeable. Group navigation and group-part retrieval remain on TradeSoft until an explicit mapping exists.

## Fitment and fallback rules

- SoloCatalog is queried in parallel with TradeSoft for supported operations.
- TradeSoft remains the preferred primary source when it returns a single verified catalogue vehicle.
- If TradeSoft is unavailable, SoloCatalog may supply the OEM catalogue result.
- A VIN-only decode from NHTSA never proves parts fitment.
- Catalogue candidates must not be silently merged when they conflict.
- Keep provider identity, result, status and latency separate in the API response and admin analytics.

## Commercial and rate limits

SoloCatalog documents a small free daily allowance for light MCP use and an optional API key for higher use. Sustained commercial SaaS traffic requires the correct provider plan and written confirmation of commercial display, multi-tenant use, retention and image-delivery rights. Do not assume the no-key allowance is sufficient for production volume.

Official docs: https://solocatalog.com/api-docs.html
