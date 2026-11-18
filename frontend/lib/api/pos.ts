/**
 * POS and kitchen against the RMS API.
 *
 * Server data is loaded into the existing RMS store (lib/rms/store.ts) in the shapes the screens already use,
 * so the UI stays the same while the backend becomes the source of truth: prices, totals, statuses, numbering
 * and approvals all come from the API. After every change the affected order is reloaded from the server;
 * the WebSocket pushes changes made on other devices.
 */
import { toast } from "sonner"
import { api, ApiError, connectRealtime, newIdempotencyKey, type Schemas } from "./client"
import { requestApproval } from "@/components/rms/dialog-host"
import * as React from "react"
import { now, rms } from "@/lib/rms/store"
import { loadSessions } from "./cash"
import { useSession } from "./session"
import type {
  BillSplit,
  ComboPick,
  Category,
  Discount,
  FloorTable,
  ItemStatus,
  LineModifier,
  MenuItem,
  ModifierGroup,
  Order,
  OrderLine,
  OrderType,
  Payment,
  Station,
  TableState,
} from "@/lib/rms/types"

type ApiOrder = Schemas["OrderOut"]
type ApiItem = Schemas["OrderItemOut"]

// ---------------------------------------------------------------- mapping
/**
 * Server time -> the store clock's unit (seconds on a ticker that starts with the screen). Anchored to the ticker's
 * current value at load time, so ticket ages stay right even when a background tab slows the ticker down.
 */
const secs = (iso?: string | null) =>
  iso ? now() - Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000)) : undefined
const num = (v: string | number | null | undefined) => (v === null || v === undefined ? 0 : Number(v))

const STATION: Record<string, Station> = { HOT: "Hot", COLD: "Cold", BEV: "Beverage", DESSERT: "Dessert", BAR: "Bar" }
export const STATION_CODE: Record<Station, string | null> = { Hot: "HOT", Cold: "COLD", Beverage: "BEV", Dessert: "DESSERT", Bar: "BAR", None: null }
const TYPE: Record<string, OrderType> = { DineIn: "DINE_IN", Takeaway: "TAKEAWAY", Delivery: "DELIVERY" }
export const TYPE_CODE: Record<OrderType, string> = { DINE_IN: "DineIn", TAKEAWAY: "Takeaway", DELIVERY: "Delivery" }
const ITEM_STATUS: Record<string, ItemStatus> = { InPreparation: "In Preparation" }
const ITEM_STATUS_CODE: Partial<Record<ItemStatus, string>> = { "In Preparation": "InPreparation", Ready: "Ready", Served: "Served", Collected: "Collected" }
const TABLE_STATE: Record<string, TableState> = { AwaitingPayment: "Awaiting Payment" }
const PAY_METHOD: Record<string, string> = { "Cash USD": "CASH_USD", "Cash KHR": "CASH_KHR", KHQR: "KHQR", "Bank Transfer": "BANK_TRANSFER", Card: "CARD" }

const discountOf = (d: { kind: string; value: string | number; reason: string; approved_by?: string | null }): Discount => ({
  kind: d.kind === "Percent" ? "percent" : "amount",
  value: num(d.value),
  reason: d.reason,
  approvedBy: d.approved_by ?? undefined,
})

export const comboOf = (slots: { id: string; name_en: string; min_select: number; max_select: number; options: { variant_id: string; item_name_en: string; variant_name: string; price_delta: string; available: boolean }[] }[] | undefined) =>
  slots?.length
    ? slots.map((s) => ({
        id: s.id,
        name: s.name_en,
        min: s.min_select,
        max: s.max_select,
        options: s.options.map((o) => ({
          variantId: o.variant_id,
          name: o.variant_name === "Regular" ? o.item_name_en : `${o.item_name_en} (${o.variant_name})`,
          delta: Number(o.price_delta),
          available: o.available,
        })),
      }))
    : undefined

