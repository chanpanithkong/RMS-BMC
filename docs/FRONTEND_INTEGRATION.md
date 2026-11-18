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

Switched to the API so far:

* **Sign-in and session** (`lib/api/session.ts`, `components/rms/auth-gate.tsx`, `components/login-form.tsx`): the login form calls `POST /auth/login`; staff pages restore the session from the refresh cookie on load and send signed-out users to `/login?next=…` (same-site paths only); `/auth/me` supplies the user, all their roles, permissions, branches and business date; sign-out calls `POST /auth/logout`; the header shows the real branch (switching sends `X-Branch-Id`) and business date. The sidebar and page gate use every role the user holds. The demo "Preview as role" switcher is gone.
* **POS, kitchen and expo** (`lib/api/pos.ts`, `app/(fullscreen)/pos`, `app/(fullscreen)/kds`, `kds/expo`, `components/rms/pos-dialogs.tsx`): menu, tables and orders load from `/menu/pos`, `/tables`, `/dining-areas` and `/orders`; every action (create order, add, change or remove items, notes and seats, send, hold, resume, move table, discounts, cancel items, print bill, take payment, kitchen start, ready, bump, recall, rush, waste outcome, serve) calls the API and then reloads that order from the server. Totals shown are the server's (`totals`). The WebSocket topics keep other screens current, and everything reloads once a minute in case events were missed. When the backend answers `APPROVAL_REQUIRED`, the approval dialog asks for a manager's username and PIN or password, calls `POST /approvals`, and retries with the `approval_id`. Users without `orders.view` (cooks) get a kitchen screen built from `GET /kitchen/stations/{code}/open-tickets` alone; ticket items carry `void_type`, `waste_outcome`, `started_at` and `ready_at` for this. Split bills use `POST /orders/{id}/bills` (equal, by item, by seat); the payment dialog then pays each bill separately. Not connected yet: the customer list on the POS (still demo data) and offline queueing.
* **Floor plan, cashier sessions, bills and payments** (`app/(back-office)/tables`, `shifts`, `billing`, `lib/api/cash.ts`, `lib/api/billing.ts`): the floor plan seats tables with `POST /tables/{id}/seat` (asking before over-capacity or reserved-soon overrides), moves, combines and splits tables, takes them out of service and marks cleaning done. Shifts open a session with floats, record paid-outs, paid-ins and drops, show X/Z reports from `/cashier-sessions/{id}/report`, and close with a blind count; expected cash and variance come back only after the count. A different user with `cash.approve` approves a variance or force-closes a session as themselves. Session responses now include `user_name`, `approved_by_name` and `movements`. The billing page lists the day's orders, payments, receipts and refunds from the API; voids go through the approval flow, refunds are requested by one user and approved or rejected by another, and receipts reprint marked COPY. The header's cash-session indicator reads `/cashier-sessions/current`. Not connected yet: the table layout editor, and payment reconciliation against bank or provider statements (no backend for it).
* **Back office (stage 4)**: every remaining screen reads and writes through the API and the shared store starts empty, so no sample data is shown. Menu (items, effective-dated prices, categories, modifier groups, availability), recipes (draft, publish, new version, server food cost, unmapped items), promotions (rules, codes, reason codes, role limits, loyalty settings), inventory (ingredients, balances, movements and reversals, issue/adjustment/wastage documents with approval, blind counts, transfers), purchasing (requests, POs, receiving, returns, invoice matching and payment), suppliers, expenses (draft, receipt upload, submit, approve, pay, reverse), customers (search, duplicates and merge, anonymise, loyalty history and adjustment, credit accounts and settlements), reservations (timeline, list, waiting list, seating), delivery (takeaway, deliveries, riders, online orders, platform orders, zones, performance), orders and order detail, kitchen supervision, users and roles (permissions, approval limits, sessions, sign-in history, approvals log, access review), employees (schedule, attendance, departments, positions, activity), branches (comparison, transfers between branches, devices), settings (features, currency and rates, tax rules, payment methods, stations, policies, text messages, Xero account codes and journal export, day end, change history), audit trail (filters, hash-chain check, CSV export), notifications (header bell and centre, live over `user:<id>`), dashboard (only the widgets the server returns for the role) and reports (catalogue, viewer built from the report's summary and rows, CSV export, background jobs). The table layout editor saves positions with the table version. Staff pages added or fixed: change password (calls the API, then reloads `/auth/me`), forgot and reset password (`/reset-password?token=`), PIN lock screen (needs the terminal's device token from Branches → Devices). Public pages: online ordering priced by `/quote` (checkout sends `expected_total` and an Idempotency-Key; `PRICE_CHANGED` re-quotes), tracking at `/track/<token>`, table QR ordering at `/qr/<token>`, customer sign-in by text-message code. New backend list endpoints (read-only): `GET /inventory/counts`, `/inventory/documents`, `/inventory/transfers`, `/purchase-returns`, `/attendance`. Phase 4 (below) adds combos, price lists and menu schedules, recurring expenses, scheduled report emails, the message delivery log and personal notification preferences, payment reconciliation, and the KHQR code on online orders.

The other screens still read the demo store in `lib/rms/` (the session feeds it the real user, roles and branch). Switch them one module at a time.

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

