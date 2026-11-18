# RMS Backend — Implementation Plan

Source of truth: `Restaurant_Management_System_SRS.docx` (RMS-SRS-001 v1.0, draft).
Section numbers below refer to that document.

## 1. Analysis of the existing project

| Item | Finding | Consequence for the backend |
|---|---|---|
| Frontend | Next.js 16.4 App Router, React 19, TypeScript, Tailwind 4, shadcn/ui (base-ui). Route groups `(back-office)`, `(fullscreen)` (POS, KDS, expo, ready board), `(auth)`, plus public `/online` and `/rider`. | API must serve every screen; POS/KDS need WebSocket updates. |
| Frontend data | All screens read an in-memory demo store (`lib/rms/store.ts`, `lib/rms/seed.ts`, `lib/rms/back-office.ts`). There are **no existing API calls**. | API contracts are defined here from SRS §13 and documented; the frontend is switched over module by module using generated types. |
| Frontend money | Demo store uses JS numbers. | API returns money as decimal strings (`"12.99"`) per §13.1; the client parses for display only. |
| Status vocabulary | Frontend uses labels such as `DINE_IN`, `In Preparation`. | Backend uses the SRS data-dictionary codes (`DineIn`, `InPreparation`, `AwaitingPayment`…). The integration guide lists the mapping. |
| Local services | PostgreSQL 18 running on `localhost:5432` (password-protected). Docker 29 available. Redis not installed locally. Python 3.12 available. | Dev DB = your local PostgreSQL via `.env`. Tests = separate container on port 5433. Redis via Docker Compose (optional locally). |

## 2. Architecture (SRS §12)

Modular monolith, one FastAPI application, layered:

```
api/v1/endpoints/*   HTTP only: auth + permission dependency, validation, idempotency, mapping
services/*           business rules (§8), state machines, calculations, approvals, audit, events
repositories/*       SQLAlchemy queries with branch scoping and row locks
models/*             SQLAlchemy 2.x declarative models = SRS §10 data dictionary
schemas/*            Pydantic v2 request/response models (money as Decimal → string)
core/*               config, database/session, security (JWT, Argon2id), errors, dependencies
permissions/*        permission catalogue, default role grants (§4.3), scope checks
workers/*            Celery app: outbox delivery, scheduled checks
integrations/*       adapters (email, payment provider, delivery platform) behind interfaces
utils/*              uuid7, money/rounding, business date, hashing
```

Key decisions:

* **Sync SQLAlchemy + sync FastAPI routes** (threadpool). Simpler transactions and row locks; adequate for SRS A-03 load. WebSocket endpoints are async.
* **One DB transaction per request** (unit of work). Audit rows are inserted in the same transaction (BR-023); if audit fails the business change rolls back.
* **Calculation engine** (`services/pricing.py`) is a pure Decimal function used by orders, bills and tests (§12.3).
* **Real-time**: in-process WebSocket hub; when `REDIS_URL` is set, events are published on Redis pub/sub so several API workers share them (§12.7). Events are emitted only after commit.
* **Idempotency** table `(scope, key)` storing request hash and response (BR-030).
* **Approvals**: approver authenticates on the same device (password or PIN) → single-use approval token bound to action, target, amount and requester, expiring in 2 minutes (BR-009, BR-029, §13.4).

## 3. Database design approach (SRS §10)

* PostgreSQL only. UUID v7 primary keys (generated in Python). `snake_case` plural tables.
* Money `NUMERIC(18,4)` + `CHAR(3)` currency; rates `NUMERIC(18,8)`; quantities `NUMERIC(18,4)`. No floats anywhere.
* `TIMESTAMPTZ` in UTC; `business_date DATE` derived by the server from branch `timezone` (default `Asia/Phnom_Penh`) and `day_end_time` (default 04:00) (BR-047).
* Standard columns: `created_at`, `updated_at`, `created_by`, `updated_by`, `version` (optimistic locking) on mutable tables.
* Status columns are `TEXT` with `CHECK` constraints.
* `branch_id NOT NULL` on every operational table (A-01).
* No physical deletion of financial, order, inventory or audit rows (BR-022). `audit_logs` and `inventory_transactions` are protected by triggers that reject `UPDATE`/`DELETE`.
* Structural rules in the database: partial unique indexes (BR-002, BR-039, BR-041), `EXCLUDE USING gist` for price overlap (BR-048) and reservation overlap (BR-028), unique source keys for idempotent stock postings (BR-014, BR-018).
* All schema changes through Alembic. Migrations never drop existing tables.

