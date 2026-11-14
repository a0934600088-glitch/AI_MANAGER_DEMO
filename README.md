# Parts Assistant — browser demo

A static, interactive UI prototype for reviewing the vehicle identification, catalog browsing, diagram-position selection, OEM/analogue distinction, and demo-cart flow.

## Open locally
Open `index.html` in a modern browser. No build step or external dependencies are required.

## Important limitations
- All catalog items, OEM references, prices, and vehicle data are fictional demo data.
- VIN input is not sent to any provider; VIN decoding is simulated.
- Fitment is not verified.
- No live AG24/API integration exists yet.
- No real order, payment, inventory, or supplier action is performed.

## GitHub Pages
The repository includes a GitHub Actions workflow to publish this static site. GitHub Pages must be enabled for this repository with **Build and deployment → Source: GitHub Actions**. After the first successful deployment, the public site URL will be shown in the workflow deployment summary.
