"use client"
// Shared client state for the staff screens. Everything is loaded from the RMS API (lib/api/*) and starts
// empty, so no sample data is ever shown. The older local actions below remain only for screens' internal
// bookkeeping; changes that matter are always made through the API and then reloaded from the server.
import { useSyncExternalStore } from "react"
import { categories as seedCategories, modifierGroups, BUSINESS_DATE } from "./seed"
import { calcBill, kitchenStatus } from "./billing"
import type {
  BillSplit,
  CashMovement,
  CashierSession,
  Category,
  DeliveryStatus,
  Discount,
  FloorTable,
  ItemStatus,
  MenuItem,
  ModifierGroup,
  Notice,
  Order,
  OrderLine,
  OrderType,
  Payment,
  Reservation,
  Role,
  Station,
  TableState,
  VoidType,
  WaitParty,
} from "./types"

export interface RmsState {
  role: Role
  /** Every role the signed-in user holds (navigation shows what any of them allows). */
  roles: Role[]
  userName: string
  lang: "en" | "km"
  branch: string
  online: boolean
  orders: Order[]
  tables: FloorTable[]
  menu: MenuItem[]
  notices: Notice[]
  reservations: Reservation[]
  waitlist: WaitParty[]
  sessions: CashierSession[]
  onlinePaused: boolean
  orderSeq: number
  receiptSeq: number
  recalled: { orderId: string; station: Station }[]
}

const initial: RmsState = {
  // User, roles and branch are set from /auth/me when the session loads (lib/api/session.ts).
  role: "WAITER",
  roles: [],
  userName: "",
  lang: "en",
  branch: "",
  online: true,
  orders: [],
  tables: [],
  menu: [],
  notices: [],
  reservations: [],
  waitlist: [],
  sessions: [],
  onlinePaused: false,
  orderSeq: 110,
  receiptSeq: 4420,
  recalled: [],
}

seedCategories.splice(0, seedCategories.length)
modifierGroups.splice(0, modifierGroups.length)
let state = initial
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())
const set = (
  patch: Partial<RmsState> | ((s: RmsState) => Partial<RmsState>)
) => {
  state = { ...state, ...(typeof patch === "function" ? patch(state) : patch) }
  emit()
}
const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => {
    listeners.delete(l)
  }
}

export function useRms() {
  return useSyncExternalStore(
    subscribe,
    () => state,
    () => initial
  )
}

// A deterministic seconds counter: 0 during SSR, ticking after hydration.
let clock = 0
let clockTimer: ReturnType<typeof setInterval> | undefined
const clockListeners = new Set<() => void>()
const subscribeClock = (l: () => void) => {
  clockListeners.add(l)
  clockTimer ??= setInterval(() => {
    clock += 1
    clockListeners.forEach((f) => f())
  }, 1000)
  return () => {
    clockListeners.delete(l)
  }
}
export const useClock = () =>
  useSyncExternalStore(
    subscribeClock,
    () => clock,
    () => 0
  )
export const now = () => clock

export const elapsed = (from: number | undefined, at: number) =>
  from === undefined ? 0 : Math.max(at - from, 0)
export const mmss = (s: number) =>
  `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
export const minLabel = (s: number) =>
  s < 3600
    ? `${Math.floor(s / 60)}m`
    : `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
export const initials = (n?: string) =>
  (n ?? "")
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()

const stamp = () => {
  const base = 13 * 60 + 2 + Math.floor(clock / 60)
  return `${String(Math.floor(base / 60)).padStart(2, "0")}:${String(base % 60).padStart(2, "0")}`
}

const patchOrder = (id: string, fn: (o: Order) => Order) =>
  set((s) => ({
    orders: s.orders.map((o) =>
      o.id === id ? { ...fn(o), version: o.version + 1 } : o
    ),
  }))
const patchTable = (code: string | undefined, patch: Partial<FloorTable>) =>
  code &&
  set((s) => ({
    tables: s.tables.map((t) => (t.code === code ? { ...t, ...patch } : t)),
  }))