function toLine(i: ApiItem, discounts: ApiOrder["discounts"]): OrderLine {
  const d = discounts.find((x) => x.order_item_id === i.id)
  return {
    id: i.id,
    itemId: i.menu_item_id,
    name: i.item_name_en_snapshot,
    km: i.item_name_km_snapshot ?? "",
    variant: i.variant_name_snapshot === "Regular" ? undefined : i.variant_name_snapshot,
    modifiers: (i.modifiers ?? []).map((m) => ({ id: m.modifier_id, name: m.name_snapshot, delta: num(m.price_delta_snapshot) })),
    unitPrice: num(i.unit_price_snapshot),
    qty: num(i.quantity),
    note: i.note ?? undefined,
    allergy: i.is_allergy,
    seat: i.seat_no ?? undefined,
    status: ITEM_STATUS[i.item_status] ?? (i.item_status as ItemStatus),
    station: i.station_code ? (STATION[i.station_code] ?? "None") : "None",
    discount: d ? discountOf(d) : undefined,
    discountId: d?.id,
    voidType: i.void_type ? (i.void_type === "AfterPreparation" ? "After preparation" : i.void_type === "Comp" ? "Comp" : "Before preparation") : undefined,
    voidReason: i.void_reason ?? undefined,
    sentAt: secs(i.sent_at),
    startedAt: secs(i.started_at),
    readyAt: secs(i.ready_at),
    parentId: i.parent_item_id ?? undefined,
    slot: i.combo_slot_name ?? undefined,
  }
}

export function toOrder(o: ApiOrder): Order {
  const od = o.discounts.find((d) => !d.order_item_id)
  const t = o.totals
  const lines = o.items.map((i) => toLine(i, o.discounts))
  const lineDiscounts = o.items.reduce((s, i) => s + num(i.line_discount), 0)
  return {
    id: o.id,
    no: o.order_no,
    type: TYPE[o.order_type] ?? "TAKEAWAY",
    channel: o.channel === "Platform" ? "PLATFORM" : o.channel === "POS" ? "POS" : "ONLINE",
    table: o.table_code ?? o.table_tag ?? undefined,
    tableId: o.table_id ?? undefined,
    pickup: o.pickup_name ?? undefined,
    guests: o.guest_count ?? 1,
    server: "",
    customer: o.customer_name ?? undefined,
    lines,
    discount: od ? discountOf(od) : undefined,
    discountId: od?.id,
    status: o.order_status as Order["status"],
    payments: [],
    createdAt: secs(o.created_at) ?? 0,
    timeline: [],
    held: o.held_label ?? undefined,
    version: o.version,
    note: o.note ?? undefined,
    business: o.business_date,
    apiTotals: {
      gross: num(t.gross),
      itemDiscounts: lineDiscounts,
      orderDiscount: 0,
      subtotal: num(t.subtotal),
      service: num(t.service_charge),
      tax: num(t.tax),
      deliveryFee: num(t.delivery_fee),
      total: num(t.grand_total),
      paid: num(t.paid),
      balance: num(t.balance),
    },
  }
}

