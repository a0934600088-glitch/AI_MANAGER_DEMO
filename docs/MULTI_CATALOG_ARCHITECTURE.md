# Multi-catalog architecture — up to 10 providers

## Version 2.1.2 implementation status

Enabled live integrations:
1. **SoloCatalog MCP** — public Streamable HTTP endpoint at https://solocatalog.com/mcp. Official documentation states that light use needs no sign-in and has a small daily allowance. Tools: decode_vin, search_parts, find_models, list_diagrams, get_diagram_parts, lookup_part_number.
2. **NHTSA vPIC** — public VIN decoder without an API key. It is not a parts catalogue and does not return OEM diagrams.

The FastAPI backend queries SoloCatalog and NHTSA in parallel for VIN decoding. Parts/diagram requests are sent to SoloCatalog MCP only. Provider failures are returned as errors; synthetic fixtures are not used as fallback in live mode.

## Provider limits and safety
- Architectural maximum: 10 configured provider connections per tenant.
- Current enabled sources: 2 (one parts catalogue and one VIN decoder).
- RockAuto integration is not enabled: the public/unauthenticated behaviour is not established as a stable official API.
- Parts-Catalogs / Tradesoft is not enabled until its API access and credentials are confirmed.
- LLM output is not a source of truth for fitment, OEM numbers, stock, or price.
- Do not merge conflicting catalog claims. Preserve source and provider status.

## API
- GET /health
- GET /api/catalog/v1/providers
- POST /api/catalog/v1/vehicles/decode
- POST /api/catalog/v1/lookup (parts, diagrams, diagram)
- GET /docs

The app serves index.html from the same FastAPI process, so the UI and API share an origin on Railway. GitHub Pages remains a static frontend; use the Railway app URL for the live backend-connected release.
