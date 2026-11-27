# AI_MANAGER_DEMO — AI Manager 2.4.20

Live test release: FastAPI serves the customer messenger and exposes the OEM catalogue integration.

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
The backend serves the messenger at / and API docs at /docs. Provider credentials must be stored as Railway service variables and must never be committed to Git or placed in browser code.