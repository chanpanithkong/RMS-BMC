/** Inventory (SRS §6.7): ingredients, balances, movements, documents, counts, transfers. Stock only changes by posting. */
import { api } from "./client"
import { num, when } from "./use-api"

export interface Unit {
  id: string
  code: string
  name: string
  dimension: string
}
export interface Location {
  id: string
  name: string
  is_active: boolean
}
export interface Ingredient {
  id: string
  code: string
  name_en: string
  name_km: string | null
  category: string
  stock_uom_id: string
  reorder_level: string
  reorder_qty: string
  track_batch: boolean
  track_expiry: boolean
  is_active: boolean
  /** Where sales take this ingredient from; null = the branch's first location by name. */
  default_location_id: string | null
}
export interface Balance {
  location_id: string
  location_name: string
  ingredient_id: string
  ingredient_code: string
  ingredient_name_en: string
  unit: string
  quantity: string
  avg_cost: string
  value: string
  reorder_level: string
  low: boolean
}
export interface CountSheet {
  id: string
  count_no: string
  location_id: string
  status: string
  progress: string
  created_at?: string
  submitted_at?: string | null
  posted_at?: string | null
  lines: {
    ingredient_id: string
    ingredient: string
    unit: string
    counted_qty: string | null
    system_qty?: string | null
    variance?: string | null
    variance_value?: string | null
  }[]
}
export interface StockDoc {
  id: string
  doc_no: string
  doc_type: string
  location_id: string
  status: string
  reason: string | null
  total_value: string
  posted_at: string | null
  created_at: string | null
  lines: { id: string; ingredient_id: string; quantity: string; uom_id: string; unit_cost: string | null }[]
}

export const units = () => api<Unit[]>("GET", "/inventory/units")
export const locations = () => api<Location[]>("GET", "/inventory/locations")
export const ingredients = () => api<Ingredient[]>("GET", "/inventory/items")
export const balances = () => api<Balance[]>("GET", "/inventory/balances")
export const expiring = () =>
  api<{ batch_no: string; ingredient: string; location: string; expiry_date: string; quantity_received: string; expired: boolean }[]>("GET", "/inventory/expiring")
export const counts = () => api<CountSheet[]>("GET", "/inventory/counts")
export const getCount = (id: string) => api<CountSheet>("GET", `/inventory/counts/${id}`)
export const documents = (docType?: string) => api<StockDoc[]>("GET", "/inventory/documents", { query: { doc_type: docType } })
export const transfers = () =>
  api<{ id: string; transfer_no: string; from_location_id: string; to_location_id: string; status: string; created_at: string; lines: { ingredient_id: string; quantity: string; uom_id: string }[] }[]>(
    "GET",
    "/inventory/transfers"
  )

export async function movements() {
  const r = await api<{
    data: { id: string; posted_at: string; location_id: string; ingredient_id: string; txn_type: string; quantity: string; unit_cost: string; total_cost: string; balance_after: string; source_type: string; reverses_txn_id: string | null; reason: string | null }[]
  }>("GET", "/inventory/transactions", { query: { page_size: 200 } })
  return r.data
}

export const saveIngredient = (v: Record<string, unknown>, id?: string) =>
  id ? api("PATCH", `/inventory/items/${id}`, { body: v }) : api("POST", "/inventory/items", { body: v })

/** Draft then post a stock document. Above the user's threshold it waits for approval instead (BR-019). */
export async function postDocument(v: { doc_type: string; location_id: string; reason?: string; lines: { ingredient_id: string; quantity: string; uom_id: string; unit_cost?: string }[] }) {
  const d = await api<StockDoc>("POST", "/inventory/documents", { body: v })
  return api<StockDoc>("POST", `/inventory/documents/${d.id}/post`)
}
export const decideDocument = (id: string, approve: boolean) => api("POST", `/inventory/documents/${id}/decision`, { body: { approve } })
export const reverseTxn = (id: string, reason: string) => api("POST", `/inventory/transactions/${id}/reverse`, { body: { reason } })
export const startCount = (locationId: string) => api<CountSheet>("POST", "/inventory/counts", { body: { location_id: locationId } })
export const enterCounts = (id: string, lines: { ingredient_id: string; quantity: string; uom_id: string }[]) =>
  api<CountSheet>("PUT", `/inventory/counts/${id}/lines`, { body: { lines } })
export const submitCount = (id: string) => api<CountSheet>("POST", `/inventory/counts/${id}/submit`)
export const decideCount = (id: string, approve: boolean) => api<CountSheet>("POST", `/inventory/counts/${id}/decision`, { body: { approve } })
export const transfer = (v: { from_location_id: string; to_location_id: string; lines: { ingredient_id: string; quantity: string; uom_id: string }[] }) =>
  api("POST", "/inventory/transfers", { body: v })
export const menuWastage = (variantId: string, quantity: number, reason: string) =>
  api("POST", "/inventory/menu-wastage", { body: { variant_id: variantId, quantity: String(quantity), reason } })
export const requestsFromLowStock = () => api<{ id: string; request_no: string; lines: number }>("POST", "/purchase-requests/from-low-stock")

export const qty = (v: string | number | null | undefined, unit = "") => `${Number(num(v).toFixed(3))}${unit ? ` ${unit}` : ""}`
export { when }
