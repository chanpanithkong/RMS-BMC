// Client stand-in for the backend calculation engine (BR-008, BR-033, BR-034).
// In production these totals must come from the API; the POS never submits them.
import type { Discount, Order, OrderLine } from "./types"

/** Illustrative values only, pending verification V-01, D-03 in the SRS. */
export const billing = {
  serviceRate: 0.05,
  taxRate: 0.1,
  usdKhr: 4100,
  khrIncrement: 100,
}

export const round2 = (n: number) =>
  Math.round((n + Number.EPSILON) * 100) / 100
export const roundKhr = (khr: number) =>
  Math.round(khr / billing.khrIncrement) * billing.khrIncrement

export const lineUnit = (l: Pick<OrderLine, "unitPrice" | "modifiers">) =>
  l.unitPrice + l.modifiers.reduce((s, m) => s + m.delta, 0)
export const lineGross = (l: OrderLine) => round2(lineUnit(l) * l.qty)

export function discountValue(d: Discount | undefined, base: number) {
  if (!d) return 0
  const v = d.kind === "percent" ? (base * d.value) / 100 : d.value
  return round2(Math.min(v, base))
}

export interface BillTotals {
  gross: number
  itemDiscounts: number
  orderDiscount: number
  subtotal: number
  service: number
  tax: number
  deliveryFee: number
  total: number
  paid: number
  balance: number
}

export function calcBill(
  order: Pick<Order, "lines" | "discount" | "type" | "payments" | "delivery"> & { apiTotals?: Order["apiTotals"] }
): BillTotals {
  // Orders loaded from the API carry the backend's own totals; those always win.
  if (order.apiTotals) return order.apiTotals
  const lines = order.lines.filter((l) => l.status !== "Cancelled")
  const gross = round2(lines.reduce((s, l) => s + lineGross(l), 0))
  const itemDiscounts = round2(
    lines.reduce((s, l) => s + discountValue(l.discount, lineGross(l)), 0)
  )
  const orderDiscount = discountValue(order.discount, gross - itemDiscounts)
  const subtotal = round2(gross - itemDiscounts - orderDiscount)
  const service =
    order.type === "DINE_IN" ? round2(subtotal * billing.serviceRate) : 0
  const tax = round2((subtotal + service) * billing.taxRate)
  const deliveryFee = order.delivery?.fee ?? 0
  const total = round2(subtotal + service + tax + deliveryFee)
  const paid = round2(
    order.payments
      .filter((p) => p.state === "Confirmed")
      .reduce((s, p) => s + p.applied, 0)
  )
  return {
    gross,
    itemDiscounts,
    orderDiscount,
    subtotal,
    service,
    tax,
    deliveryFee,
    total,
    paid,
    balance: round2(Math.max(total - paid, 0)),
  }
}

export function paymentStatus(order: Order) {
  const { total, paid } = calcBill(order)
  if (total > 0 && paid >= total) return "Paid"
  return paid > 0 ? "Partially Paid" : "Unpaid"
}

export function kitchenStatus(order: Order) {
  const lines = order.lines.filter((l) => l.status !== "Cancelled")
  if (!lines.length || lines.every((l) => l.status === "Pending"))
    return "Not Sent"
  if (lines.every((l) => l.status === "Served" || l.status === "Collected"))
    return "Served"
  if (
    lines.every(
      (l) =>
        l.status !== "Pending" &&
        l.status !== "Sent" &&
        l.status !== "In Preparation"
    )
  )
    return "Ready"
  return "In Progress"
}

export interface Tender {
  method: "cash"
  currency: "USD" | "KHR"
  tendered: number
  balance: number
  changeCurrency: "USD" | "KHR"
}

/** Applied amount (USD base) and change for a cash tender. */
export function cashResult({
  currency,
  tendered,
  balance,
  changeCurrency,
}: Tender) {
  const dueKhr = roundKhr(balance * billing.usdKhr)
  const covered = currency === "USD" ? tendered >= balance : tendered >= dueKhr
  const applied = covered
    ? balance
    : round2(currency === "USD" ? tendered : tendered / billing.usdKhr)
  let change = 0
  if (covered) {
    const overKhr =
      currency === "KHR"
        ? tendered - dueKhr
        : (tendered - balance) * billing.usdKhr
    change =
      changeCurrency === "KHR"
        ? roundKhr(overKhr)
        : round2(overKhr / billing.usdKhr)
  }
  const rounding =
    covered && currency === "KHR"
      ? dueKhr - Math.round(balance * billing.usdKhr)
      : 0
  return { applied, change, covered, dueKhr, rounding }
}

export const usd = (n: number) =>
  `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
export const khr = (n: number) => `៛${Math.round(n).toLocaleString("en-US")}`
export const toKhr = (usdValue: number) => roundKhr(usdValue * billing.usdKhr)