1. Login, `/auth/me` and the role-based sidebar (done; PIN login on the lock screen still to do).
2. POS, orders, KDS and expo (done, except split bills and offline queueing).
3. Floor plan, payments, cashier sessions (done, except the layout editor).
4. Menu, inventory, settings, users, audit, dashboard and reports (done).
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

## Phase 4 notes

Migrations (additive only; nothing is dropped): `phase4_price_lists_and_menu_schedules`, `phase4_combo_slots`, `phase4_reconciliation_schedules_preferences`. After upgrading a database, run `python -m scripts.seed` once so existing roles get the new permissions (`payments.reconcile`, `messages.view`, `messages.retry`); it only adds missing rows.

* **Price lists and menu schedules (FR-MENU-008, BR-003)**: `GET/POST /price-lists`, `PATCH /price-lists/{id}`, `GET /price-lists/{id}/prices`, `GET/POST /menu-schedules`, `PUT /menu-schedules/{id}`. Automatic lists apply by day, hours (may pass midnight), channel, order type and branch, highest priority wins, in the branch's local time. The POS feed returns `price`, plus `regular_price` and `price_list` while a list applies (tiles show the normal price struck through). Items on a schedule can be ordered only while a schedule is in effect.
* **Combos (FR-MENU-005)**: a menu item of type `Combo` has slots: `GET/PUT /menu-items/{id}/combo-slots` (`{slots: [{name_en, min_select, max_select, options: [{variant_id, price_delta}]}]}`); `MenuItemOut.combo_slots` carries them in the POS and public menus. Add a combo with `{variant_id, quantity, combo: [{slot_id, variant_id}]}`. The order gets a combo line at 0.00 and one line per chosen item (`parent_item_id`, `combo_slot_name`); the combo price plus extra charges is **split across the items in proportion to their normal prices** (owner's decision), so item sales, food cost, tax, kitchen routing and stock follow the real items. Quantity changes and cancellation act on the combo line (`COMBO_PART` on a single item); one approval covers prepared items. Item discounts and automatic promotions don't apply to combo lines (`COMBO_DISCOUNT`). Item modifiers inside a combo are not offered.
* **Payment reconciliation (FR-BILL-018)**, Billing → Reconciliation, permission `payments.reconcile` (Accountant, GM, Branch manager, Owner): `GET /payment-reconciliation?business_date&method_code`, `POST /payment-reconciliation/lines` (typed lines) or `/import` (`csv` with `reference,amount[,currency][,received_at]`; all-or-nothing), `POST /payment-reconciliation/lines/{id}/match` (by hand, with a note), `/remove` (a mistyped statement line, audited), `POST /payment-reconciliation/close` (a note is required when anything is unmatched or differs). Matching uses the payment reference (case and spaces ignored), then amount and currency. A reference already entered is skipped, so re-importing adds nothing. Payments are never changed here. `GET /payment-reconciliation/days` lists the last 30 days.
* **Delivery log (FR-NOTIF-013)**, Notifications → Delivery log, `messages.view`: `GET /message-log?date_from&date_to&channel&status` lists text messages and emails with status (Queued, Retrying, Sent, Logged = email not set up so only logged, Failed), attempts and last error. Numbers and addresses are masked, and SMS text hidden, for viewers without `customers.contact.view`; email bodies are never shown. `POST /message-log/{SMS|Email}/{id}/retry` (`messages.retry`) gives a failed message a fresh set of attempts. Emails now back off like SMS (30 s doubling; `OUTBOX_MAX_ATTEMPTS`, `OUTBOX_BACKOFF_SECONDS`).
* **Notification preferences (FR-NOTIF-011)**, Notifications → Preferences: `GET/PUT /me/notification-preferences`. Always on (owner's decision, "safety and money"): approvals, kitchen, payment, cash, system. Can be muted: stock (low stock and expiry), reminders, daily summaries. Muting a mandatory kind returns `NOTIFICATION_MANDATORY`.
* **Recurring expenses (FR-EXP-008)**, Expenses → Recurring: `GET/POST /expense-templates`, `PUT /expense-templates/{id}`, `POST /expense-templates/generate`. Weekly or monthly (short months use their last day). The worker (`generate_recurring_expenses`, hourly) creates one **Draft** per template and date (never twice); a person still submits it for approval.
* **Scheduled report emails (FR-RPT-027)**, Reports → Scheduled, `report.export`: `GET/POST /report-schedules`, `PUT /report-schedules/{id}`. Daily (yesterday), weekly (last 7 days) or monthly (previous month) at an hour in branch time. Each recipient must have an email, access to the branch and permission for the report; the worker (`run_report_schedules`) runs one background job per recipient with their own permissions and emails a sign-in link to Reports → Background jobs (no report data in the email). Email is only logged until SMTP is configured.
* **KHQR on online orders (FR-ONL-007)**: the public menu now returns `payment: {online: "khqr" | "redirect" | null, pay_later}`. When a KHQR gateway is configured, checkout offers "Pay now (KHQR)" (`payment: "Online"`), and the tracking page draws the KHQR code (npm package `qrcode`), counts down to its expiry, checks the payment every 5 seconds and offers a new code once it expires (`GET/POST /public/track/{token}/payment`). Without a gateway, checkout stays pay at pickup or on delivery.
