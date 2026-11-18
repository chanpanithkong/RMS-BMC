/** Bills, payments, receipts and refunds for the back office (SRS §6.9). All money comes from the server. */
import { api } from "./client"

export interface PaymentRow {
  id: string
  time: string
  method: string
  currency: "USD" | "KHR"
  tendered: number
  applied: number
  base: number
  change: number
  changeCurrency: "USD" | "KHR"
  state: string
  billId: string
  billNo: string
  billStatus: string
  receipt: string
}
export interface RefundRow {
  id: string
  refundNo: string
  method: string
  currency: string
  amount: number
  amountBase: number
  reason: string
  status: string
  created: string
}
export interface OrderRow {
  id: string
  no: string
  type: string
  status: string
  payment: string
  where: string
  total: number
  created: string
}

const num = (v: unknown) => (v === null || v === undefined ? 0 : Number(v))
const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "")
const PAYMENT_STATUS: Record<string, string> = { PartiallyPaid: "Partially Paid" }
export const METHOD_LABEL: Record<string, string> = {
  CASH_USD: "Cash USD",
  CASH_KHR: "Cash KHR",
  KHQR: "KHQR",
  BANK_TRANSFER: "Bank Transfer",
  CARD: "Card",
}

interface ApiPayment {
  payment_id: string
  status: string
  method: string
  currency: "USD" | "KHR"
  amount_tendered: string
  amount_applied: string
  amount_base: string
  change: { currency: "USD" | "KHR"; amount: string } | null
  bill: { id: string; bill_no: string; status: string }
  receipt_no: string | null
  created_at: string
}

export async function listPayments(businessDate?: string): Promise<PaymentRow[]> {
  const r = await api<{ data: ApiPayment[] }>("GET", "/payments", { query: { business_date: businessDate, page_size: 200 } })
  return r.data.map((p) => ({
    id: p.payment_id,
    time: when(p.created_at),
    method: METHOD_LABEL[p.method] ?? p.method,
    currency: p.currency,
    tendered: num(p.amount_tendered),
    applied: num(p.amount_applied),
    base: num(p.amount_base),
    change: num(p.change?.amount),
    changeCurrency: p.change?.currency ?? p.currency,
    state: p.status,
    billId: p.bill.id,
    billNo: p.bill.bill_no,
    billStatus: p.bill.status,
    receipt: p.receipt_no ?? "—",
  }))
}

export async function listOrders(businessDate?: string): Promise<OrderRow[]> {
  const r = await api<{
    data: {
      id: string
      order_no: string
      order_type: string
      order_status: string
      payment_status: string
      table_code: string | null
      pickup_name: string | null
      grand_total: string
      created_at: string
    }[]
  }>("GET", "/orders", { query: { business_date: businessDate, page_size: 200 } })
  return r.data
    .filter((o) => o.order_status !== "Draft" && o.order_status !== "Cancelled")
    .map((o) => ({
      id: o.id,
      no: o.order_no,
      type: o.order_type,
      status: o.order_status,
      payment: PAYMENT_STATUS[o.payment_status] ?? o.payment_status,
      where: o.table_code ? `Table ${o.table_code}` : (o.pickup_name ?? "—"),
      total: num(o.grand_total),
      created: when(o.created_at),
    }))
}

export async function listRefunds(): Promise<RefundRow[]> {
  const r = await api<
    { id: string; refund_no: string; method_code: string; currency: string; amount: string; amount_base: string; reason: string; status: string; created_at: string }[]
  >("GET", "/refunds")
  return r.map((x) => ({
    id: x.id,
    refundNo: x.refund_no,
    method: METHOD_LABEL[x.method_code] ?? x.method_code,
    currency: x.currency,
    amount: num(x.amount),
    amountBase: num(x.amount_base),
    reason: x.reason,
    status: x.status,
    created: when(x.created_at),
  }))
}

export const voidPayment = (paymentId: string, reason: string, approvalId?: string) =>
  api("POST", `/payments/${paymentId}/void`, { body: { reason, approval_id: approvalId } })

export const requestRefund = (paymentId: string, amount: number, reason: string) =>
  api("POST", "/refunds", { idempotent: true, body: { payment_id: paymentId, amount: String(amount), reason } })

export const decideRefund = (refundId: string, approve: boolean, note?: string) =>
  api("POST", `/refunds/${refundId}/${approve ? "approve" : "reject"}`, { body: { note } })

export const reprintReceipt = (billId: string) =>
  api<{ receipt_no: string; label: string }>("POST", `/bills/${billId}/receipt/reprint`)