function toMenu(feed: { categories: Schemas["CategoryOut"][]; items: Schemas["MenuItemOut"][] }) {
  const groups = new Map<string, ModifierGroup>()
  const items: MenuItem[] = feed.items.map((i) => {
    for (const g of i.modifier_groups ?? [])
      groups.set(g.id, {
        id: g.id,
        name: g.name_en,
        km: g.name_km ?? "",
        min: g.min_select,
        max: g.max_select,
        modifiers: g.modifiers.filter((m) => m.is_active).map((m) => ({ id: m.id, name: m.name_en, delta: num(m.price_delta) })),
      })
    const variants = i.variants.filter((v) => v.is_active && v.price !== null && v.price !== undefined)
    const variantIds = Object.fromEntries(variants.map((v) => [v.name_en, v.id]))
    const several = variants.length > 1 || (variants[0] && variants[0].name_en !== "Regular")
    return {
      id: i.id,
      code: i.code,
      name: i.name_en,
      km: i.name_km ?? "",
      cat: i.category_id,
      station: i.station_code ? (STATION[i.station_code] ?? "None") : "None",
      price: num(variants[0]?.price),
      type: i.item_type === "Beverage" ? "Beverage" : i.item_type === "Food" ? "Food" : "Other",
      variants: several ? variants.map((v) => ({ name: v.name_en, price: num(v.price) })) : undefined,
      groups: (i.modifier_groups ?? []).map((g) => g.id),
      available: i.available && variants.length > 0,
      active: i.is_active,
      tax: i.tax_profile_id,
      desc: i.description ?? "",
      sku: i.barcode ?? undefined,
      channels: i.channels,
      variantIds,
      regularPrice: variants[0]?.regular_price ? num(variants[0].regular_price) : undefined,
      priceList: variants[0]?.price_list ?? undefined,
      combo: comboOf(i.combo_slots),
    }
  })
  const cats: Category[] = feed.categories.map((c) => ({ id: c.id, name: c.name_en, km: c.name_km ?? "", order: c.sort_order, active: c.is_active }))
  return { cats, groups: [...groups.values()], items }
}

// ---------------------------------------------------------------- errors and approvals
export function report(e: unknown) {
  toast.error(e instanceof ApiError ? e.message : "Can't reach the server. Check the connection and try again.")
}

/**
 * Run an action; if the backend answers APPROVAL_REQUIRED, ask a manager on this device (POST /approvals),
 * then run it again with the single-use approval id.
 */
export function withApproval<T>(label: string, run: (approvalId?: string) => Promise<T>, targetId?: string): Promise<T> {
  return run().catch((e) => {
    if (!(e instanceof ApiError) || e.code !== "APPROVAL_REQUIRED") throw e
    const action = String(e.body.action ?? "")
    const amount = e.body.amount === null || e.body.amount === undefined ? undefined : String(e.body.amount)
    let approvalId: string | undefined
    return new Promise<T>((resolve, reject) =>
      requestApproval({
        action: label,
        amount,
        verify: async (username, secret) => {
          try {
            const r = await api<{ approval_id: string }>("POST", "/approvals", {
              body: { action, approver_username: username, approver_secret: secret, amount, target_id: targetId },
            })
            approvalId = r.approval_id
          } catch (err) {
            throw new Error(err instanceof ApiError ? err.message : "Approval was not accepted")
          }
        },
        onApproved: () => run(approvalId).then(resolve, reject),
        onDeclined: () => reject(new ApiError(403, { code: "APPROVAL_CANCELLED", message: "Approval cancelled.", correlation_id: "" })),
      })
    )
  })
}

// ---------------------------------------------------------------- loading
export async function loadMenu() {
  const feed = await api<{ categories: Schemas["CategoryOut"][]; items: Schemas["MenuItemOut"][] }>("GET", "/menu/pos")
  const { cats, groups, items } = toMenu(feed)
  rms.loadCatalog(cats, groups, items)
}

export async function loadTables() {
  const [areas, tables] = await Promise.all([
    api<{ id: string; name: string }[]>("GET", "/dining-areas"),
    api<Schemas["TableOut"][]>("GET", "/tables"),
  ])
  const area = Object.fromEntries(areas.map((a) => [a.id, a.name]))
  const out: FloorTable[] = tables.map((t) => ({
    id: t.id,
    code: t.table_code,
    area: area[t.dining_area_id] ?? "",
    capacity: t.capacity,
    shape: (["square", "round", "rect"].includes(t.shape) ? t.shape : "square") as FloorTable["shape"],
    x: num(t.layout_x),
    y: num(t.layout_y),
    state: TABLE_STATE[t.service_state] ?? (t.service_state as TableState),
    guests: t.guest_count,
    orderId: t.open_order_id ?? undefined,
    seatedAt: secs(t.seated_at as string | null),
    outOfService: t.is_out_of_service ? (t.out_of_service_reason ?? "Out of service") : undefined,
    flagged: t.flagged,
    group: t.current_group_id ?? undefined,
    version: t.version,
    areaId: t.dining_area_id,
  }))
  rms.loadTables(out)
}

