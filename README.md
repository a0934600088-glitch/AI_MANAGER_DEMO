# AI_MANAGER_DEMO v1.5

Static browser prototype for the AI Manager automotive-parts sales workflow.

## Published demo

https://a0934600088-glitch.github.io/AI_MANAGER_DEMO/

## Included in v1.5

- Three-column workspace: VIN and vehicle context; backend activity journal; customer messenger.
- No manual vehicle selector.
- Volkswagen vehicle card shown inside the chat with **Да, подтверждаю** and **Нет, проверить VIN** actions.
- Guided demo flow: VIN → customer confirmation → brake-pad request → catalog lookup → OEM mapping → analogues → customer offer.
- Left-side text context, file attachments, and optional microphone recording.
- Responsive layout for desktop, tablet, and mobile.

## Strict demo boundaries

This repository contains a static frontend only. The v1.5 workflow is a client-side simulation, not a live backend integration.

- The Volkswagen VIN card is a fixed demonstration fixture. No VIN decoder or Parts-Catalogs request is made.
- Catalog search, OEM mapping, analogues, fitment status, and offer price are synthetic demonstration records.
- The journal labels mock sources explicitly. “Demo flow passed” does not mean real compatibility was established.
- Selected files and recorded audio remain in the browser; no upload endpoint exists.
- No live inventory, supplier pricing, order creation, checkout, or payment is available.
- No API keys or credentials are embedded in the frontend.
- Do not use the displayed part numbers, prices, or fitment statements to purchase parts.

## Run locally

Open `index.html` in a modern browser. No build step or external runtime dependency is required. Microphone recording requires browser permission and a secure context (HTTPS or localhost).

## GitHub Pages deployment

The existing GitHub Actions workflow in `.github/workflows/pages.yml` publishes the repository root on pushes to `main`. The published address is the URL above.