const log = (o: Order, label: string): Order => ({
  ...o,
  timeline: [
    ...o.timeline,
    { at: clock, label, user: state.userName, time: stamp() },
  ],
})
const notice = (n: Omit<Notice, "id" | "at" | "read">) =>
  set((s) => ({
    notices: [
      { ...n, id: `n${s.notices.length + 100}`, at: stamp(), read: false },
      ...s.notices,
    ],
  }))

function settle(id: string) {
  const o = state.orders.find((x) => x.id === id)
  if (!o || o.status !== "Open") return
  const live = o.lines.filter((l) => l.status !== "Cancelled")
  const delivered =
    live.length > 0 &&
    live.every((l) => l.status === "Served" || l.status === "Collected")
  const totals = calcBill(o)
  if (delivered && totals.balance === 0) {
    patchOrder(id, (x) => log({ ...x, status: "Completed" }, "Order completed"))
    if (o.table) patchTable(o.table, { state: "Cleaning", orderId: undefined })
  } else if (o.table) {
    const t = state.tables.find((x) => x.code === o.table)
    if (t && delivered && t.state === "Ordering")
      patchTable(o.table, { state: "Served" })
  }
}

export const rms = {
  setRole: (role: Role) => set({ role }),
  setUser: (userName: string, role?: Role, roles?: Role[]) =>
    set({ userName, ...(role ? { role, roles: roles?.length ? roles : [role] } : {}) }),
  setLang: (lang: "en" | "km") => set({ lang }),
  setBranch: (branch: string) => set({ branch }),
  toggleOnline: () => set((s) => ({ online: !s.online })),
  toggleOnlinePaused: () => set((s) => ({ onlinePaused: !s.onlinePaused })),

  createOrder(type: OrderType, opts: Partial<Order> = {}): string {
    const seq = state.orderSeq + 1
    const o: Order = {
      id: `o${seq}`,
      no: `#${String(seq).padStart(4, "0")}`,
      type,
      channel: "POS",
      guests: 1,
      server: state.userName.split(" ")[0],
      lines: [],
      status: "Draft",
      payments: [],
      createdAt: clock,
      business: BUSINESS_DATE,
      version: 1,
      timeline: [
        {
          at: clock,
          label: "Order created",
          user: state.userName,
          time: stamp(),
        },
      ],
      ...opts,
    }
    set((s) => ({ orders: [o, ...s.orders], orderSeq: seq }))
    if (o.table) patchTable(o.table, { orderId: o.id })
    return o.id
  },
  updateOrder: (id: string, patch: Partial<Order>) =>
    patchOrder(id, (o) => ({ ...o, ...patch })),
  addLine(id: string, line: Omit<OrderLine, "id" | "status">) {
    patchOrder(id, (o) => {
      const same = o.lines.find(
        (l) =>
          l.status === "Pending" &&
          l.itemId === line.itemId &&
          l.variant === line.variant &&
          !l.note &&
          !line.note &&
          !l.discount &&
          JSON.stringify(l.modifiers) === JSON.stringify(line.modifiers)
      )
      if (same)
        return {
          ...o,
          lines: o.lines.map((l) =>
            l === same ? { ...l, qty: l.qty + line.qty } : l
          ),
        }
      return {
        ...o,
        lines: [
          ...o.lines,
          { ...line, id: `l-${clock}-${o.lines.length}`, status: "Pending" },
        ],
      }
    })
    const o = state.orders.find((x) => x.id === id)
    if (o?.table) {
      const t = state.tables.find((x) => x.code === o.table)
      if (t && t.state === "Seated") patchTable(o.table, { state: "Ordering" })
    }
  },
  setQty: (id: string, lineId: string, qty: number) =>
    patchOrder(id, (o) => ({
      ...o,
      lines:
        qty <= 0
          ? o.lines.filter((l) => l.id !== lineId)
          : o.lines.map((l) => (l.id === lineId ? { ...l, qty } : l)),
    })),
  setLine: (id: string, lineId: string, patch: Partial<OrderLine>) =>
    patchOrder(id, (o) => ({
      ...o,
      lines: o.lines.map((l) => (l.id === lineId ? { ...l, ...patch } : l)),
    })),
  setDiscount: (id: string, discount?: Discount) =>
    patchOrder(id, (o) =>
      log(
        { ...o, discount },
        discount
          ? `Order discount applied (${discount.reason})`
          : "Order discount removed"
      )
    ),

  send(id: string) {
    let sent = 0
    patchOrder(id, (o) => {
      const lines = o.lines.map((l) => {
        if (l.status !== "Pending") return l
        sent += l.qty
        return {
          ...l,
          status: (l.station === "None" ? "Ready" : "Sent") as ItemStatus,
          sentAt: clock,
        }
      })
      return log(
        { ...o, lines, status: "Open", held: undefined },
        `${sent} item(s) sent to kitchen`
      )
    })
    const o = state.orders.find((x) => x.id === id)
    if (o?.table) patchTable(o.table, { state: "Ordering", orderId: id })
    return sent
  },
  hold: (id: string, label: string) =>
    patchOrder(id, (o) => log({ ...o, held: label }, `Held as “${label}”`)),
  resume: (id: string) =>
    patchOrder(id, (o) => log({ ...o, held: undefined }, "Resumed")),
  printBill(id: string) {
    patchOrder(id, (o) => log({ ...o, billPrinted: true }, "Bill printed"))
    const o = state.orders.find((x) => x.id === id)
    if (o?.table) patchTable(o.table, { state: "Awaiting Payment" })
  },
  setSplits: (id: string, splits?: BillSplit[]) =>
    patchOrder(id, (o) =>
      log(
        { ...o, splits },
        splits ? `Bill split into ${splits.length}` : "Split removed"
      )
    ),
  addPayment(id: string, p: Omit<Payment, "id" | "time" | "session">) {
    patchOrder(id, (o) =>
      log(
        {
          ...o,
          payments: [
            ...o.payments,
            {
              ...p,
              id: `p-${clock}-${o.payments.length}`,
              time: stamp(),
              session: "CS-0412",
            },
          ],
        },
        `Payment ${p.method} recorded`
      )
    )
    const o = state.orders.find((x) => x.id === id)!
    const t = calcBill(o)
    if (t.balance === 0 && !o.receiptNo) {
      const r = state.receiptSeq + 1
      set({ receiptSeq: r })
      patchOrder(id, (x) =>
        log({ ...x, receiptNo: `R-2026-${r}` }, `Receipt R-2026-${r} issued`)
      )
    }
    settle(id)
  },
  cancelOrder(id: string, reason: string) {
    const o = state.orders.find((x) => x.id === id)
    patchOrder(id, (x) =>
      log(
        {
          ...x,
          status: "Cancelled",
          lines: x.lines.map((l) => ({
            ...l,
            status: "Cancelled",
            voidReason: reason,
          })),
        },
        `Order cancelled: ${reason}`
      )
    )
    if (o?.table) patchTable(o.table, { state: "Cleaning", orderId: undefined })
  },
  voidLine(id: string, lineId: string, reason: string, voidType: VoidType) {
    patchOrder(id, (o) =>
      log(
        {
          ...o,
          lines: o.lines.map((l) =>
            l.id === lineId
              ? {
                  ...l,
                  status: "Cancelled",
                  voidReason: reason,
                  voidType,
                  modified: true,
                }
              : l
          ),
        },
        `Item voided: ${reason}`
      )
    )
  },

  setLineStatus(id: string, lineId: string, status: ItemStatus) {
    const patch: Partial<OrderLine> = { status }
    if (status === "In Preparation") patch.startedAt = clock
    if (status === "Ready") patch.readyAt = clock
    patchOrder(id, (o) => ({
      ...o,
      lines: o.lines.map((l) => (l.id === lineId ? { ...l, ...patch } : l)),
    }))
    settle(id)
  },
  bump(id: string, station: Station) {
    const before = state.orders.find((x) => x.id === id)
    patchOrder(id, (o) =>
      log(
        {
          ...o,
          lines: o.lines.map((l) =>
            l.station === station &&
            (l.status === "Sent" || l.status === "In Preparation")
              ? {
                  ...l,
                  status: "Ready",
                  readyAt: clock,
                  startedAt: l.startedAt ?? clock,
                }
              : l
          ),
        },
        `${station} ticket bumped`
      )
    )
    set((s) => ({
      recalled: [{ orderId: id, station }, ...s.recalled].slice(0, 20),
    }))
    if (before)
      notice({
        title: `Order ${before.no} ready`,
        body: `${station} items are ready for ${before.table ? `table ${before.table}` : (before.pickup ?? "pickup")}.`,
        kind: "Kitchen",
        href: `/orders/${id}`,
      })
  },
  startTicket(id: string, station: Station) {
    patchOrder(id, (o) => ({
      ...o,
      lines: o.lines.map((l) =>
        l.station === station && l.status === "Sent"
          ? { ...l, status: "In Preparation", startedAt: clock }
          : l
      ),
    }))
  },
  recall() {
    const last = state.recalled[0]
    if (!last) return undefined
    patchOrder(last.orderId, (o) =>
      log(
        {
          ...o,
          lines: o.lines.map((l) =>
            l.station === last.station && l.status === "Ready"
              ? { ...l, status: "In Preparation", readyAt: undefined }
              : l
          ),
        },
        `${last.station} ticket recalled`
      )
    )
    set((s) => ({ recalled: s.recalled.slice(1) }))
    return last
  },
  toggleRush: (id: string, station: Station) =>
    patchOrder(id, (o) => {
      const rush = o.rush ?? []
      return {
        ...o,
        rush: rush.includes(station)
          ? rush.filter((r) => r !== station)
          : [...rush, station],
      }
    }),
  serveAll(id: string) {
    patchOrder(id, (o) =>
      log(
        {
          ...o,
          lines: o.lines.map((l) =>
            l.status === "Ready"
              ? { ...l, status: o.type === "DINE_IN" ? "Served" : "Collected" }
              : l
          ),
        },
        o.type === "DINE_IN" ? "Items served" : "Items collected"
      )
    )
    settle(id)
    const o = state.orders.find((x) => x.id === id)
    if (o?.table && o.status === "Open" && kitchenStatus(o) === "Served")
      patchTable(o.table, { state: "Served" })
  },

  seat(code: string, guests: number, server: string) {
    patchTable(code, {
      state: "Seated",
      guests,
      server,
      seatedAt: clock,
      upcoming: undefined,
    })
  },
  setTableState: (code: string, st: TableState) =>
    patchTable(
      code,
      st === "Available"
        ? {
            state: st,
            guests: 0,
            server: undefined,
            seatedAt: undefined,
            orderId: undefined,
            flagged: false,
          }
        : { state: st }
    ),
  setOutOfService: (code: string, reason?: string) =>
    patchTable(code, { outOfService: reason }),
  clearFlag: (code: string) =>
    patchTable(code, { flagged: false, orderId: undefined }),
  transferTable(from: string, to: string) {
    const f = state.tables.find((t) => t.code === from)
    if (!f) return
    patchTable(to, {
      state: f.state,
      guests: f.guests,
      server: f.server,
      seatedAt: f.seatedAt,
      orderId: f.orderId,
    })
    patchTable(from, {
      state: "Cleaning",
      guests: 0,
      server: undefined,
      seatedAt: undefined,
      orderId: undefined,
    })
    if (f.orderId)
      patchOrder(f.orderId, (o) =>
        log({ ...o, table: to }, `Transferred ${from} → ${to}`)
      )
  },
  combineTables(codes: string[]) {
    const group = codes.join("+")
    set((s) => ({
      tables: s.tables.map((t) =>
        codes.includes(t.code) ? { ...t, group } : t
      ),
    }))
  },
  splitGroup: (group: string) =>
    set((s) => ({
      tables: s.tables.map((t) =>
        t.group === group ? { ...t, group: undefined } : t
      ),
    })),
  saveTable: (t: FloorTable) =>
    set((s) => ({
      tables: s.tables.some((x) => x.id === t.id)
        ? s.tables.map((x) => (x.id === t.id ? t : x))
        : [...s.tables, t],
    })),
  removeTable: (id: string) =>
    set((s) => ({ tables: s.tables.filter((t) => t.id !== id) })),

  saveMenu: (m: MenuItem) =>
    set((s) => ({
      menu: s.menu.some((x) => x.id === m.id)
        ? s.menu.map((x) => (x.id === m.id ? m : x))
        : [m, ...s.menu],
    })),
  setAvailable(id: string, available: boolean) {
    set((s) => ({
      menu: s.menu.map((m) => (m.id === id ? { ...m, available } : m)),
    }))
  },

  markRead: (id: string) =>
    set((s) => ({
      notices: s.notices.map((n) => (n.id === id ? { ...n, read: true } : n)),
    })),
  markAllRead: () =>
    set((s) => ({ notices: s.notices.map((n) => ({ ...n, read: true })) })),

  saveReservation: (r: Reservation) =>
    set((s) => ({
      reservations: s.reservations.some((x) => x.id === r.id)
        ? s.reservations.map((x) => (x.id === r.id ? r : x))
        : [...s.reservations, r],
    })),
  setReservationStatus: (id: string, status: Reservation["status"]) =>
    set((s) => ({
      reservations: s.reservations.map((r) =>
        r.id === id ? { ...r, status } : r
      ),
    })),
  addWait: (w: WaitParty) => set((s) => ({ waitlist: [...s.waitlist, w] })),
  setWait: (id: string, status: WaitParty["status"]) =>
    set((s) => ({
      waitlist: s.waitlist.map((w) => (w.id === id ? { ...w, status } : w)),
    })),

  setDelivery: (id: string, status: DeliveryStatus, rider?: string) =>
    patchOrder(id, (o) =>
      log(
        {
          ...o,
          delivery: o.delivery && {
            ...o.delivery,
            status,
            rider: rider ?? o.delivery.rider,
          },
        },
        `Delivery: ${status}`
      )
    ),
  acceptOnline(id: string) {
    patchOrder(id, (o) =>
      log({ ...o, onlineState: "Accepted" }, "Online order accepted")
    )
    rms.send(id)
  },
  rejectOnline: (id: string, reason: string) =>
    patchOrder(id, (o) =>
      log(
        { ...o, onlineState: "Rejected", status: "Cancelled" },
        `Online order rejected: ${reason}`
      )
    ),

  openSession(s: Pick<CashierSession, "floatUSD" | "floatKHR">) {
    const id = `CS-0${413 + state.sessions.length}`
    set((st) => ({
      sessions: [
        {
          id,
          cashier: st.userName,
          branch: st.branch,
          terminal: "POS-1",
          opened: `${BUSINESS_DATE} ${stamp()}`,
          salesUSD: 0,
          salesKHR: 0,
          refundsUSD: 0,
          status: "Open",
          movements: [],
          ...s,
        },
        ...st.sessions,
      ],
    }))
  },
  addMovement: (id: string, m: Omit<CashMovement, "id" | "time">) =>
    set((s) => ({
      sessions: s.sessions.map((x) =>
        x.id === id
          ? {
              ...x,
              movements: [
                ...x.movements,
                {
                  ...m,
                  id: `m${x.movements.length + 1}-${clock}`,
                  time: stamp(),
                },
              ],
            }
          : x
      ),
    })),
  closeSession: (id: string, patch: Partial<CashierSession>) =>
    set((s) => ({
      sessions: s.sessions.map((x) =>
        x.id === id
          ? { ...x, closed: `${BUSINESS_DATE} ${stamp()}`, ...patch }
          : x
      ),
    })),
  updateSession: (id: string, patch: Partial<CashierSession>) =>
    set((s) => ({
      sessions: s.sessions.map((x) => (x.id === id ? { ...x, ...patch } : x)),
    })),

  // ---- API sync (lib/api/pos.ts): the backend is the source of truth for menu, tables and orders.
  /** Replace categories, modifier groups and menu items. The exported arrays are refilled in place so every import sees them. */
  loadCatalog(cats: Category[], groups: ModifierGroup[], menu: MenuItem[]) {
    seedCategories.splice(0, seedCategories.length, ...cats)
    modifierGroups.splice(0, modifierGroups.length, ...groups)
    set({ menu })
  },
  loadTables: (tables: FloorTable[]) => set({ tables }),
  loadSessions: (sessions: CashierSession[]) => set({ sessions }),
  loadNotices: (notices: Notice[]) => set({ notices }),
  /** Replace the signed-in user's open session (from the API), keeping other loaded sessions and dropping demo ones. */
  setOwnSession: (own?: CashierSession) =>
    set((s) => ({
      sessions: [
        ...(own ? [own] : []),
        ...s.sessions.filter((x) => x.mine === false || (x.mine && x.status !== "Open" && x.id !== own?.id)),
      ],
    })),
  loadOrders: (orders: Order[]) =>
    set((s) => ({
      orders: orders.map((o) => {
        const old = s.orders.find((x) => x.id === o.id)
        return old ? { ...o, payments: o.payments.length ? o.payments : old.payments, rush: o.rush ?? old.rush, splits: o.splits ?? old.splits, receiptNo: o.receiptNo ?? old.receiptNo, billPrinted: o.billPrinted ?? old.billPrinted } : o
      }),
    })),
  upsertOrder: (o: Order) =>
    set((s) => {
      const old = s.orders.find((x) => x.id === o.id)
      const merged = old ? { ...o, payments: o.payments.length ? o.payments : old.payments, rush: o.rush ?? old.rush, splits: o.splits ?? old.splits, receiptNo: o.receiptNo ?? old.receiptNo, billPrinted: o.billPrinted ?? old.billPrinted } : o
      return { orders: old ? s.orders.map((x) => (x.id === o.id ? merged : x)) : [merged, ...s.orders] }
    }),
  /** Set or clear the rush flag of one station on an order (from the ticket priority). */
  markRush: (id: string, station: Station, on: boolean) =>
    patchOrder(id, (o) => {
      const rush = (o.rush ?? []).filter((r) => r !== station)
      return { ...o, rush: on ? [...rush, station] : rush }
    }),
  addLocalPayment: (orderId: string, p: Payment) =>
    patchOrder(orderId, (o) => ({ ...o, payments: [...o.payments.filter((x) => x.id !== p.id), p] })),
}