/** Open and draft (not yet sent or held) orders of the current business day, with their items. */
export async function loadOrders() {
  const pages = await Promise.all(
    ["Open", "Draft"].map((status) => api<{ data: { id: string }[] }>("GET", "/orders", { query: { status, page_size: 200 } }))
  )
  const ids = pages.flatMap((p) => p.data.map((o) => o.id))
  const orders = await Promise.all(ids.map((id) => api<ApiOrder>("GET", `/orders/${id}`)))
  rms.loadOrders(orders.map(toOrder))
}

export async function refreshOrder(id: string): Promise<Order> {
  const o = toOrder(await api<ApiOrder>("GET", `/orders/${id}`))
  rms.upsertOrder(o)
  return o
}

const pending = new Map<string, ReturnType<typeof setTimeout>>()
function refreshSoon(id: string) {
  clearTimeout(pending.get(id))
  pending.set(id, setTimeout(() => void refreshOrder(id).catch(() => undefined), 150))
}

/**
 * What this screen loads, decided by the signed-in user's permissions (the backend enforces them too):
 * a cook has kitchen.view but not orders.view, so the kitchen screen is then built from station tickets alone.
 */
const sync = { orders: true, tables: true, stations: [] as string[] }

/** Load everything the POS/KDS needs and keep it current with WebSocket events. Returns a stop function. */
export function startLiveSync(branchId: string, opts: { stations?: string[]; permissions?: string[]; userId?: string } = {}) {
  let alive = true
  const perms = opts.permissions
  sync.orders = !perms || perms.includes("orders.view")
  sync.tables = !perms || perms.includes("tables.view")
  sync.stations = opts.stations && (!perms || perms.includes("kitchen.view")) ? opts.stations : []
  const all = () =>
    Promise.all([
      loadMenu(),
      sync.tables ? loadTables() : undefined,
      sync.orders ? loadOrders() : undefined,
      sync.stations.length ? loadTickets(sync.stations) : undefined,
      // The POS needs to know whether this user has an open cashier session (cash payments need one).
      opts.userId && !opts.stations ? loadSessions(opts.userId, false) : undefined,
    ]).catch(report)
  void all()
  const topics = [
    `branch:${branchId}`,
    ...(sync.tables ? [`tables:${branchId}`] : []),
    ...sync.stations.map((s) => `station:${branchId}:${s}`),
  ]
  const stop = connectRealtime(topics, (ev) => {
    if (!alive) return
    const orderId = (ev.data?.order_id as string | undefined) ?? undefined
    if (ev.type.startsWith("menu.")) void loadMenu().catch(() => undefined)
    if (sync.tables && ev.topic.startsWith("tables:")) void loadTables().catch(() => undefined)
    if (orderId && sync.orders) refreshSoon(orderId)
    if (sync.stations.length && (ev.topic.startsWith("station:") || ev.type.startsWith("kitchen.") || ev.type.startsWith("order.")))
      ticketsSoon()
  })
  // After a reconnect the socket only delivers new events, so reload the full state now and then (SRS: KDS resync).
  const timer = setInterval(() => void all(), 60_000)
  return () => {
    alive = false
    clearInterval(timer)
    stop()
  }
}

let ticketTimer: ReturnType<typeof setTimeout> | undefined
function ticketsSoon() {
  clearTimeout(ticketTimer)
  ticketTimer = setTimeout(() => void loadTickets(sync.stations).catch(() => undefined), 150)
}

/** After a kitchen action: reload the order (if this user may read orders) and the station tickets. */
async function afterKitchen(orderId: string) {
  await Promise.all([sync.orders ? refreshOrder(orderId) : undefined, sync.stations.length ? loadTickets(sync.stations) : undefined])
}

