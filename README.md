# AI_MANAGER_DEMO — AI Manager 2.4.35

Live test release: FastAPI serves the customer messenger and exposes the OEM catalogue integration. The separate `admin.html` page provides a protected administrator analytics console.

## Administrator console
- Open `/admin.html` on the published site.
- The page uses server-verified HTTP Basic credentials; it does not store the password in browser storage.
- Configure `ADMIN_USERNAME` and `ADMIN_PASSWORD` as Railway service variables. Do not commit real credentials or send passwords in chat.
- Legacy fallback remains available when those variables are not set: username `admin` and the existing server-side `ADMIN_API_TOKEN` as password.
- The console separates overview, client sessions, VIN activity, parts demand, CRM/store analytics, sales, AI performance and integrations.
- CRM sales metrics remain explicitly unavailable until a real CRM/e-commerce connector sends verified events. No sales figures are fabricated.

## Tenant-aware customer widget

Each shop is provisioned with its own public tenant key and HTTPS domain allowlist. Set `window.AI_MANAGER_TENANT_KEY = '...'` before the widget application script loads. Customer analytics and catalogue request telemetry are assigned to the tenant on the server. The public key is an identifier for public event attribution, not an authentication credential for private APIs. Set `TENANT_CORS_ENABLED=true` on the API service when the widget is embedded on external HTTPS shop domains.

## Catalogue integration
- **TradeSoft OEM Parts.Catalogs** — the sole OEM source configured by the application for VIN identification, vehicle catalogue lookup, original diagrams, OE numbers and callout positions. It is enabled only when TRADESOFT_ENABLED=true and a valid server-side TRADESOFT_API_TOKEN is present in Railway.
- **NHTSA vPIC and SoloCatalog** — not used as fallback providers in this release.
- **Parts-Info** — its key is not used by this backend; store assortment, prices and stock remain a separate CRM responsibility.

## Vehicle identification
1. VIN is resolved by TradeSoft /car/info.
2. For one unambiguous vehicle, the backend requests the detailed vehicle record from /catalogs/{catalogId}/cars2/{carId} with the returned criteria.
3. The original parameter payload is preserved and normalized into the stable customer vehicle-card fields.
4. Missing parameters remain missing; the application does not infer engine, power, body or fitment.

## Run and deploy
The backend serves the messenger at / and API docs at /docs. Provider and administrator credentials must be stored as Railway service variables and must never be committed to Git or placed in browser code.

## Brake-system catalogue selection (2.4.35)
- A generic brake-pad request first returns a list of brake-system choices, not an automatically opened diagram.
- TradeSoft schema labels and the selected VIN catalogue ancestry are used to classify front disc brakes, rear disc brakes, drum brakes and parking-brake shoes separately.
- Parking-brake classification has precedence over generic drum/rear labels so drum-in-hat handbrake shoes are not merged into rear service-brake shoes.
- The customer chooses one listed schema; only then does the backend request the corresponding VIN-specific parts2 payload and original diagram. OE numbers and callout positions remain sourced from TradeSoft.
- Unknown or ambiguous categories are withheld rather than guessed. No CRM stock, price or fitment is fabricated.

## Simple brake diagram cards (2.4.36)
- Brake search displays at most one customer-facing card per confirmed brake category.
- Internal TradeSoft subgroup labels and numbered schema variants are not exposed.
- Each card shows the original VIN-specific diagram thumbnail, a plain-language title and a short explanation.
- Clicking anywhere on the card opens the selected original diagram and its OE callout positions.
- When TradeSoft returns several technical subgroups for one category, the UI chooses one candidate using query relevance and available part-name detail, with deterministic provider ordering as tie-breaker.
