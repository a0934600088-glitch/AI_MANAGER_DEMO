# AI Manager Demo

Release version is maintained in one place: `backend/VERSION`. The backend exposes that value through `GET /health`; the chat and admin interfaces display the backend-reported version instead of maintaining independent version strings.

## Current test architecture

- Customer interface: `index.html` — customer chat.
- Test diagnostics: built into the test interface and protected by administrator login.
- Admin analytics: `admin.html` — requests, conversations, messages, VIN decodes, catalogue lookups, errors and response times.
- Backend: FastAPI in `backend/app`.
- Analytics storage: PostgreSQL, configured through `DATABASE_URL`.
- Active OEM provider: TradeSoft Parts.Catalogs. Its API key is kept only in backend environment variables.

## Credentials and security

- `TRADESOFT_API_TOKEN` is an upstream TradeSoft credential. It is required when TradeSoft requires API-key authentication and must remain server-side; it is never entered in the customer chat or admin page.
- Admin access uses HTTP Basic login configured through backend environment variables `ADMIN_USERNAME` and `ADMIN_PASSWORD`. No `ADMIN_API_TOKEN` or custom admin-token header is used.
- Customer analytics events contain a generated conversation ID, not an admin credential.

## Local run

Install backend dependencies from `backend/requirements.txt`, then run the FastAPI app from the `backend` directory:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The backend image copies `backend/VERSION` into its runtime image. A release version change is made once in that file.