// ---------------------------------------------------------------- floor plan
/**
 * Seat a party and open its order in one step (FR-TBL-006). The backend refuses parties over capacity and tables
 * reserved soon; pass the overrides after the user confirms (over-capacity needs tables.manage).
 */
export async function seatTable(tableId: string, guests: number, o: { overCapacity?: boolean; overrideReservation?: boolean } = {}) {
  const r = await api<{ order_id: string | null }>("POST", `/tables/${tableId}/seat`, {
    body: { guest_count: guests, allow_over_capacity: !!o.overCapacity, override_reservation: !!o.overrideReservation },
  })
  await Promise.all([loadTables(), r.order_id ? refreshOrder(r.order_id) : undefined])
  return r.order_id
}

const tableAction = async (fn: () => Promise<unknown>) => {
  await fn()
  await loadTables()
}
export const setTableState = (tableId: string, state: "Available" | "Cleaning") =>
  tableAction(() => api("POST", `/tables/${tableId}/state`, { body: { state } }))
export const outOfService = (tableId: string, reason: string) =>
  tableAction(() => api("POST", `/tables/${tableId}/out-of-service`, { body: { reason } }))
export const returnToService = (tableId: string) => tableAction(() => api("POST", `/tables/${tableId}/return-to-service`))
export const combineTables = (tableIds: string[]) => tableAction(() => api("POST", "/table-groups", { body: { table_ids: tableIds } }))
export const splitGroup = (groupId: string) => tableAction(() => api("DELETE", `/table-groups/${groupId}`))

// ---------------------------------------------------------------- POS actions
export async function createOrder(type: OrderType, o: { tableId?: string; tableTag?: string; guests?: number; pickup?: string; customer?: string }) {
  const created = await api<ApiOrder>("POST", "/orders", {
    idempotent: true,
    body: {
      order_type: TYPE_CODE[type],
      table_id: type === "DINE_IN" ? o.tableId : undefined,
      table_tag: type === "DINE_IN" && !o.tableId ? o.tableTag : undefined,
      guest_count: type === "DINE_IN" ? o.guests : undefined,
      pickup_name: type !== "DINE_IN" ? o.pickup || "Walk-in" : undefined,
      customer_name: o.customer,
      items: [],
    },
  })
  const order = toOrder(created)
  rms.upsertOrder(order)
  if (type === "DINE_IN") void loadTables().catch(() => undefined)
  return order
}

export async function addLine(
  orderId: string,
  item: MenuItem,
  pick: { variant?: string; modifiers: LineModifier[]; qty: number; note?: string; seat?: number; combo?: ComboPick[] }
) {
  const variantId = item.variantIds?.[pick.variant ?? "Regular"] ?? Object.values(item.variantIds ?? {})[0]
  if (!variantId) throw new ApiError(422, { code: "PRICE_MISSING", message: `${item.name} has no current price.`, correlation_id: "" })
  await api("POST", `/orders/${orderId}/items`, {
    body: [{ variant_id: variantId, quantity: String(pick.qty), modifiers: pick.modifiers.filter((m) => m.id).map((m) => ({ modifier_id: m.id })), note: pick.note || undefined, seat_no: pick.seat, combo: pick.combo ?? [] }],
  })
  return refreshOrder(orderId)
}

export async function setQty(orderId: string, line: OrderLine, qty: number) {
  if (qty <= 0) await api("POST", `/orders/${orderId}/items/${line.id}/cancel`, { body: { reason: "Removed before sending" } })
  else await api("PATCH", `/orders/${orderId}/items/${line.id}`, { body: { quantity: String(qty) } })
  return refreshOrder(orderId)
}

export async function setLine(orderId: string, lineId: string, patch: { note?: string; seat?: number }) {
  await api("PATCH", `/orders/${orderId}/items/${lineId}`, { body: { note: patch.note, seat_no: patch.seat } })
  return refreshOrder(orderId)
}

export async function updateOrder(orderId: string, patch: { guests?: number; pickup?: string; customer?: string; tableTag?: string }) {
  await api("PATCH", `/orders/${orderId}`, {
    body: { guest_count: patch.guests, pickup_name: patch.pickup, customer_name: patch.customer, table_tag: patch.tableTag },
  })
  return refreshOrder(orderId)
}