export { modifierGroups, seedCategories as categories }

export function expectedCash(s: CashierSession) {
  const mv = (cur: "USD" | "KHR") =>
    s.movements
      .filter((m) => m.currency === cur)
      .reduce(
        (sum, m) => sum + (m.kind === "Paid-in" ? m.amount : -m.amount),
        0
      )
  return {
    usd: s.floatUSD + s.salesUSD - s.refundsUSD + mv("USD"),
    khr: s.floatKHR + s.salesKHR + mv("KHR"),
  }
}

export interface Ticket {
  order: Order
  station: Station
  lines: OrderLine[]
  age: number
  rush: boolean
}

export function ticketsFor(
  orders: Order[],
  at: number,
  station?: Station
): Ticket[] {
  const out: Ticket[] = []
  for (const order of orders) {
    if (order.status !== "Open") continue
    const stations = [
      ...new Set(
        order.lines.filter((l) => l.station !== "None").map((l) => l.station)
      ),
    ]
    for (const st of stations) {
      if (station && st !== station) continue
      const lines = order.lines.filter(
        (l) =>
          l.station === st &&
          (l.sentAt !== undefined || l.status === "Cancelled")
      )
      if (
        !lines.some((l) => l.status === "Sent" || l.status === "In Preparation")
      )
        continue
      const firstSent = Math.min(...lines.map((l) => l.sentAt ?? at))
      out.push({
        order,
        station: st,
        lines,
        age: at - firstSent,
        rush: order.rush?.includes(st) ?? false,
      })
    }
  }
  return out.sort((a, b) => Number(b.rush) - Number(a.rush) || b.age - a.age)
}
