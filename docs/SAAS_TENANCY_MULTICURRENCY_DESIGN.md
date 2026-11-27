# Multi-tenant access and multi-currency finance design

Status: approved product direction; design only. This document does not claim that authentication, tenant isolation, or financial posting is implemented.

## 1. Product decisions

- One sign-in entry point: `/login`.
- A user is assigned to a tenant (internet store) on the server. A store employee must never choose or override their tenant in a request, URL, query parameter, or header.
- Roles: platform owner (superadmin), store administrator, store manager, read-only observer.
- Store employees can access only their store's customers, conversations, VIN activity, orders, and financial information allowed by their role.
- Platform owner can inspect consolidated data and select a store scope.
- Customer identity and conversation history are tenant-scoped. The same person contacting two stores must not expose either store's history to the other.
- Finance uses immutable source-currency transactions. USD is the default reporting currency, with selectable USD, EUR, and UAH reporting views.
- A transaction retains its original amount, ISO 4217 currency, effective date, and the exact FX rate/source used for reporting. Historical postings are not silently recalculated when a rate changes.

## 2. Identity and authorization requirements

- Replace the single shared HTTP Basic administrator model with individual users and secure server-managed sessions.
- Passwords are stored only as strong password hashes. Invitations are single-use, expiring, and delivered through a configured email provider; never expose invitation secrets in logs.
- Session claims identify user ID, tenant ID, role, and session expiry. Tenant and role are reloaded/validated server-side; a client-supplied tenant ID is never authoritative.
- Every tenant-owned query and mutation must apply a server-derived tenant scope.
- Superadmin access is an explicit privileged path, audited separately. Store administrators cannot elevate themselves or switch tenant scope.
- Audit employee creation, invitation, login/session revocation, role changes, exports, financial edits, and sensitive administrative actions.
- Add negative tests proving cross-tenant reads and writes fail, including guessed IDs and forged tenant headers/body fields.

## 3. Finance ledger

Use an append-only ledger rather than calculating profit from dashboard counters.

Each financial transaction should include:
- transaction ID and tenant ID;
- type: revenue, catalogue expense, AI/API expense, infrastructure expense, payment fee, tax, refund, chargeback, or other expense;
- signed source amount (or explicit debit/credit direction), ISO currency code, and source amount in fixed-precision decimal;
- effective date, recorded timestamp, and external reference/idempotency key;
- source: verified order/payment connector, provider usage record, invoice, or manual entry;
- original evidence/reference and description, with sensitive payment data excluded;
- FX rate, rate date, rate source, and converted reporting amount;
- creator and audit metadata for manual adjustments.

Rules:
- Only captured/settled payments count as revenue. Quotes, carts, and unpaid orders do not.
- Refunds, chargebacks, taxes, and payment fees are separate ledger entries; do not conceal them by netting source values without traceability.
- Unknown costs remain unknown/unrecorded and are visibly marked as incomplete coverage, never treated as zero.
- Manual entries require an authorized role, reason, and audit trail. Corrections use reversal plus replacement, not destructive edits.
- Decimal arithmetic is required; binary floating-point is not acceptable for money.
- FX rate snapshots are immutable per posted transaction. Revaluation, if later required, is a separate accounting event.
- Profit is reported only for a period and tenant with clearly disclosed data coverage. Gross revenue, expenses by category, net operating result, and margin are separate metrics.

## 4. FX and reporting

- Default reporting currency: USD.
- Initial selectable reporting currencies: USD, EUR, UAH.
- Store each transaction in its original currency and retain the rate used to translate it into the reporting currency.
- FX source, timestamp, quote direction, and fallback policy must be explicit and testable.
- If no valid rate exists for the transaction date, mark the conversion as pending/unavailable. Do not substitute today's rate or a guessed rate.
- Changing the dashboard reporting currency changes the presentation conversion, not the source ledger. Preserve the transaction's original currency and rate snapshot.
- Reports must disclose whether they use transaction-date rates or a separately identified period-end revaluation method.

## 5. Data migration and rollout

1. Inventory all existing tables, event producers, integrations, and deployed environment variables. Back up the database before schema changes.
2. Introduce tenant, user, membership, session, invitation, audit, and ledger tables with migrations that are safe to run more than once.
3. Create one legacy tenant and migrate current `tenant_id='default'` analytics rows to it without changing event contents.
4. Keep the existing owner login as a temporary migration bridge; do not create default passwords for store employees.
5. Add authentication and server-side tenant scoping to every protected route before enabling store accounts.
6. Add ledger endpoints and admin UI only after role enforcement and database migrations are tested.
7. Connect verified payment/order events and provider usage records. Until then, show finance data coverage as incomplete and do not claim real profit.
8. Run unit, API, migration, permission, cross-tenant isolation, and regression tests for VIN, TradeSoft, catalogue diagrams, chat, localization, and existing analytics.
9. Deploy backend migrations and frontend as a coordinated release with a rollback plan. Do not enable manager access until production secrets, email delivery, session security, and backups are verified.

## 6. Release acceptance criteria

- A store manager cannot read or modify another store's customers, conversations, VIN records, orders, employees, or ledger entries.
- A store administrator cannot create platform administrators or change their own tenant.
- The platform owner can view consolidated reports and explicitly scope to a store.
- Every posted financial amount can be traced to its source and original currency.
- FX calculations are deterministic, use stored rates, and never silently rewrite historical records.
- Revenue excludes unpaid orders; refunds, fees, taxes, and expenses remain separately auditable.
- Incomplete data coverage is visible; unknown costs are not represented as zero.
- Existing VIN/OEM/chat/localization functionality passes regression tests.

## 7. Current implementation status

The current application still has a single administrator authentication mechanism and analytics hard-coded to the legacy `default` tenant. It does not yet have store users, role-based access, tenant isolation, a financial ledger, payment ingestion, or FX snapshots. This document records the approved target design only; it is not a production feature release.