/** Sends new items to the kitchen. The idempotency key is reused if the request is retried (BR-030). */
export async function send(orderId: string) {
  const before = (await refreshOrder(orderId)).lines.filter((l) => l.status === "Pending").reduce((s, l) => s + l.qty, 0)
  await api("POST", `/orders/${orderId}/send`, { idempotent: newIdempotencyKey() })
  await refreshOrder(orderId)
  void loadTables().catch(() => undefined)
  return before
}

export async function voidLine(orderId: string, line: OrderLine, reason: string) {
  await withApproval(`Void ${line.qty} × ${line.name}`, (approval_id) =>
    api("POST", `/orders/${orderId}/items/${line.id}/cancel`, { body: { reason, approval_id } })
  )
  return refreshOrder(orderId)
}

export async function setDiscount(orderId: string, current: { discountId?: string }, d: Discount | undefined, itemId?: string) {
  if (current.discountId) await api("DELETE", `/orders/${orderId}/discounts/${current.discountId}`)
  if (d)
    await withApproval(`${d.kind === "percent" ? `${d.value}%` : `$${d.value}`} discount`, (approval_id) =>
      api("POST", `/orders/${orderId}/discounts`, {
        body: { order_item_id: itemId ?? null, kind: d.kind === "percent" ? "Percent" : "Amount", value: String(d.value), reason: d.reason, approval_id },
      })
    )
  return refreshOrder(orderId)
}

export async function hold(orderId: string, label: string) {
  await api("POST", `/orders/${orderId}/hold`, { body: { label } })
  return refreshOrder(orderId)
}

export async function resume(orderId: string) {
  await api("POST", `/orders/${orderId}/resume`)
  return refreshOrder(orderId)
}

export async function transfer(orderId: string, tableId: string) {
  await api("POST", `/orders/${orderId}/transfer`, { body: { table_id: tableId } })
  await loadTables()
  return refreshOrder(orderId)
}

type ApiBill = Schemas["BillOut"]
const toSplits = (bills: ApiBill[]): BillSplit[] | undefined =>
  bills.length > 1
    ? [...bills]
        .sort((a, b) => a.split_index - b.split_index)
        .map((b) => ({ label: `Bill ${b.split_index}`, total: num(b.total), balance: num(b.balance), billId: b.id }))
    : undefined

/** Load the order's active bills; a split order shows one entry per bill with its own balance. */
export async function loadBills(orderId: string) {
  const bills = await api<ApiBill[]>("GET", `/orders/${orderId}/bills`)
  rms.updateOrder(orderId, { splits: toSplits(bills) })
  return bills
}

/**
 * Split the bill (or return to one bill with mode "single"). The server works out each bill's lines, charges and
 * rounding; unpaid bills are replaced, and once paying has started the split can no longer change.
 */
export async function splitBills(orderId: string, mode: "single" | "equal" | "items" | "seats", parts = 1, assignment?: Record<string, number>) {
  const bills = await api<ApiBill[]>("POST", `/orders/${orderId}/bills`, {
    body: { mode, parts: mode === "single" ? 1 : parts, assignment: mode === "items" ? assignment : undefined },
  })
  rms.setSplits(orderId, toSplits(bills))
  await refreshOrder(orderId)
  return bills
}

async function openBill(orderId: string) {
  const bills = await api<Schemas["BillOut"][]>("GET", `/orders/${orderId}/bills`)
  const open = bills.find((b) => b.status === "Open" || b.status === "PartiallyPaid")
  if (open) return open
  const made = await api<Schemas["BillOut"][]>("POST", `/orders/${orderId}/bills`, { body: { mode: "single" } })
  return made[0]
}

export async function printBill(orderId: string) {
  const bill = await openBill(orderId)
  await api("POST", `/bills/${bill.id}/print`)
  void loadTables().catch(() => undefined)
  return refreshOrder(orderId)
}

