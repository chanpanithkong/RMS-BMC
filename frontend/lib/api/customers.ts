/** Customers, loyalty and credit accounts (SRS §6.11, §6.22). Contact details come back masked without customers.contact.view. */
import { api } from "./client"

export interface Customer {
  id: string
  code: string
  name: string
  phone: string | null
  email: string | null
  contact_masked: boolean
  preferred_language: string
  classification: string
  preferences: string | null
  allergy_notes: string | null
  consent_marketing: boolean
  no_show_count: number
  loyalty_points: number
  anonymised: boolean
  addresses: { id: string; label: string; address: string; landmark: string | null }[]
  version: number
  visits?: number
  total_spend?: string
  last_visit?: string | null
}
export interface CreditAccount {
  id: string
  account_no: string
  customer_id: string
  customer_name: string | null
  company_name: string | null
  billing_contact: string | null
  credit_limit: string
  terms_days: number
  balance: string
  available: string
  overdue: string
  status: string
  notes: string | null
}
export interface Loyalty {
  balance: number
  redeemable_points: number
  redeemable_value: string
  expiring_within_30_days: number
  next_expiry: string | null
  history: { kind: string; points: number; remaining: number | null; expires_at: string | null; order_id: string | null; value: string | null; reason: string | null; created_at: string }[]
}

export const list = async (q?: string) => (await api<{ data: Customer[] }>("GET", "/customers", { query: { q: q || undefined, page_size: 200 } })).data
export const get = (id: string) => api<Customer>("GET", `/customers/${id}`)
export const create = (v: Record<string, unknown>, force = false) => api<Customer>("POST", "/customers", { body: v, query: { force: force || undefined } })
export const update = (id: string, v: Record<string, unknown>) => api<Customer>("PATCH", `/customers/${id}`, { body: v })
export const merge = (keepId: string, mergeId: string) => api<Customer>("POST", "/customers/merge", { body: { keep_id: keepId, merge_id: mergeId } })
export const anonymise = (id: string, reason: string) => api<Customer>("POST", `/customers/${id}/anonymise`, { body: { reason } })
export const orders = async (id: string) =>
  (
    await api<{ data: { id: string; order_no: string; business_date: string; order_type: string; order_status: string; grand_total: string }[] }>(
      "GET",
      `/customers/${id}/orders`,
      { query: { page_size: 200 } }
    )
  ).data
export const loyalty = (id: string) => api<Loyalty>("GET", `/customers/${id}/loyalty`)
export const adjustPoints = (id: string, points: number, reason: string) => api<Loyalty>("POST", `/customers/${id}/loyalty/adjust`, { body: { points, reason } })

export const accounts = () => api<CreditAccount[]>("GET", "/credit-accounts")
export const openAccount = (v: Record<string, unknown>) => api<CreditAccount>("POST", "/credit-accounts", { body: v })
export const updateAccount = (id: string, v: Record<string, unknown>) => api<CreditAccount>("PATCH", `/credit-accounts/${id}`, { body: v })
export const settle = (id: string, v: { amount: string; method: string; reference?: string }) => api("POST", `/credit-accounts/${id}/settlements`, { body: v })
export const statement = (id: string) => api<Record<string, unknown>>("GET", `/credit-accounts/${id}/statement`)
