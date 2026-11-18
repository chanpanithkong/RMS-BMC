/** Purchasing and suppliers (SRS §6.8): requests, purchase orders, goods receipts, returns, invoices. */
import { api } from "./client"

export interface Supplier {
  id: string
  name: string
  contact_person: string
  phone: string
  email: string | null
  address: string | null
  tax_id: string | null
  payment_terms: string
  currency: string
  status: string
  branch_ids: string[]
}
export interface Line {
  ingredient_id: string
  quantity: string
  uom_id: string
}
export interface PurchaseRequest {
  id: string
  request_no: string
  source: string
  status: string
  purchase_order_id: string | null
  lines: Line[]
}
export interface PO {
  id: string
  po_no: string
  supplier_id: string
  location_id: string
  status: string
  delivery_date: string | null
  total: string
  currency: string
  version: number
  lines: { id: string; ingredient_id: string; qty_ordered: string; qty_received: string; uom_id: string; unit_price: string }[]
}
export interface GR {
  id: string
  gr_no: string
  po_id: string | null
  supplier_id: string | null
  location_id: string
  status: string
  is_direct: boolean
  exception_note: string | null
  total_value: string
  posted_at: string | null
  lines: { id: string; po_item_id: string | null; ingredient_id: string; qty_received: string; qty_rejected: string; uom_id: string; unit_cost: string | null }[]
}
export interface Return {
  id: string
  return_no: string
  gr_id: string
  gr_no: string
  supplier_id: string | null
  reason: string
  total_value: string
  created_at: string
  lines: { gr_item_id: string; quantity: string }[]
}
export interface Invoice {
  id: string
  supplier_id: string
  invoice_no: string
  invoice_date: string
  due_date: string
  amount: string
  currency: string
  gr_ids: string[]
  matched_value: string | null
  match_status: string
  status: string
  paid_amount: string
}

export const suppliers = () => api<Supplier[]>("GET", "/suppliers")
export const saveSupplier = (v: Record<string, unknown>, id?: string) =>
  id ? api("PATCH", `/suppliers/${id}`, { body: v }) : api("POST", "/suppliers", { body: v })
export const supplierHistory = (id: string) => api<Record<string, unknown>>("GET", `/suppliers/${id}/history`)

export const requests = () => api<PurchaseRequest[]>("GET", "/purchase-requests")
export const createRequest = (lines: Line[], note?: string) => api("POST", "/purchase-requests", { body: { lines, note } })
export const decideRequest = (id: string, approve: boolean) => api("POST", `/purchase-requests/${id}/${approve ? "approve" : "reject"}`)

export const orders = async () => (await api<{ data: PO[] }>("GET", "/purchase-orders", { query: { page_size: 200 } })).data
export const createPO = (v: { supplier_id: string; location_id: string; delivery_date?: string; request_id?: string; lines: { ingredient_id: string; qty_ordered: string; uom_id: string; unit_price: string }[] }) =>
  api<PO>("POST", "/purchase-orders", { body: v })
export const poAction = (id: string, action: "submit" | "approve" | "send") => api("POST", `/purchase-orders/${id}/${action}`)
export const cancelPO = (id: string, reason: string) => api("POST", `/purchase-orders/${id}/cancel`, { body: { reason } })

export const receipts = () => api<GR[]>("GET", "/goods-receipts")
/** Record what arrived against a PO and post it to stock (BR-018); over tolerance it waits for approval (BR-042). */
export async function receive(po: PO, received: Record<string, number>) {
  const gr = await api<GR>("POST", "/goods-receipts", {
    body: { po_id: po.id, lines: po.lines.filter((l) => received[l.id] > 0).map((l) => ({ po_item_id: l.id, qty_received: String(received[l.id]) })) },
  })
  return api<GR>("POST", `/goods-receipts/${gr.id}/post`)
}
export const postGR = (id: string) => api<GR>("POST", `/goods-receipts/${id}/post`)
export const approveGR = (id: string) => api<GR>("POST", `/goods-receipts/${id}/approve`)

export const returns = () => api<Return[]>("GET", "/purchase-returns")
export const createReturn = (grId: string, reason: string, lines: { gr_item_id: string; quantity: string }[]) =>
  api("POST", "/purchase-returns", { body: { gr_id: grId, reason, lines } })

export const invoices = () => api<Invoice[]>("GET", "/supplier-invoices")
export const createInvoice = (v: { supplier_id: string; invoice_no: string; invoice_date: string; due_date: string; amount: string; gr_ids: string[] }) =>
  api<Invoice>("POST", "/supplier-invoices", { body: v })
export const payInvoice = (id: string, v: { amount: string; method: string; reference?: string }) =>
  api("POST", `/supplier-invoices/${id}/payments`, { body: v })
