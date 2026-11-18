/**
 * Public online and QR ordering (SRS §6.18): no staff sign-in. The server prices every cart (quote) and
 * checks the total again at checkout (PRICE_CHANGED). Customer accounts sign in by a text-message code and
 * send an X-Customer-Token header; the token is kept in this browser tab's session storage, never in a URL.
 */
import { api, newIdempotencyKey } from "./client"
import type { Category, ComboPick, MenuItem, ModifierGroup } from "@/lib/rms/types"
import { comboOf } from "./pos"
import { rms } from "@/lib/rms/store"

export interface PublicItem {
  id: string
  code: string
  name_en: string
  name_km: string | null
  description: string | null
  category_id: string
  category_name_en: string
  modifier_groups: { id: string; name_en: string; name_km: string | null; min_select: number; max_select: number; modifiers: { id: string; name_en: string; price_delta: string; is_active: boolean }[] }[]
  variants: { id: string; name_en: string; price: string | null; is_active: boolean }[]
  combo_slots?: { id: string; name_en: string; min_select: number; max_select: number; options: { variant_id: string; item_name_en: string; variant_name: string; price_delta: string; available: boolean }[] }[]
}
export interface PublicMenu {
  branch: { code: string; name_en: string; name_km: string | null; address: string | null; phone: string | null; opening_hours: string | null; open_now: boolean }
  lead_minutes: number | null
  min_order: string | null
  max_qty_per_line: number | null
  /** Checkout choices: KHQR only when a QR payment gateway is configured. */
  payment?: { online: "khqr" | "redirect" | null; pay_later: boolean }
  items: PublicItem[]
}
export interface Totals {
  subtotal: string
  discount_total: string
  service_charge: string
  tax: string
  delivery_fee: string
  total: string
  currency: string
}
export interface CartItem {
  variant_id: string
  quantity: string
  modifiers: { modifier_id: string }[]
  note?: string
  combo?: ComboPick[]
}
export interface Cart {
  fulfilment: "Pickup" | "Delivery"
  name: string
  phone: string
  email?: string
  scheduled_at?: string
  delivery?: { zone_id: string; address: string; landmark?: string }
  promo_code?: string
  note?: string
  items: CartItem[]
}

const TOKEN_KEY = "rms.customer_token"
export const customerToken = () => {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? undefined
  } catch {
    return undefined
  }
}
export const setCustomerToken = (t: string | null) => {
  try {
    if (t) sessionStorage.setItem(TOKEN_KEY, t)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage blocked: the customer stays a guest */
  }
}
const auth = () => ({ "X-Customer-Token": customerToken() })

/** The branch to order from: ?branch=CODE on the link, else the site default. */
export const branchCode = (param: string | null) => (param || process.env.NEXT_PUBLIC_ONLINE_BRANCH || "").trim()

export const menu = (code: string) => api<PublicMenu>("GET", `/public/branches/${code}/menu`)
export const zones = (code: string) =>
  api<{ id: string; name: string; fee: string; free_over: string | null; min_order: string | null; estimated_minutes: number | null }[]>("GET", `/public/branches/${code}/delivery-zones`)
export const quote = (code: string, cart: Cart) =>
  api<{ totals: Totals; lines: { name: string; variant: string; quantity: string; net: string }[] }>("POST", `/public/branches/${code}/quote`, { body: cart })
/** Place the order once: the same key is reused if the customer presses again after a timeout (BR-030). */
export const checkout = (code: string, cart: Cart, expectedTotal: string, key: string, payment: "Online" | "PayLater" = "PayLater") =>
  api<{ order_id: string; order_no: string; status: string; tracking_token: string; totals: Totals }>("POST", `/public/branches/${code}/orders`, {
    body: { ...cart, payment, expected_total: expectedTotal },
    idempotent: key,
    headers: auth(),
  })
export { newIdempotencyKey }

/** KHQR for an order paid online (FR-ONL-007): the QR string, its expiry and the payment state. */
export interface KhqrState {
  payment_status: string
  check?: string | null
  expires_at: string | null
  qr: string | null
  amount: string
  currency: string
}
export const paymentState = (token: string) => api<KhqrState>("GET", `/public/track/${token}/payment`)
export const newKhqr = (token: string) => api<KhqrState>("POST", `/public/track/${token}/payment`)

export const track = (token: string) =>
  api<{
    order_no: string
    status: string
    fulfilment: string | null
    scheduled_at: string | null
    branch: { name_en: string; name_km: string | null; phone: string | null }
    items: { name: string; variant: string; quantity: string; status: string }[]
    totals: Totals
    payment_status: string | null
    reject_reason: string | null
    expires_at: string
  }>("GET", `/public/track/${token}`)

export const requestCode = (code: string, phone: string) => api<{ message?: string }>("POST", `/public/branches/${code}/account/code`, { body: { phone } })
export const verifyCode = (code: string, phone: string, sms: string, name?: string) =>
  api<{ customer_token: string; name: string }>("POST", `/public/branches/${code}/account/verify`, { body: { phone, code: sms, name } })
export const account = () => api<{ name: string; phone: string; email: string | null; loyalty_points: number }>("GET", "/public/account", { headers: auth() })
export const myOrders = () =>
  api<{ order_no: string; business_date: string; branch: string; order_type: string; status: string; total: string; items: { name: string; quantity: string }[] }[]>(
    "GET",
    "/public/account/orders",
    { headers: auth() }
  )
export const signOutCustomer = () => api("POST", "/public/account/sign-out", { headers: auth() }).finally(() => setCustomerToken(null))

export const qrMenu = (token: string) => api<PublicMenu & { table: string; staff_confirmation: boolean }>("GET", `/public/qr/${token}`)
export const qrOrder = (token: string, items: CartItem[], guests?: number, note?: string, key?: string) =>
  api<{ order_no: string; status: string }>("POST", `/public/qr/${token}/orders`, { body: { items, guest_count: guests, note }, idempotent: key ?? true })

/** Put the public menu into the shared store, so the item-options dialog works as on the POS. */
export function loadPublicMenu(m: PublicMenu) {
  const cats = new Map<string, Category>()
  const groups = new Map<string, ModifierGroup>()
  const items: MenuItem[] = m.items.map((i, n) => {
    if (!cats.has(i.category_id)) cats.set(i.category_id, { id: i.category_id, name: i.category_name_en, km: "", order: n, active: true })
    for (const g of i.modifier_groups)
      groups.set(g.id, {
        id: g.id,
        name: g.name_en,
        km: g.name_km ?? "",
        min: g.min_select,
        max: g.max_select,
        modifiers: g.modifiers.filter((x) => x.is_active).map((x) => ({ id: x.id, name: x.name_en, delta: Number(x.price_delta) })),
      })
    const several = i.variants.length > 1 || (i.variants[0] && i.variants[0].name_en !== "Regular")
    return {
      id: i.id,
      code: i.code,
      name: i.name_en,
      km: i.name_km ?? "",
      cat: i.category_id,
      station: "None",
      price: Number(i.variants[0]?.price ?? 0),
      type: "Food",
      variants: several ? i.variants.map((v) => ({ name: v.name_en, price: Number(v.price) })) : undefined,
      groups: i.modifier_groups.map((g) => g.id),
      available: true,
      active: true,
      tax: "",
      desc: i.description ?? "",
      channels: ["Online"],
      variantIds: Object.fromEntries(i.variants.map((v) => [v.name_en, v.id])),
      combo: comboOf(i.combo_slots),
    }
  })
  rms.loadCatalog([...cats.values()], [...groups.values()], items)
  return items
}
