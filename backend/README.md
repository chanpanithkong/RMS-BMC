# RMS backend (FastAPI)

Backend for the Restaurant Management System described in `Restaurant_Management_System_SRS.docx` (RMS-SRS-001). It serves the Next.js app in `../frontend`.

**Status:** Phase 1 (core restaurant operations) and Phase 2 (business control) are built and tested. Phase 3 has multi-branch, delivery management, online and QR ordering, and loyalty built and tested; online payment by Bakong KHQR is built (tested against NBC's documented formats, not yet against live Bakong); customer SMS through PlasGate and phone sign-in accounts are built (tested against PlasGate's documented request format, not yet against live PlasGate). See [Scope and known gaps](#scope-and-known-gaps) and `../docs/TRACEABILITY.md` for each of the 332 functional requirements.

> Tax, service-charge, exchange-rate and approval-limit values in the seed data are the SRS's **illustrative** values. They are stored as unverified and must be confirmed against current official Cambodian sources (SRS §5.4, V-01, V-04) before use. Nothing here claims legal or tax compliance.

## Contents

1. [Technology](#technology)
2. [Architecture](#architecture)
3. [Folder structure](#folder-structure)
4. [PostgreSQL setup](#postgresql-setup)
5. [Environment variables](#environment-variables)
6. [Create the database and run migrations](#create-the-database-and-run-migrations)
7. [Run locally](#run-locally)
8. [Run with Docker](#run-with-docker)
9. [API documentation and conventions](#api-documentation-and-conventions)
10. [Authentication](#authentication)
11. [Frontend integration](#frontend-integration)
12. [Running tests](#running-tests)
13. [Deployment](#deployment)
14. [Scope and known gaps](#scope-and-known-gaps)

## Technology

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (sync), Alembic, PostgreSQL 16+ (tested on 16 and 18), psycopg 3, Argon2id password hashing, PyJWT, WebSockets, Redis (optional locally) and Celery for background work, pytest with the FastAPI test client.

## Architecture

A modular monolith (SRS §12.1) with strict layers:

| Layer | Folder | Responsibility |
|---|---|---|
| API | `app/api/v1/endpoints` | Routing, `require("permission")` dependency, request validation, idempotency, response models |
| Services | `app/services` | Business rules (SRS §8), state machines, the pure calculation engine (`pricing.py`), approvals, audit |
| Models | `app/models` | SQLAlchemy models matching the SRS §10 data dictionary |
| Schemas | `app/schemas` and endpoint modules | Pydantic request/response models; unknown fields are rejected |
| Core | `app/core` | Settings, DB engine and session, JWT/Argon2, error format, request context, real-time hub |
| Permissions | `app/permissions/catalog.py` | `resource.action` catalogue, default role grants (§4.3) and approval limits |
| Workers | `app/workers` | Celery: outbox delivery (password-reset email) and daily audit-chain verification |
| Integrations | `app/integrations` | Adapters (email today; payment and delivery providers later) |

Key behaviours:

* **One transaction per request.** The session commits when the route returns, before the response is sent. Audit rows are written in the same transaction, so a failed audit rolls the change back (BR-023).
* **Server-side money.** Prices, discounts, service charge, tax, totals, exchange conversion, change and rounding are computed only by the backend with `Decimal`. Totals sent by clients are never used. Money is returned as decimal strings.
* **Idempotency.** `Idempotency-Key` is required on order creation, send-to-kitchen, payments and refunds. A repeat with the same key returns the original response; a different body with the same key returns `409 IDEMPOTENCY_MISMATCH` (BR-030).
* **Concurrency.** Row locks on orders, bills, payments, stock balances and tables; optimistic `version` checks with `If-Match` (409 `VERSION_CONFLICT`).
* **Append-only records.** `audit_logs` (hash-chained) and `inventory_transactions` reject `UPDATE`, `DELETE` and `TRUNCATE` via database triggers. Financial records are corrected by voids, refunds and reversals, never deletion (BR-022).
* **Approvals.** A manager authenticates on the requesting device (`POST /approvals` with their PIN or password). The result is a single-use token bound to the action, record, amount and requester, valid for 2 minutes. Approver must differ from requester (BR-029).
* **Branch scope.** Every operational row has `branch_id`. Requests act in the user's default branch or the `X-Branch-Id` header; other branches' records return 404 (BR-025).

## Folder structure

```
backend/
├── app/
│   ├── main.py                 FastAPI app, CORS, correlation IDs
│   ├── core/                   config, database, security, dependencies, exceptions, realtime, ratelimit
│   ├── api/v1/router.py        mounts every module under /api/v1
│   ├── api/v1/endpoints/       auth, users, menu, orders, kitchen_tables, money, inventory, config, platform, reports_ws,
│   │                           front (customers, reservations), staff_expenses, recipes_stock, purchasing, promotions,
│   │                           branches, delivery, online (public routes under /public)
│   ├── models/                 identity, catalog (config/menu/tables), orders, money (bills/payments/cash), inventory, phase2, phase3
│   ├── schemas/                common, identity, menu, orders
│   ├── services/               auth, menu, orders, kitchen, billing, cash, inventory, reports, reports_advanced, pricing, platform, seed,
│   │                           front, recipes, purchasing, promotions, branches, delivery, online
│   ├── permissions/catalog.py
│   ├── workers/celery_app.py
│   ├── integrations/           email, payments (sandbox gateway only)
│   └── utils/                  ids (UUID v7), money, timeutil (business date)
├── alembic/                    migrations (never drop tables automatically)
├── scripts/seed.py             idempotent reference and demo data
├── tests/                      pytest suite (isolated test database)
├── Dockerfile
├── requirements.txt
├── .env.example                copy to .env
└── README.md
```

## PostgreSQL setup

Any PostgreSQL 16 or later works. On Windows, the EDB installer creates a `postgres` superuser and the `postgresql-x64-NN` service.

Create the database once (it is never created or dropped by the app):

```bash
psql -U postgres -h localhost -c "CREATE DATABASE restaurant_management_db ENCODING 'UTF8'"
```

The first migration enables the `btree_gist` and `pg_trgm` extensions, which needs a superuser or the database owner.

## Environment variables

Copy `.env.example` to `.env` (git-ignored) and fill in:

| Variable | Purpose |
|---|---|
| `DB_PASSWORD` | Your PostgreSQL password. Substituted into `DATABASE_URL`'s `${DB_PASSWORD}`. |
| `DATABASE_URL` | `postgresql+psycopg://postgres:${DB_PASSWORD}@localhost:5432/restaurant_management_db`. In Docker the host is `db`. |
| `JWT_SECRET_KEY` | Random secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The app refuses to start without one. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes |
| `FRONTEND_URL` | CORS origin(s), comma separated |
| `REDIS_URL` | Optional. Shares WebSocket events across API workers and is the Celery broker. |
| `APP_ENV` | `development` allows the refresh cookie over plain http; any other value marks it `Secure`. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Optional email delivery (password resets, purchase orders, online order confirmations). Without them, emails are logged. |
| `PAYMENT_GATEWAY`, `PAYMENT_SANDBOX_SECRET` | Online payment: `bakong` (KHQR), or `sandbox` (a test gateway, refused when `APP_ENV=production`). Leave empty to offer pay at pickup or on delivery only. |
| `SMS_PROVIDER`, `PLASGATE_*` | Customer SMS through PlasGate (`plasgate`): private key, secret and the sender ID agreed with PlasGate. Empty = messages are logged only and phone sign-in is unavailable. |
| `GRABFOOD_*` | GrabFood: the partner client ID/secret RMS issues to Grab (Grab uses them to get a token for the webhooks), the OAuth client Grab issues to RMS, and Grab's API and auth URLs. |
| `BAKONG_*` | Bakong KHQR: API URL and token (from the Bakong Open API site, valid 90 days), receiving Bakong account, merchant type (`individual` tag 29 or `merchant` tag 30 with merchant ID and acquiring bank), name (max 25), city, MCC and QR lifetime (max 10 minutes). |
| `PUBLIC_RATE_LIMIT_PER_MINUTE` | Requests per IP per minute on public online-ordering routes (checkout is capped lower). Shared across workers only with `REDIS_URL`. |

No credentials appear in source files.

## Create the database and run migrations

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
python -m scripts.seed --demo --admin-username admin --admin-password "<a password of 10+ characters>"
```

* `alembic upgrade head` only adds schema. Migrations are named `YYYYMMDD_hhmm_<slug>`; create new ones with `python -m alembic revision --autogenerate -m "..."` and review them before applying.
* The seed is idempotent. Run it again after upgrading so new permissions and role grants reach an existing database. `--demo` adds the demo menu, tables and ingredients that mirror the frontend screens. The administrator gets the `SYSADMIN` and `OWNER` roles; there is no default password.

## Run locally

```bash
python -m uvicorn app.main:app --reload --port 8000
```

* Health: <http://localhost:8000/api/v1/health> (also checks the database)
* Swagger UI: <http://localhost:8000/api/v1/docs>, ReDoc: `/api/v1/redoc`, spec: `/api/v1/openapi.json`

Background worker (optional locally, needs `REDIS_URL`). It delivers queued emails, verifies the audit chain daily, holds reserved tables and marks no-shows every 5 minutes, expires loyalty points hourly, checks pending KHQR payments with Bakong, sends queued SMS and runs background reports every 10 seconds, queues reservation reminders every 5 minutes, and refreshes the analytics summaries every 15 minutes:

```bash
celery -A app.workers.celery_app worker -B -l info
```

## Run with Docker

From the repository root:

```bash
cp .env.example .env        # set DB_PASSWORD and JWT_SECRET_KEY
docker compose up -d --build
```

Services: `db` (PostgreSQL 16, data in the `pgdata` volume), `redis`, `api` (runs migrations and the reference seed, then serves on `${API_PORT:-8000}`), and `worker` (Celery with beat). All have health checks, and containers reach each other by service name. The database port isn't published, because a local PostgreSQL usually holds 5432; uncomment `ports` in `docker-compose.yml` to reach it on 5434.

To create the first administrator in the container:

```bash
docker compose exec api python -m scripts.seed --demo --admin-password "<password>"
```

## API documentation and conventions

All routes are under `/api/v1` (SRS §13.1).

| Convention | Behaviour |
|---|---|
| Errors | `{"error": {"code", "message", "details": [{field, issue}], "correlation_id", ...}}` with 400/401/403/404/409/422/423/500 |
| Money | Decimal strings (`"12.99"`) with currency; never floats |
| Pagination | `page`, `page_size` (max 200); responses `{data, total, page, page_size}` |
| Idempotency | `Idempotency-Key` header on create order, send, payments, refunds |
| Concurrency | `If-Match: <version>` on order updates; stale → 409 `VERSION_CONFLICT` |
| Branch | `X-Branch-Id: <uuid or code>`; default is the user's first branch |
| Time | ISO 8601 with offset; `business_date` is derived by the server from the branch day-end time (default 04:00, Asia/Phnom_Penh) |

Endpoint groups: `auth`, `approvals`, `users`, `roles`/`permissions`, `menu-categories`, `menu-items` (prices, availability/86, modifier groups), `modifier-groups`, `menu/pos`, `orders` (items, send, cancel, discounts, hold, transfer, serve, timeline), `kitchen` (stations, open tickets, item status, bump, recall, priority, waste outcome), `dining-areas`, `tables` (seat, state, out of service), `table-groups`, `orders/{id}/bills`, `bills`, `payments`, `refunds`, `cashier-sessions`, `inventory` (items, units, locations, balances, transactions, documents), `settings`, `exchange-rates`, `tax-profiles`, `payment-methods`, `kitchen-stations`, `reason-codes`, `branches`, `devices`, `day-end/close`, `notifications`, `audit-logs`, `dashboard`, `reports`, and the WebSocket `/api/v1/ws`.

Phase 3 groups: `branches` (create), `menu-items/{id}/branch-assignment`, `branch-transfers` (dispatch, receive, cancel), `branch-comparison`, `delivery-zones`, `deliveries` (assign, out, delivered, failed, redeliver, mine, performance), `orders/{id}/delivery-fee`, `ready-board`, `platform-orders`, `platform-settlements` (reconciliation), `online-orders` (accept, reject), `online-ordering/pause`, `tables/{id}/qr-code`, `customers/{id}/loyalty` (and `/adjust`), `orders/{id}/loyalty-redemption`, `accounting/mapping`, `accounting/journals` (and `/xero.csv`), `platform-orders/{order_id}/accept|reject`, `credit-accounts` (statement, settlements), `bills/{id}/charge-to-account`, `analytics/summary|rebuild|menu-engineering`, `reports/{id}/jobs`, `report-jobs` (and `/download`), `platform-item-maps`, `integrations/grabfood/inbound`, the GrabFood webhooks `integrations/grabfood/oauth/token|orders|order/state|merchant/menu|menu-sync-state|pushIntegrationStatus|pushGrabMenu`, `integrations/grabfood/menu/preview|sync`, and the public routes `/public/branches/{code}/menu|delivery-zones|quote|orders`, `/public/track/{token}` (and `/payment`), `/public/branches/{code}/account/code|verify`, `/public/account` (and `/orders`, `/sign-out`), `/public/qr/{token}` (and `/orders`), `/public/payments/{provider}/callback`.

Phase 2 groups: `customers` (search, duplicates, merge, anonymise, attach to order), `reservations` (availability, seat, no-show, process-holds), `waitlist`, `departments`, `positions`, `employees` (clock in/out, activity), `shift-schedules`, `expense-categories`, `expenses` (attachments, submit, decision, pay, reverse, summary), `recipes` (versions, publish, cost, unmapped items), `inventory/counts`, `inventory/transfers`, `inventory/expiring`, `inventory/menu-wastage`, `suppliers` (history), `reorder-suggestions`, `purchase-requests`, `purchase-orders`, `goods-receipts`, `purchase-returns`, `supplier-invoices` (payments), `promotions` (codes), `orders/{id}/promotions` and `orders/{id}/promo-codes`.

Reports take `date_from`, `date_to` and, where they apply, `user_id`, `customer_id`, `supplier_id`, `station_code` and `category`. The dashboard takes `trend=day|week|month`.

## Authentication

* `POST /auth/login` returns a 30-minute access token in the body and sets the refresh token as an **HttpOnly, SameSite=Strict cookie** (`rms_refresh`, path `/api/v1/auth`). JavaScript never sees the refresh token.
* `POST /auth/refresh` rotates the refresh token. Reusing an old one revokes all of that user's sessions.
* `POST /auth/pin-login` switches user on a registered POS/KDS device (`POST /devices` returns the device token once).
* `POST /auth/logout`, `GET /auth/me` (roles, permissions, limits, branches, business date), `POST /auth/password/change`, `/password/forgot` (always the same answer), `/password/reset` (revokes all sessions).
* Lockout: 5 failures in 15 minutes locks the account for 15 minutes and alerts administrators.
* Every route declares its permission; the backend checks it on every request. Users can't change their own roles or edit a role they hold.

## Frontend integration

See `../docs/FRONTEND_INTEGRATION.md`. In short: the frontend has typed bindings in `frontend/lib/api/schema.d.ts` (generated from the OpenAPI spec) and a fetch client in `frontend/lib/api/client.ts`. The screens still use the demo store and are switched to the API one module at a time.

## Running tests

Tests never touch your development database. They need a PostgreSQL database whose name ends in `_test` (the suite refuses to run otherwise), set in `backend/.env.test`:

```
TEST_DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5433/restaurant_management_test
```

A disposable one in Docker:

```bash
docker run -d --name rms-test-postgres -e POSTGRES_PASSWORD=<password> -e POSTGRES_DB=restaurant_management_test -p 5433:5432 postgres:16-alpine
```

Run:

```bash
python -m pytest
```

The suite applies the real Alembic migrations, seeds once, snapshots the seeded rows, and restores the snapshot before every test. It covers authentication, authorisation, users, menu, POS, orders, kitchen, billing calculations, payments, refunds, inventory, cashier sessions, audit integrity, configuration, reports, WebSockets, idempotent replays and concurrent payments, plus the Phase 2 acceptance tests (customers, reservations, expenses, cashier expected cash, recipes and food cost, stock counts, transfers, purchasing, promotions including concurrent code redemption, and the advanced reports) and Phase 3 (multi-branch, delivery, platform settlements, online and QR ordering, the sandbox payment callback, rate limiting, loyalty, Bakong KHQR, SMS and phone sign-in, accounting export, GrabFood import and menu sync, customer credit accounts, analytics). 118 tests, a few minutes.

## Deployment

* Build the image from `backend/Dockerfile`. It runs as a non-root user and starts with `alembic upgrade head`, the reference seed, then uvicorn.
* Back up the database before running migrations in production (SRS §10.11).
* Set `APP_ENV=production` so the refresh cookie is `Secure`, and serve over HTTPS behind a reverse proxy.
* Use a real secret store for `JWT_SECRET_KEY`, `DB_PASSWORD` and SMTP credentials.
* Run more API workers behind Redis (`REDIS_URL`) so WebSocket events reach every worker.

## Scope and known gaps

Built (Phase 1): authentication with lockout, refresh rotation and PIN login; users and roles with approval limits; approvals; menu (categories, items, variants, effective-dated prices with overlap protection, modifiers, 86 availability, POS feed); tables (floor plan, state machine, seat-and-order, transfer, combine, out of service); orders (snapshots, modifier rules, send with per-station tickets, voids by status with approval, discounts with limits, hold, serve, auto-completion, timeline); kitchen (open tickets, item status machine, bump, recall, priority, waste outcome, ready notifications); billing (calculation engine per BR-008, single/equal/item/seat splits, USD and KHR cash with rounding and change, reference payments, voids, refunds with separation of duties, receipts and reprints); cashier sessions (floats, movements, blind close, variance approval, force close, X/Z report); basic inventory (ingredients, units with conversion rules, ledger, weighted average cost, receipts posted once, issues, adjustments and wastage with threshold approval, reversals, low-stock alerts); configuration (settings, exchange rates, tax rules, payment methods, stations, branches, devices, day-end close); in-app notifications; audit trail with hash-chain verification and export; dashboard; reports RPT-01, 02, 03, 04, 07, 11, 12, 13, 14, 17, 18, 24 with CSV export; WebSocket events; Celery outbox.

Built (Phase 2):

* **Customers:** profiles with phone normalised to +855, duplicate detection, merge, anonymisation that keeps orders, contact masking, classification, and preferences and allergy notes shown when a customer is attached to an order.
* **Reservations and waiting list:** availability with the next free slot, overlaps blocked by a database constraint, hold and no-show processing, seating in one action, a warning when a walk-in takes a table reserved soon, and a waiting list with quoted wait.
* **Staff and expenses:** departments, positions, employees linked to users, shift schedules with overlap checks, clock in/out and activity history. Expense categories with attachment rules, approval by someone else above the submitter's limit, payment (including cash paid out from the drawer), reversal with approval, and summaries.
* **Recipes and food cost:** effective-dated versions, unit compatibility, prep and cook loss, consumption posted once when items are sent and reversed when they're cancelled before preparation, cost per portion, food cost % and margin, and unmapped items.
* **Advanced inventory:** blind stock counts with variance approval, transfers between locations at weighted average cost, batches with expiry warnings, and menu-item wastage converted through the recipe.
* **Purchasing:** suppliers, requests (manual and from low stock), POs with value-band approval and no self-approval, approved POs sent back for approval when changed, a plain-text PO email sent through the outbox, goods receipts posted once with quantity and price tolerance approval, returns, invoice matching, supplier payments, balances and ageing.
* **Promotions:** percent, amount, fixed price and buy-X-get-Y for the order, an item or a category. Validity by date, day, time window, branch, order type and customer segment. Priority and combination rules, with reasons for promotions that don't apply. Case-insensitive codes with total and per-customer limits, counted under a row lock.
* **Reports and dashboard:** RPT-05, 08, 09, 10, 15, 16, 19, 20, 21, 22, 23, 25 and 26; dashboard trends, theoretical food cost, approved expenses and an indicative operating result.

Built (Phase 3 so far):

* **Multi-branch:** create branches (with default stations and storage locations), branch menu assignment and prices, suppliers shared or restricted by branch, inter-branch transfers (dispatch at the source's cost, in transit, receive with variance and reason, cancel back to source), branch comparison and RPT-06 for users with `report.cross_branch`, limited to their own branches.
* **Delivery:** zones with fee, free-delivery threshold, minimum order and the fee's own tax profile; delivery orders with address, landmark and map point; fee override with permission and reason; riders (new Delivery Rider role) with their own view; Assigned, Out for delivery, Delivered (recipient name), Failed and re-delivery; takeaway ready board; delivery performance; scheduled pickup/delivery time.
* **Delivery platforms:** platform orders with a reference unique per platform and commission (rate or amount), paid with the `PLATFORM` method; commission is a cost, never a discount; settlement statements reconciled line by line with every difference listed.
* **Online and QR ordering:** public menu per branch, quote, checkout with full server-side validation (availability, channel, prices, modifiers, quantity, opening hours, lead time, minimum order, zone, promotion codes) and `PRICE_CHANGED` when totals moved; idempotent submission; signed, expiring tracking links; confirmation email; staff accept or reject; pause per branch; table QR codes that create or add to the table's order, with staff confirmation by default; rate limits on public routes; online payment by Bakong KHQR (dynamic QR per NBC's KHQR guideline, confirmed by polling `check_transaction_by_md5`; the receiving account, currency and amount must all match before a `KHQR` payment is recorded; codes expire after at most 10 minutes and can be reissued) or, for development, a sandbox with a signed callback.
* **Loyalty (owner's rules for D-14):** 1 point per whole 1.00 USD of net sales (after discounts; no tax, service charge or delivery fee), earned once when an order with a customer completes, on every channel including orders with promotions; 100 points = 1.00 USD off as the order-level discount, never more than the order; each lot expires 12 months after it was earned and the oldest points are used first. Removing a redemption or cancelling the order returns the points, refunds take back points in proportion, managers can adjust with a reason, and online orders from a known phone number earn too. Off until a manager sets `loyalty.enabled`.
* **Customer SMS (PlasGate):** online order updates (received with the tracking link, accepted, rejected, ready for pickup, out for delivery), reservation confirmations (again when the time changes), one reminder before the booking (120 minutes by default) and waiting-list "table ready". Messages are queued in the same transaction as the change, de-duplicated, and sent by the worker with up to 5 attempts and exponential back-off (30 s to 4 min). Off until a manager sets `sms.enabled`.
* **Online customer accounts:** sign in with a 6-digit code sent by SMS (10 minutes, 5 tries, 3 codes per 15 minutes per phone, only a hash stored). The first sign-in creates the customer record with name and phone only. Signed-in customers see their own orders and loyalty points; their online orders are linked to them.
* **Accounting export (Xero):** one balanced manual journal per branch and business day (`GET /accounting/journals` to review, `/accounting/journals/xero.csv` to import into Xero), covering sales by category, discounts, service charge, tax, delivery fees, payments by method, KHR rounding, refunds, cash over/short, platform commissions, stock movements at weighted average cost, expenses and supplier invoices and payments. Xero manual journals can't post to bank, receivable or payable accounts, so money goes through clearing accounts the accountant settles in Xero. Needs `accounting.export` (Owner, Accountant).
* **GrabFood import:** Grab sends orders to RMS (Submit order webhook) and state changes (Push order state webhook), authenticated with a token RMS issues through its partner OAuth endpoint. Orders arrive in RMS as platform orders priced from the RMS menu; Grab's own total (KHR, minor units) is stored and a difference is flagged. Staff accept or reject each order (owner's choice): accepting records the PLATFORM payment, sends it to the kitchen and tells Grab (`/partner/v1/order/prepare`); when the kitchen finishes, RMS marks it ready at Grab; COLLECTED/DELIVERED completes it; a Grab cancellation alerts the manager. Every webhook is logged with what RMS did. Menu IDs: RMS variant/modifier IDs, or codes mapped in `platform-item-maps`; an order with unknown IDs is logged for manual entry.
* **Grab menu sync:** RMS answers Grab's Get menu webhook with the branch's menu in Grab's selling-time structure: categories, one Grab item per RMS variant, modifier groups and modifiers, Khmer names with English translations, the branch opening hours as the selling time, and tax-inclusive prices converted to KHR minor units at today's rate in 100-riel steps. Items in the `menu_channel` (default Online) are included; items not sold at the branch are left out and 86'd items are sent as unavailable. `POST /integrations/grabfood/menu/sync` asks Grab to pull the full menu (Grab recommends once a day, off-peak); marking an item sold out or back sends an immediate menu record update. Menu sync failures and integration status changes alert managers. The first Get menu during activation stores the Grab merchant ID for the branch.
* **Customer credit accounts (owner's decisions for D-07):** the Owner, GM or Accountant opens an account for a customer or company with a credit limit and terms (30 days by default). Staff charge an unpaid bill to the account (`POST /bills/{id}/charge-to-account`); it is recorded as an `ON_ACCOUNT` payment so the bill is settled and the sale counted, and the account ledger gets a charge due after the terms. A charge over the limit, or any charge while the account has an overdue amount, needs a manager's approval on the device (`credit_override`). Settlements pay off the oldest charges first; cash settlements go into the cashier's session. Refunds of on-account payments credit the account. Statements show opening and closing balances and ageing by due date. Off until a manager sets `credit.enabled`.
* **Analytics (owner's choice for "advanced analytics"):** daily summary tables per branch (sales by item, category, hour, payment method and employee; ingredient consumption) as in SRS §12, rebuilt at day-end close and refreshed every 15 minutes for today and yesterday, with `POST /analytics/rebuild` for history; `GET /analytics/summary` reads them. `GET /analytics/menu-engineering` classifies items as Star, Plowhorse, Puzzle or Dog (Kasavana-Smith: 70 % popularity rule, quantity-weighted average contribution margin); items without recipe cost are listed as Unclassified. Long reports run in the background (`POST /reports/{id}/jobs`) with the requester's current permissions and give a CSV that only the requester can download for 24 hours (audited); expired files are deleted.

Assumptions to confirm:

* Phase 2 approval limits are placeholders, not SRS values: purchase orders (branch manager 500, GM 5,000) and expenses (supervisor 50, branch manager 300, GM 2,000). So are the receipt and price tolerances (5%) and the kitchen late threshold (`late_ticket_minutes`, 15). Change them in role limits and settings.
* Recipe versions are Published with an `effective_from` time rather than carrying a single Active flag. The version in effect is the latest published one whose time has passed.
* Per-order net sales in RPT-05, 08, 09 and 23 is the discounted subtotal of completed orders. RPT-01 and the dashboard also deduct refunds.
* Phase 3 placeholders: online ordering lead time 20 minutes, 20 items per line, tracking links valid 24 hours, public limit 60 requests per minute. Platform commission rates are calculated on the order total including tax. Branch opening hours are read as `HH:MM-HH:MM`.

Not built yet:

* **PlasGate go-live checks:** PlasGate publishes the request format only, so any 2xx reply counts as accepted and delivery reports aren't processed. Messages are in English; confirm Khmer (Unicode) support, message length and sender ID registration with PlasGate before switching on, and send a few test messages.
* **Xero set-up:** the account codes start as labelled placeholders (`GET /accounting/mapping`). The accountant sets the real codes, the Xero tax rate name for these lines, the date format and the tracking category in `PUT /settings/accounting`, then sets `mapping_confirmed`; the CSV is refused until then. Create the clearing accounts in Xero as ordinary (non-bank) accounts. Check one imported day against RPT-01 before relying on it. Inclusive taxes stay inside sales; KHR cash differences use the current exchange rate; an expense reversed after export needs a manual journal in Xero.
* **GrabFood go-live checks:** built from Grab's public Partner API v1.1.3 docs and SDK; not yet run against Grab's staging project. Apply as a POS partner, set the partner endpoints in the developer portal (`https://<host>/api/v1/integrations/grabfood/...`), confirm the OAuth URL, set the branch's Grab merchant ID and commission rate in `PUT /settings/grabfood`, configure the store for manual acceptance (Grab cancels orders not answered within 5 minutes, so the worker must be running), and work through Grab's staging test cases. Check the menu preview (`GET /integrations/grabfood/menu/preview`) in Grab's Menu Simulator before the first sync; prices follow the KHR rate on the day of each full sync, and price changes reach Grab with the next full sync. Selling-time windows per category, service-based pricing, photos beyond one and Meal for One tags aren't used. Grab-side edits after acceptance and Grab cancellations are flagged for a manager rather than changed automatically.
* **Bakong go-live checks:** the KHQR adapter follows NBC's published documents (KHQR guideline v1.4, QR Pay Integration v1.0.3, Open API v1.0.1) and its CRC matches NBC's sample, but it hasn't run against Bakong SIT or production yet. Before going live: register for a token, set the merchant details your bank gives you (including the MCC), pay a few test orders from a banking app on SIT, and plan for the 90-day token renewal. Bakong blocks API requests from outside Cambodia, so the server must call from a Cambodian network.
* **Phase 3, waiting on decisions:** other delivery platforms, forecasting and period-over-period comparisons.
* **Partial or missing in Phases 1 and 2:**
  * Report export is CSV only (no PDF or Excel), and there is no printable or PDF purchase order.
  * There is no print agent or printer fallback.
  * The restaurant profile, receipt templates and numbering settings have no endpoints.
  * Dine-in "move selected items between orders" and "merge orders" aren't built.
  * Top-up bills after payment has started are rejected.
  * Financial setting changes need `settings.approve` rather than a separate change-request workflow.
  * Sub-recipes and batch production, recipe photos, first-expiry-first-out issuing, recurring expenses, combo-price promotions and staff-meal or comp discount types aren't built.
  * A change to a promotion reaches an open order the next time that order changes.
  * Customer search speed at 50,000 records hasn't been measured.
  * Riders can't attach a delivery photo yet; a failure is reported as unassigned once the delivery is sent out again.
  * Public routes have rate limits and idempotency but no CAPTCHA or bot challenge.
  * The existing reports still query the transactional tables; only the analytics endpoints read the summaries. Report files are stored on the API server's disk (`backend/uploads/reports`), not object storage.
  * A bill charged to a credit account shows as Paid (method `ON_ACCOUNT`) rather than the SRS's separate `Credit` bill status, so existing payment, completion and sales logic applies unchanged. Accounts are restaurant-wide, settled in USD; customer statements are data only (no printed or emailed statement yet).
  * A loyalty redemption is the order-level discount, so it can't be combined with another order-level discount or promotion (BR-037). Points aren't earned for a customer attached after the order completed, and a refund after the points were spent can leave a negative balance.
