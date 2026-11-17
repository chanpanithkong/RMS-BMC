# Frontend integration guide

How the Next.js app in `frontend/` talks to the FastAPI backend in `backend/`.

## Base URL and environment

| Variable (frontend) | Example | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend origin. The client appends `/api/v1`. |

The backend allows the origins listed in its `FRONTEND_URL` setting (CORS with credentials), so `http://localhost:3000` works out of the box.

## Files in the frontend

* `lib/api/schema.d.ts`: TypeScript types generated from the OpenAPI spec. Regenerate after backend changes:
  ```bash
  npx openapi-typescript@7.4.4 http://localhost:8000/api/v1/openapi.json -o lib/api/schema.d.ts
  ```
* `lib/api/client.ts`: a small fetch wrapper: `api(method, path, { body, query, idempotent, ifMatch })`, `login`, `logout`, `connectRealtime`, `ApiError`.

The screens still read the demo store in `lib/rms/`. Switch them one module at a time; nothing else changes until you do.

## Authentication and tokens

1. `login(username, password)` calls `POST /api/v1/auth/login`. The access token comes back in the body and is kept in memory by the client. The refresh token is set as an HttpOnly cookie that JavaScript can't read.
2. Every request sends `Authorization: Bearer <access token>`.
3. On a 401 the client calls `POST /auth/refresh` once (the cookie goes automatically because requests use `credentials: "include"`) and retries.
4. `GET /auth/me` returns the user's roles, permissions, approval limits, branches, current branch and business date. Use `permissions` to hide what the user can't do. The backend still enforces everything.
5. Shared terminals: register the device (`POST /devices`, keep the returned `device_token` on the device), then `POST /auth/pin-login`.

## Requests

```ts
import { api } from "@/lib/api/client"

// POS feed: categories, items, prices, modifiers, 86 status
const menu = await api("GET", "/menu/pos")

// Create an order with items (Idempotency-Key generated for you)
const order = await api("POST", "/orders", {
  idempotent: true,
  body: {
    order_type: "DineIn",
    table_id,
    guest_count: 2,
    items: [{ variant_id, quantity: "2", modifiers: [{ modifier_id }], note: "no chilli" }],
  },
})

// Send to kitchen; reuse the same key if you retry after a timeout
const key = crypto.randomUUID()
await api("POST", `/orders/${order.id}/send`, { idempotent: key, ifMatch: order.version })

// Bill and pay 20,000 KHR cash with change in KHR
const [bill] = await api("POST", `/orders/${order.id}/bills`, { body: { mode: "single" } })
const pay = await api("POST", "/payments", {
  idempotent: true,
  body: { bill_id: bill.id, method: "CASH_KHR", currency: "KHR", amount_tendered: "20000", change_currency: "KHR" },
})
```

Example payment response (values from the SRS worked example):

```json
{
  "payment_id": "0193...",
  "status": "Confirmed",
  "currency": "KHR",
  "amount_tendered": "20000",
  "amount_applied": "12300",
  "rate": "4100",
  "amount_base": "3.00",
  "rounding_base": "0.01",
  "rounding": { "currency": "KHR", "amount": "41" },
  "change": { "currency": "KHR", "amount": "7700" },
  "bill": { "bill_no": "B-RVS-000001", "total": "12.99", "paid": "12.99", "balance": "0", "status": "Paid" },
  "receipt_no": "R-RVS-000001"
}
```

Money is always a decimal string. Show it as-is (or format with `Intl.NumberFormat`), and never compute totals in the browser.

## Errors

Every error has the same shape:

```json
{ "error": { "code": "APPROVAL_REQUIRED", "message": "This needs approval from a manager.", "details": [], "action": "discount", "amount": "20.00", "correlation_id": "…" } }
```

`client.ts` throws `ApiError` with `status`, `code` and `body`. Common codes:

| Code | Meaning in the UI |
|---|---|
| `VALIDATION_ERROR` (422) | Highlight `details[].field` |
| `MODIFIER_REQUIRED`, `ITEM_UNAVAILABLE` | Keep the modifier dialog open / grey the item |
| `APPROVAL_REQUIRED` (403) | Open the approval dialog, call `POST /approvals` with the manager's PIN, retry with `approval_id` |
| `VERSION_CONFLICT` (409) | Reload the order and try again |
| `IDEMPOTENCY_MISMATCH` (409) | A key was reused for a different request; generate a new one |
| `CASHIER_SESSION_REQUIRED`, `EXCHANGE_RATE_MISSING`, `BUSINESS_DAY_CLOSED` | Show the message; link to Shifts or Settings |
| `PERMISSION_DENIED` (403) | Hide or disable the control |
| `POSSIBLE_DUPLICATE` (409) | Show `existing` customers and offer to use one, or create anyway with `?force=true` |
| `TABLE_TIME_CONFLICT` (409) | Offer `next_available` or one of `alternative_table_ids` |
| `TABLE_RESERVED_SOON` (409) | Warn, then retry seating with `override_reservation: true` |
| `SELF_APPROVAL`, `APPROVER_LIMIT_EXCEEDED` (403) | Someone else, or a role with a higher limit, must approve |
| `PROMO_CODE_INVALID`, `PROMO_NOT_APPLICABLE`, `PROMO_LIMIT_REACHED`, `PROMO_ALREADY_APPLIED` | Show the message under the code field |
| `UNIT_INCOMPATIBLE` (422) | The recipe line's unit doesn't match the ingredient's dimension |

## Approval flow (discounts, voids, refunds, adjustments)

1. The action fails with `APPROVAL_REQUIRED` and tells you the action and amount.
2. Show the existing `ApprovalDialog`. On submit: `POST /approvals { action, approver_username, approver_secret, amount, target_id }`.
3. Retry the original request with `approval_id` from the response. The token is single use and expires in 2 minutes.

## Real-time (WebSocket)

```ts
import { connectRealtime } from "@/lib/api/client"

const stop = connectRealtime([`station:${branchId}:HOT`, `user:${userId}`], (event) => {
  if (event.type === "kitchen.ticket.created") refetchTickets()
})
```

Topics: `branch:<branchId>` (orders, payments, menu availability), `tables:<branchId>` (floor plan), `station:<branchId>:<code>` (KDS), `user:<userId>` (notifications). After a reconnect, reload full state, for example `GET /kitchen/stations/<code>/open-tickets`.

## Vocabulary mapping (demo store → API)

| Demo store | API |
|---|---|
| `DINE_IN`, `TAKEAWAY`, `DELIVERY` | `DineIn`, `Takeaway`, `Delivery` |
| `In Preparation` | `InPreparation` |
| `Awaiting Payment` | `AwaitingPayment` |
| `Out of Service` (state) | `is_out_of_service: true` flag (state stays separate, BR-027) |
| station `Hot`, `Cold`, `Beverage`… | `station_code` `HOT`, `COLD`, `BEV`, `DESSERT`, `BAR` |
| numbers for money | decimal strings |

## Suggested switch-over order

1. Login, lock screen, `/auth/me` and the role-based sidebar.
2. POS, orders, KDS and expo (highest value; uses WebSockets).
3. Floor plan, payments, cashier sessions.
4. Menu, inventory, settings, users, audit, dashboard and reports.
5. Phase 2 screens: customers, reservations, recipes, purchasing, expenses, employees, promotions and the advanced reports. The backend for all of them is ready.

## Phase 2 notes

* **Customers.** Contact details come back masked (`012 *** 678`) unless the user has `customers.contact.view`. `POST /customers` returns 409 `POSSIBLE_DUPLICATE` with `existing` matches. Attaching a customer to an order (`POST /customers/attach/{order_id}`) returns preferences and allergy notes to show on the POS.
* **Reservations.** `GET /reservations/availability?at=…&party_size=…` lists free tables. Seating a reservation (`POST /reservations/{id}/seat`) opens the order in one call.
* **Promotions.** Automatic promotions apply whenever the order changes; nothing to call. Show `GET /orders/{id}/promotions` on the bill: `applied` with the saving, and `not_applied` with a `reason` for each. Codes: `POST /orders/{id}/promo-codes { code }`, removed with `DELETE /orders/{id}/promo-codes/{redemption_id}`. Promotion discounts appear in the order's `discounts` with `promotion_id` set.
* **Purchasing.** PO approval returns 403 `SELF_APPROVAL` for the creator and `APPROVER_LIMIT_EXCEEDED` above the approver's `po_amount` limit (both in `/auth/me` limits). Posting a goods receipt can return `status: "PendingApproval"` with an `exception_note` when it's over tolerance.
* **Reports.** `GET /reports` lists only the reports the user can run. Each report returns `{summary, rows}`; some summaries carry extra breakdowns (RPT-15 `by_item` and `by_hour`, RPT-20 `by_item`, RPT-22 `daily` and `monthly`, RPT-23 `categories`). Filters: `date_from`, `date_to`, `user_id`, `customer_id`, `supplier_id`, `station_code`, `category`.
* **Dashboard.** `GET /dashboard?trend=day|week|month` adds `trends.series`, `costs` (theoretical food cost and approved expenses) and the `indicative_operating_result` with its label, which must be shown as written.