## 4. Phases and order of work (SRS §19)

| Step | Scope | Exit check |
|---|---|---|
| 1–2 | Inspect project and SRS, this plan, traceability matrix | Plan reviewed |
| 3–4 | Backend skeleton, config, DB engine/pool, session management, error format (§13.1) | App starts, health check hits DB |
| 5 | Phase 1 models + initial Alembic migration + idempotent seed (permissions, roles, units, reasons, payment methods, demo menu) | `alembic upgrade head` on empty DB |
| 6 | Auth (login, lockout, refresh rotation, logout, PIN login, password change/reset, me) + RBAC + branch scope | Auth and permission tests |
| 7 | Phase 1 modules: CFG, MENU, TBL, ORD/POS, KDS, BILL, STAFF cashier sessions, basic INV, PROMO manual discounts, NOTIF in-app, AUD, DASH, RPT 01/02/03/04/07/11/12/13/14/17/18/24, DLV takeaway | Acceptance tests from §16 for these modules |
| 8 | Frontend integration: OpenAPI → TypeScript types, typed client, integration guide; switch login first | Types generated, guide written |
| 9 | Phase 2: CUST, RSV, RCP, advanced INV, PUR, EXP, STAFF schedules, promotions/codes, advanced RPT | Module tests (done; see `TRACEABILITY.md`) |
| 10 | Phase 3: BRN, ONL, delivery platforms, payment gateway adapters, external notifications | Module tests (BRN, DLV, ONL done with a sandbox gateway; loyalty, real gateway, SMS wait for D-13, D-14, V-06) |
| 11–12 | Test completion, Docker Compose, README | Full suite green, compose up healthy |

## 5. Assumptions and open decisions carried from the SRS

These are **configurable** and seeded with the SRS's *illustrative* values only. None is a verified legal or tax value.

| Item | Default seeded | SRS reference |
|---|---|---|
| Service charge 5 % on discounted subtotal, dine-in only | illustrative, `verified=false` | V-01, D-03, BR-010 |
| Tax 10 % on subtotal + service charge | illustrative, `verified=false` | V-01, BR-010 |
| Exchange rate 4,100 KHR/USD, KHR cash rounding 100 riel | illustrative | V-04, D-06, BR-024 |
| Discount limits by role (Cashier 10 %, Supervisor 20 %, Branch Manager 30 %, GM 50 %) | illustrative | D-04, D-05 |
| Consumption posted on send to kitchen; negative stock allowed for sales only | default per A-15 | D-08, BR-040 |
| Weighted average cost | default per A-16 | D-09 |
| Partial payments allowed | default on | D-11 |
| Cash variance tolerance 1.00 USD / 4,000 KHR | illustrative | BR-013 |
| Lockout 5 failures / 15 min → 15 min | proposed | §14.2 |
| Purchase-order approval bands (Branch Manager 500, GM 5,000) and expense limits (Supervisor 50, Branch Manager 300, GM 2,000) | placeholder, not from the SRS | BR-017, BR-020 |
| Goods-receipt quantity and price tolerance 5 %, invoice tolerance 1.00 | placeholder | BR-042, FR-PUR-010 |
| Reservation duration 90 min, buffer 15, hold 60, grace 15 | placeholder | FR-RSV-005/006 |
| Target food cost 35 %, kitchen late threshold 15 min | placeholder | FR-RCP-008, FR-RPT-014 |

## 6. Frontend integration plan

1. Backend serves `/api/v1/openapi.json`; `npm run api:types` generates `lib/api/schema.d.ts` with `openapi-typescript`.
2. A small typed fetch client (`lib/api/client.ts`) adds the bearer token, `Idempotency-Key`, `If-Match`, refresh-on-401 and the problem-details error type.
3. Screens move from the demo store to the API one module at a time, starting with login, then POS/orders/KDS (highest value), then back office. The demo store stays until each screen is switched, so nothing breaks in between.
4. KDS, POS, floor plan and notifications subscribe to `ws://…/api/v1/ws?token=…` topics.

See `docs/FRONTEND_INTEGRATION.md` for contracts and examples.
