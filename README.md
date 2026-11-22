# AI_MANAGER_DEMO v2.1.1

Static browser prototype for the AI Manager automotive-parts sales workflow.

## Published demo

https://a0934600088-glitch.github.io/AI_MANAGER_DEMO/

## Included in v2.1.1\n\n- Added a FastAPI SoloCatalog adapter under `backend/`, with server-only Bearer authentication via `SOLOCATALOG_API_KEY`, VIN decode and documented quick-lookup proxy routes.\n- Added `.env.example`, backend setup instructions, and `docs/SOLOCATALOG_ADAPTER.md`.\n- The backend panel identifies the adapter source as present but the server runtime as not deployed. GitHub Pages remains a static frontend and makes no live catalogue requests.\n\n## Included in v2.1\n\n- Customer messenger is displayed above the backend journal. The customer-only URL hides internal diagnostics.

- Backend panel now displays a live, code-style selection hierarchy: VIN → confirmed vehicle → requested node/system → diagram → selected callouts → catalog item → OE reference → analogues. It updates as the customer progresses through the demo. All catalog identifiers remain explicitly marked as local synthetic fixtures.

## Included in v1.9

- Interactive **Original Parts Diagram Selection** demo: after VIN confirmation, the messenger parses a requested parts list into supported nodes and opens the corresponding test diagrams (front suspension/control arms and front brakes).
- Each diagram has numbered, clickable SVG callouts and a matching position list. Customers can select multiple positions, clear the selection, and confirm it.
- Confirmed callouts resolve through structured local fixture data to synthetic catalog item IDs, test-only OE labels, and synthetic analogue IDs. Multiple node diagrams can open for a mixed parts list.
- Unknown requests prompt for clarification instead of inventing a diagram. Diagram selection is gated on VIN confirmation.

## Included in v1.8

- Customer messenger includes an active **Связаться с менеджером** action. Clicking it records a local handoff event, updates the chat status, and explains the intended Operator Console workflow. This is a frontend simulation only: no live operator queue, notification, or human connection is configured.

## Included in v1.7

- Three-column workspace: VIN and vehicle context; backend activity journal; customer messenger.
- No manual vehicle selector.
- Volkswagen vehicle card shown inside the chat with **Да, подтверждаю** and **Нет, проверить VIN** actions.
- Guided demo flow: VIN → customer confirmation → brake-pad request → catalog lookup → OEM mapping → analogues → customer offer.
- **Architecture requirement added: Original Parts Diagram Selection.** After vehicle confirmation, AI Manager requests the exact original-catalog diagram for the requested node, sends it into the chat, lets the customer select a numbered callout, resolves that callout through structured catalog data to an OE/OEM number, and then continues to validated analogues and pricing.
- Customer messenger: voice dictation to text (where browser speech recognition is supported), file attachments, and photo attachments with in-chat previews. The left-side context panel also retains its local attachment and microphone-recording controls.
- Responsive layout for desktop, tablet, and mobile.

## Architecture specification

See [docs/ORIGINAL_PARTS_DIAGRAM_SELECTION.md](docs/ORIGINAL_PARTS_DIAGRAM_SELECTION.md) for module boundaries, domain entities, workflow, logical API/events, reliability rules, UI requirements, and acceptance criteria.

The module is a first-class capability in the planned **Catalog & Fitment** domain, orchestrated by the conversation/application layer and integrated with Vehicle/VIN, OEM catalog adapters, cross-reference, fitment, inventory/pricing, Operator Console, and audit.

## Strict demo boundaries

GitHub Pages still serves a static frontend only. v2.1.1 adds backend source code for a FastAPI SoloCatalog adapter, but the API service has not been deployed and the frontend does not call it. The v2.0, v2.1 and v1.9 workflows remain client-side simulations, not a live backend integration.

- The Volkswagen VIN card is a fixed demonstration fixture. No VIN decoder or Parts-Catalogs request is made.
- Catalog search, OEM mapping, analogues, fitment status, and offer price are synthetic demonstration records.
- Original Parts Diagram Selection now has an interactive synthetic demo for front suspension and front brakes. The diagrams and callout mappings are hand-authored test fixtures, not original OEM illustrations or validated VW data. This static demo does not connect to ETKA or another live OEM catalog and does not validate real callout-to-OE mappings.
- The journal labels mock sources explicitly. “Demo flow passed” does not mean real compatibility was established.
- Messenger attachments and photos are displayed locally in the chat; left-panel files and recorded audio remain in the browser. No upload endpoint exists. Voice dictation uses the browser Speech Recognition API where available; recognized text is inserted into the message field for review and manual sending.
- No live inventory, supplier pricing, order creation, checkout, or payment is available.
- No API keys or credentials are embedded in the frontend. The adapter reads `SOLOCATALOG_API_KEY` only from the backend environment.\n- The adapter source is not a running service. It must be deployed separately, with secrets configured on the host, before any live catalogue request can succeed.
- Do not use the displayed part numbers, prices, or fitment statements to purchase parts.

## Run locally

Open `index.html` in a modern browser. No build step or external runtime dependency is required. Microphone recording requires browser permission and a secure context (HTTPS or localhost).

## GitHub Pages deployment

The existing GitHub Actions workflow in `.github/workflows/pages.yml` publishes the repository root on pushes to `main`. The published address is the URL above.
