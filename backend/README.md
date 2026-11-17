# RMS backend (FastAPI)

Backend for the Restaurant Management System described in `Restaurant_Management_System_SRS.docx` (RMS-SRS-001). It serves the Next.js app in `../frontend`.

**Status:** Phase 1 (core restaurant operations) is built and tested. Phase 2 and 3 are not started yet. See [Scope and known gaps](#scope-and-known-gaps) and `../docs/TRACEABILITY.md` for each of the 332 functional requirements.

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
│   ├── core/                   config, database, security, dependencies, exceptions, realtime
│   ├── api/v1/router.py        mounts every module under /api/v1
│   ├── api/v1/endpoints/       auth, users, menu, orders, kitchen_tables, money, inventory, config, platform, reports_ws
│   ├── models/                 identity, catalog (config/menu/tables), orders, money (bills/payments/cash), inventory
│   ├── schemas/                common, identity, menu, orders
│   ├── services/               auth, menu, orders, kitchen, billing, cash, inventory, reports, pricing, platform, seed
│   ├── permissions/catalog.py
│   ├── workers/celery_app.py
│   ├── integrations/email.py
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
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Optional email delivery for password resets. Without them, emails are logged. |

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
* The seed is idempotent. `--demo` adds the demo menu, tables and ingredients that mirror the frontend screens. The administrator gets the `SYSADMIN` and `OWNER` roles; there is no default password.

## Run locally

```bash
python -m uvicorn app.main:app --reload --port 8000
```

* Health: <http://localhost:8000/api/v1/health> (also checks the database)
* Swagger UI: <http://localhost:8000/api/v1/docs>, ReDoc: `/api/v1/redoc`, spec: `/api/v1/openapi.json`

Background worker (optional locally, needs `REDIS_URL`):

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

The suite applies the real Alembic migrations, seeds once, snapshots the seeded rows, and restores the snapshot before every test. It covers authentication, authorisation, users, menu, POS, orders, kitchen, billing calculations, payments, refunds, inventory, cashier sessions, audit integrity, configuration, reports, WebSockets, idempotent replays and concurrent payments. 47 tests, about 30 seconds.

## Deployment

* Build the image from `backend/Dockerfile`. It runs as a non-root user and starts with `alembic upgrade head`, the reference seed, then uvicorn.
* Back up the database before running migrations in production (SRS §10.11).
* Set `APP_ENV=production` so the refresh cookie is `Secure`, and serve over HTTPS behind a reverse proxy.
* Use a real secret store for `JWT_SECRET_KEY`, `DB_PASSWORD` and SMTP credentials.
* Run more API workers behind Redis (`REDIS_URL`) so WebSocket events reach every worker.

## Scope and known gaps

Built (Phase 1): authentication with lockout, refresh rotation and PIN login; users and roles with approval limits; approvals; menu (categories, items, variants, effective-dated prices with overlap protection, modifiers, 86 availability, POS feed); tables (floor plan, state machine, seat-and-order, transfer, combine, out of service); orders (snapshots, modifier rules, send with per-station tickets, voids by status with approval, discounts with limits, hold, serve, auto-completion, timeline); kitchen (open tickets, item status machine, bump, recall, priority, waste outcome, ready notifications); billing (calculation engine per BR-008, single/equal/item/seat splits, USD and KHR cash with rounding and change, reference payments, voids, refunds with separation of duties, receipts and reprints); cashier sessions (floats, movements, blind close, variance approval, force close, X/Z report); basic inventory (ingredients, units with conversion rules, ledger, weighted average cost, receipts posted once, issues, adjustments and wastage with threshold approval, reversals, low-stock alerts); configuration (settings, exchange rates, tax rules, payment methods, stations, branches, devices, day-end close); in-app notifications; audit trail with hash-chain verification and export; dashboard; reports RPT-01, 02, 03, 04, 07, 11, 12, 13, 14, 17, 18, 24 with CSV export; WebSocket events; Celery outbox.

Not built yet:

* **Phase 2:** customers, reservations and waiting list, recipes and food cost (so no ingredient consumption on send yet), stock counts, batches and transfers, purchasing and suppliers, expenses, employee profiles and schedules, promotions and codes, advanced reports.
* **Phase 3:** multi-branch consolidation and transfers, online ordering, delivery platforms, payment gateway integration, external notifications.
* **Partial in Phase 1:** report export is CSV only (no PDF/Excel); no print agent or printer fallback; restaurant profile, receipt templates and numbering settings have no endpoints; dine-in "move selected items between orders" and "merge orders" are not built; top-up bills after payment has started are rejected; financial setting changes require the `settings.approve` permission rather than a separate change-request workflow.