export async function pay(
  orderId: string,
  p: { method: string; currency: "USD" | "KHR"; tendered?: number; changeCurrency?: "USD" | "KHR"; reference?: string; billId?: string }
) {
  const bill = p.billId ? { id: p.billId } : await openBill(orderId)
  const r = await api<{
    payment_id: string
    status: string
    amount_tendered: string
    amount_applied: string
    amount_base: string
    rate: string | null
    change: { currency: "USD" | "KHR"; amount: string } | null
    receipt_no: string | null
  }>("POST", "/payments", {
    idempotent: true,
    body: {
      bill_id: bill.id,
      method: PAY_METHOD[p.method] ?? p.method,
      currency: p.currency,
      amount_tendered: p.tendered !== undefined ? String(p.tendered) : undefined,
      change_currency: p.changeCurrency,
      reference: p.reference,
    },
  })
  const payment: Payment = {
    id: r.payment_id,
    method: p.method,
    currency: p.currency,
    tendered: num(r.amount_tendered),
    rate: r.rate ? num(r.rate) : undefined,
    applied: num(r.amount_base),
    change: num(r.change?.amount),
    changeCurrency: r.change?.currency ?? p.changeCurrency ?? p.currency,
    reference: p.reference,
    state: r.status === "Confirmed" ? "Confirmed" : "Pending",
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  }
  rms.addLocalPayment(orderId, payment)
  const bills = p.billId ? await loadBills(orderId) : undefined
  const order = await refreshOrder(orderId)
  if (r.receipt_no) rms.updateOrder(orderId, { receiptNo: r.receipt_no })
  void loadTables().catch(() => undefined)
  return { order, payment, change: r.change, splits: bills ? toSplits(bills) : undefined }
}

// ---------------------------------------------------------------- kitchen (KDS)
interface TicketRef {
  ids: string[]
  priority: number
}
let tickets = new Map<string, TicketRef>() // `${orderId}:${station}` -> open tickets
let lastBumped: { orderId: string; station: Station; ticketIds: string[] }[] = []

export async function loadTickets(stations: string[]) {
  const lists = await Promise.all(stations.map((s) => api<Schemas["TicketOut"][]>("GET", `/kitchen/stations/${s}/open-tickets`)))
  const next = new Map<string, TicketRef>()
  for (const list of lists)
    for (const t of list) {
      const key = `${t.order_id}:${STATION[t.station_code] ?? "None"}`
      const ref = next.get(key) ?? { ids: [], priority: 0 }
      ref.ids.push(t.ticket_id)
      ref.priority = Math.max(ref.priority, t.priority)
      next.set(key, ref)
    }
  tickets = next
  if (!sync.orders) rms.loadOrders(ticketOrders(lists.flat()))
  for (const [key, ref] of next) {
    const [orderId, station] = key.split(":")
    if (ref.priority > 0) rms.markRush(orderId, station as Station, true)
  }
}

const KITCHEN_VOID: Record<string, OrderLine["voidType"]> = {
  BeforePreparation: "Before preparation",
  AfterPreparation: "After preparation",
  Comp: "Comp",
}

