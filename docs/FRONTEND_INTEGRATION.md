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
| `BRANCH_FORBIDDEN`, `WRONG_BRANCH` (403) | The user isn't assigned to that branch, or the action belongs to the other branch of a transfer |
| `VARIANCE_REASON_REQUIRED` (422) | A short-received transfer line needs a reason |
| `DELIVERY_DETAILS_REQUIRED`, `ZONE_NOT_SERVED`, `MINIMUM_ORDER_NOT_MET` | Ask for zone and address, or show the zone's minimum |
| `ORDER_NOT_READY`, `NOT_YOUR_DELIVERY`, `NOT_A_RIDER` | Rider screen: wait for the kitchen, or the delivery belongs to someone else |
| `PLATFORM_REF_EXISTS` (409) | The platform order was already entered |
| `PRICE_CHANGED` (409) | Online checkout: show `current_total` and ask the customer to confirm |
| `ONLINE_ORDERING_PAUSED`, `BRANCH_CLOSED`, `TOO_SOON`, `QUANTITY_LIMIT` | Online checkout messages |
| `PAYMENT_PENDING` (409) | Staff: wait for the online payment before accepting |
| `RATE_LIMITED` (429) | Public pages: wait `retry_after_seconds` and try again |

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

## Phase 3 notes

* **Branches.** Send `X-Branch-Id: <code or id>` to act in another branch the user is assigned to. `GET /branch-comparison` and RPT-06 need `report.cross_branch`.
* **Transfers between branches.** The sending branch calls `POST /branch-transfers`; the receiving branch sees it in `GET /branch-transfers?direction=in` and calls `/receive` with any short quantities and a reason.
* **Delivery.** Create delivery orders with `delivery: {zone_id, address, landmark?, latitude?, longitude?}`; the server sets the fee. The rider app uses `GET /deliveries/mine` and the `/out`, `/delivered` and `/failed` actions. Listen for `delivery.updated` on `branch:<id>`.
* **Ready board.** `GET /ready-board` lists paid takeaway orders that are ready; poll it or refresh on `order.updated`.
* **Public online ordering.** These routes need no token and are rate limited:
  * `GET /public/branches/{code}/menu` and `/delivery-zones`
  * `POST /public/branches/{code}/quote` to show totals while the cart changes
  * `POST /public/branches/{code}/orders` with an `Idempotency-Key` and `expected_total`; on `PRICE_CHANGED` show the new total
  * the response has `tracking_url` (build a page at `/track/[token]` that calls `GET /public/track/{token}`) and, for online payment, `payment.redirect_url`
  * table QR codes point to `/qr/[token]`; that page calls `GET /public/qr/{token}` and `POST /public/qr/{token}/orders`
* **Online payment.** Only the sandbox gateway exists. Its `redirect_url` points at `/pay/sandbox` in the frontend, which is a placeholder: the payment is confirmed only by a signed server-to-server callback, never by the browser.
* **Staff screens.** `GET /online-orders` (incoming), `/accept` and `/reject`, and `PUT /online-ordering/pause`. A new online order also raises an in-app notification for users with `orders.edit`.
* **Loyalty.** Show `GET /customers/{id}/loyalty` (balance, redeemable points and value, points expiring within 30 days) when a customer is attached. Redeem with `POST /orders/{id}/loyalty-redemption { points }` in steps of 100 and undo with `DELETE`. Errors: `LOYALTY_DISABLED`, `LOYALTY_CUSTOMER_REQUIRED`, `LOYALTY_STEP`, `LOYALTY_INSUFFICIENT`, `LOYALTY_EXCEEDS_ORDER`, `LOYALTY_NOT_COMBINABLE`, `LOYALTY_ALREADY_REDEEMED`, and `LOYALTY_REDEMPTION_APPLIED` when a manual discount would replace it.
* **Bakong KHQR payment.** With `PAYMENT_GATEWAY=bakong`, checkout with `payment: "Online"` returns `payment: {kind: "khqr", qr, md5, expires_at, amount, currency}`. Render `qr` as a QR image with the KHQR frame and a countdown to `expires_at`. Poll `GET /public/track/{token}/payment` every 3 to 5 seconds until `payment_status` is `Paid` or `Failed` (`check` says `expired` when time ran out). Offer "New QR code" with `POST /public/track/{token}/payment`. The browser never confirms a payment; the server checks Bakong and the worker also polls every 10 seconds.
* **Customer accounts (online).** `POST /public/branches/{code}/account/code {phone}` texts a 6-digit code; `POST /public/branches/{code}/account/verify {phone, code, name?}` returns `customer_token` (`NAME_REQUIRED` the first time). Send it as `X-Customer-Token` on checkout and on `GET /public/account` and `/public/account/orders`; `POST /public/account/sign-out` ends it. Errors: `SMS_UNAVAILABLE` (503), `CODE_INVALID` (with `tries_left`), `RATE_LIMITED`, `CUSTOMER_SIGN_IN_REQUIRED`, `CUSTOMER_SESSION_INVALID`. Keep the token in memory or secure storage, not in a URL.
* **Accounting export.** A back-office page for users with `accounting.export`: show `GET /accounting/mapping` (highlight `placeholder: true`), let the owner edit codes through `PUT /settings/accounting`, preview `GET /accounting/journals?date_from&date_to` (each journal balances; show any `warnings`), and download `/accounting/journals/xero.csv`. `MAPPING_NOT_CONFIRMED` (409) means the mapping hasn't been confirmed yet.
* **GrabFood orders.** New Grab orders appear in `GET /platform-orders` with `acceptance: "Received"` and raise an in-app notification; staff must answer within 5 minutes with `POST /platform-orders/{order_id}/accept` or `/reject {reason}`. Show `platform_short_no` (e.g. GF-123), `external_state` (driver status) and any `mismatch_note`. Menu ID mapping: `GET/POST /platform-item-maps`. The webhook log for troubleshooting: `GET /integrations/grabfood/inbound`.
* **Grab menu.** A settings page can show `GET /integrations/grabfood/menu/preview` (what Grab will receive, KHR minor units) and a "Sync menu to Grab" button for `POST /integrations/grabfood/menu/sync` (`GRABFOOD_NOT_LINKED` until the branch has a Grab merchant ID; `EXCHANGE_RATE_MISSING` without today's KHR rate). Sold-out changes go to Grab automatically.
* **Credit accounts.** At payment, offer "Charge to account" when the attached customer has an account (`GET /credit-accounts`, showing `available` and `overdue`), then `POST /bills/{id}/charge-to-account {account_id}`. On `APPROVAL_REQUIRED` with `action: "credit_override"`, open the approval dialog (`POST /approvals` with that action, the bill as `target_id` and the amount) and retry with `approval_id`. Back office: open and edit accounts, `POST /credit-accounts/{id}/settlements`, and `GET /credit-accounts/{id}/statement`. Errors: `CREDIT_DISABLED`, `CREDIT_ACCOUNT_INACTIVE`, `CREDIT_ACCOUNT_MISMATCH`, `SETTLEMENT_EXCEEDS_BALANCE`, `CREDIT_BALANCE_OUTSTANDING`.
* **Analytics.** Charts can read `GET /analytics/summary?dimension=item|category|hour|method|employee|ingredient&date_from&date_to` (show `last_refreshed`). A menu engineering page reads `GET /analytics/menu-engineering` (a 2x2 matrix by `classification`). For long reports, `POST /reports/{id}/jobs {date_from, date_to, ...filters}`, poll `GET /report-jobs/{id}` until `status` is `Done` (or `Failed` with `error`), then download from `download`. `REPORT_NOT_AVAILABLE` means the link expired.
