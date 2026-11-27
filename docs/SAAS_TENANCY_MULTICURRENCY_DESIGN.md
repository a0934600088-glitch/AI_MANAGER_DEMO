# Multi-tenant access and multi-currency finance design

Status: approved target design only. This document does not claim that the described features are implemented.

## Product decisions

- One sign-in entry point: `/login`.
- Users are assigned to a store (tenant) on the server. Store employees cannot select or override tenant scope in a URL, request body, or header.
- Roles: platform owner (superadmin), store administrator, store manager, read-only observer.
- Store employees can access only their store's customers, conversations, VIN activity, orders, and permitted financial information.
- Customer identity and conversation history are tenant-scoped. A person contacting two stores must not expose either store's history to the other.
- Finance uses an auditable ledger of source-currency transactions. USD is the default reporting currency; USD, EUR, and UAH are selectable reporting views.
- Every posted transaction retains its source amount, ISO 4217 currency, effective date, and immutable FX-rate snapshot/source. Historical transactions are not silently recalculated.

## Identity, sessions, and authorization

- Replace shared HTTP Basic credentials for normal users with individual accounts and secure server-managed sessions.
- Store only strong password hashes. Invitations are single-use, expire, and are delivered through a configured email provider. Never log invitation secrets.
- The server derives user ID, tenant ID, and role from the authenticated session and validates membership on each protected request.
- Every tenant-owned read and write must use server-derived tenant scope. A client-supplied tenant ID is never authoritative.
- Superadmin cross-tenant access is a separate, explicitly audited privilege path.
- Audit employee creation, invitation, login/session revocation, role changes, exports, financial postings, reversals, and manual adjustments.
- Add negative tests for cross-tenant access, guessed object IDs, forged headers, and forged request-body tenant IDs.

## Finance ledger

Each ledger entry must retain:
- transaction ID and tenant ID;
- category: revenue, OEM/catalogue expense, AI/API expense, infrastructure, payment fee, tax, refund, chargeback, or other expense;
- exact source amount in fixed-precision decimal and ISO 4217 currency;
- effective date, recorded timestamp, external reference/idempotency key;
- source: verified payment/order connector, provider usage record, invoice, or authorized manual entry;
- description and evidence reference, excluding sensitive payment data;
- FX rate, rate date, rate source, quote direction, and converted reporting amount;
- creator and audit metadata for manual entries.

Accounting rules:
- Only captured/settled payments count as revenue. Quotes, carts, and unpaid orders do not.
- Refunds, chargebacks, taxes, and payment fees remain separately traceable.
- Unknown costs remain unrecorded and visibly marked as incomplete coverage; they are never treated as zero.
- Manual entries require permission, reason, and audit trail. Corrections use reversal plus replacement, not destructive edits.
- Use decimal arithmetic for money, never binary floating-point.
- FX snapshots are immutable for posted transactions. Any later revaluation is a separate, explicitly identified accounting event.
- Reports distinguish gross revenue, expenses by category, net operating result, and margin, and disclose data coverage.

## FX and reporting

- Default reporting currency: USD.
- Initial selectable currencies: USD, EUR, UAH.
- Keep the original transaction currency and amount permanently.
- If a valid rate for the transaction date is unavailable, mark conversion as pending/unavailable. Never substitute today's rate or a guessed rate.
- Switching the report currency changes presentation only; it does not rewrite source ledger entries.
- Reports must identify whether they use transaction-date FX or a separately defined period-end revaluation method.

## Migration and rollout

1. Inventory tables, event producers, integrations, and production environment variables. Back up the database before migration.
2. Add tenant, user, membership, session, invitation, audit, and ledger tables through repeatable migrations.
3. Create one legacy tenant and migrate existing `tenant_id='default'` analytics rows without changing event contents.
4. Keep the current owner login only as a temporary migration bridge. Never create default employee passwords.
5. Enforce authentication and tenant scoping on every protected route before enabling store accounts.
6. Add finance endpoints and admin UI only after role enforcement and database migrations are tested.
7. Connect verified payment/order events and actual provider usage. Until connected, finance coverage must be marked incomplete and no real profit claim may be made.
8. Run unit, API, migration, permission, tenant-isolation, and regression tests for VIN, TradeSoft, diagrams, chat, localization, and analytics.
9. Deploy backend migrations and frontend as a coordinated release with rollback. Do not enable manager accounts until secrets, email delivery, session security, and backups are verified.

## Release acceptance criteria

- Store managers cannot read or modify another store's customers, conversations, VIN records, orders, employees, or ledger entries.
- Store administrators cannot create platform administrators or change their tenant.
- Platform owner can view consolidated reports and explicitly scope to one store.
- Every financial amount is traceable to its source and original currency.
- FX calculations are deterministic and use stored rates; historical entries are not silently rewritten.
- Unpaid orders are excluded from revenue; refunds, fees, taxes, and expenses remain separately auditable.
- Incomplete coverage is visible; unknown costs are not displayed as zero.
- Existing VIN/OEM/chat/localization functionality passes regression tests.

## Current implementation status

The current application still uses a single administrator authentication mechanism and analytics hard-coded to the legacy `default` tenant. It does not yet have store users, role-based access, tenant isolation, a financial ledger, payment ingestion, or FX snapshots. This document records the approved target design only; it is not a production feature release.