/** Orders as the kitchen sees them, built from open station tickets (for users without orders.view). */
function ticketOrders(list: Schemas["TicketOut"][]): Order[] {
  const byOrder = new Map<string, Order>()
  for (const t of list) {
    const station = STATION[t.station_code] ?? "None"
    const sentAt = secs(t.created_at) ?? 0
    const o =
      byOrder.get(t.order_id) ??
      ({
        id: t.order_id,
        no: t.order_no,
        type: TYPE[t.order_type] ?? "TAKEAWAY",
        channel: "POS",
        table: t.table_code ?? undefined,
        pickup: t.pickup_name ?? undefined,
        guests: 0,
        server: "",
        lines: [],
        status: "Open",
        payments: [],
        createdAt: sentAt,
        timeline: [],
        version: 0,
        business: "",
        rush: [],
      } satisfies Order)
    o.createdAt = Math.min(o.createdAt, sentAt)
    if (t.priority > 0 && !o.rush!.includes(station)) o.rush!.push(station)
    for (const i of t.items) {
      if (o.lines.some((l) => l.id === i.order_item_id)) continue
      // A prepared item that was cancelled and already has an outcome needs nothing more from the kitchen.
      o.lines.push({
        id: i.order_item_id,
        itemId: "",
        name: i.name_en,
        km: i.name_km ?? "",
        variant: i.variant === "Regular" ? undefined : i.variant,
        modifiers: i.modifiers.map((name) => ({ name, delta: 0 })),
        unitPrice: 0,
        qty: num(i.quantity),
        note: i.note ?? undefined,
        allergy: i.is_allergy,
        status: ITEM_STATUS[i.status] ?? (i.status as ItemStatus),
        station,
        voidType: i.void_type && !i.waste_outcome ? KITCHEN_VOID[i.void_type] : undefined,
        version: i.version,
        sentAt,
        startedAt: secs(i.started_at),
        readyAt: secs(i.ready_at),
      })
    }
    byOrder.set(t.order_id, o)
  }
  return [...byOrder.values()]
}

export async function setLineStatus(orderId: string, lineId: string, status: ItemStatus) {
  const code = ITEM_STATUS_CODE[status]
  if (!code) return
  await api("POST", `/kitchen/items/${lineId}/status`, { body: { status: code } })
  await afterKitchen(orderId)
}

export async function startTicket(order: Order, station: Station) {
  for (const l of order.lines.filter((x) => x.station === station && x.status === "Sent"))
    await api("POST", `/kitchen/items/${l.id}/status`, { body: { status: "InPreparation" } })
  await afterKitchen(order.id)
}

export async function bump(orderId: string, station: Station) {
  const ref = tickets.get(`${orderId}:${station}`)
  if (!ref?.ids.length) throw new ApiError(404, { code: "NOT_FOUND", message: "This ticket is no longer open. The screen will refresh.", correlation_id: "" })
  for (const id of ref.ids) await api("POST", `/kitchen/tickets/${id}/bump`)
  lastBumped = [{ orderId, station, ticketIds: ref.ids }, ...lastBumped].slice(0, 20)
  await afterKitchen(orderId)
}

export async function recall() {
  const last = lastBumped[0]
  if (!last) return undefined
  for (const id of last.ticketIds) await api("POST", `/kitchen/tickets/${id}/recall`)
  lastBumped = lastBumped.slice(1)
  await afterKitchen(last.orderId)
  return last
}

export async function toggleRush(orderId: string, station: Station, rush: boolean) {
  const ref = tickets.get(`${orderId}:${station}`)
  for (const id of ref?.ids ?? []) await api("POST", `/kitchen/tickets/${id}/priority`, { body: { priority: rush ? 1 : 0 } })
  rms.markRush(orderId, station, rush)
}

export async function wasteOutcome(orderId: string, lineId: string, outcome: "Wastage" | "Reusable") {
  await api("POST", `/kitchen/items/${lineId}/waste-outcome`, { body: { outcome } })
  await afterKitchen(orderId)
}

export async function serveAll(orderId: string) {
  await api("POST", `/orders/${orderId}/serve`, { body: {} })
  if (sync.tables) void loadTables().catch(() => undefined)
  await afterKitchen(orderId)
}

/** Keep the POS/KDS store in sync with the API for the current branch while the screen is open. */
export function useLiveSync(stations?: string[]) {
  const { me } = useSession()
  const branchId = me?.current_branch.id
  const key = stations?.join(",")
  const perms = me?.permissions.join(",")
  const userId = me?.id
  React.useEffect(() => {
    if (!branchId) return
    return startLiveSync(branchId, { stations: key ? key.split(",") : undefined, permissions: perms ? perms.split(",") : [], userId })
  }, [branchId, key, perms, userId])
}
