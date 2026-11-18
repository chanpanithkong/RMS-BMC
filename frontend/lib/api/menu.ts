/** Menu administration (SRS §6.4): items, variants and prices, categories, modifier groups, availability. */
import { api } from "./client"
import { num, when } from "./use-api"

export const STATION_NAME: Record<string, string> = { HOT: "Hot", COLD: "Cold", BEV: "Beverage", DESSERT: "Dessert", BAR: "Bar" }

export interface ApiVariant {
  id: string
  name_en: string
  name_km: string | null
  portion_factor: string
  is_active: boolean
  price: string | null
}
export interface ApiGroup {
  id: string
  name_en: string
  name_km: string | null
  min_select: number
  max_select: number
  is_active: boolean
  modifiers: { id: string; name_en: string; name_km: string | null; price_delta: string; is_active: boolean }[]
}
export interface ApiItem {
  id: string
  code: string
  name_en: string
  name_km: string | null
  description: string | null
  category_id: string
  category_name_en: string
  item_type: string
  station_code: string | null
  tax_profile_id: string
  barcode: string | null
  channels: string[]
  is_active: boolean
  version: number
  available: boolean
  unavailable_reason: string | null
  variants: ApiVariant[]
  modifier_groups: ApiGroup[]
  combo_slots?: ApiComboSlot[]
}
export interface ApiComboSlot {
  id: string
  name_en: string
  name_km: string | null
  min_select: number
  max_select: number
  options: { id: string; variant_id: string; menu_item_id: string; item_name_en: string; variant_name: string; price_delta: string; available: boolean }[]
}
export interface ApiCategory {
  id: string
  name_en: string
  name_km: string | null
  sort_order: number
  is_active: boolean
}

/** Row shape for the menu tables. */
export interface ItemRow {
  id: string
  code: string
  name: string
  km: string
  category: string
  categoryId: string
  station: string
  type: string
  price: number
  available: boolean
  active: boolean
  channels: string[]
  raw: ApiItem
}

export const toItemRow = (i: ApiItem): ItemRow => {
  const priced = i.variants.find((v) => v.is_active && v.price !== null)
  return {
    id: i.id,
    code: i.code,
    name: i.name_en,
    km: i.name_km ?? "",
    category: i.category_name_en,
    categoryId: i.category_id,
    station: i.station_code ? (STATION_NAME[i.station_code] ?? i.station_code) : "None",
    type: i.item_type,
    price: num(priced?.price),
    available: i.available,
    active: i.is_active,
    channels: i.channels,
    raw: i,
  }
}

export async function listItems() {
  const r = await api<{ data: ApiItem[] }>("GET", "/menu-items", { query: { page_size: 200 } })
  return r.data.map(toItemRow)
}
export const getItem = (id: string) => api<ApiItem>("GET", `/menu-items/${id}`)
export const listCategories = () => api<ApiCategory[]>("GET", "/menu-categories")
export const listGroups = () => api<ApiGroup[]>("GET", "/modifier-groups")
export const listTaxProfiles = () => api<{ id: string; code: string; name: string; is_active: boolean }[]>("GET", "/tax-profiles")
export const listStations = () => api<{ id: string; code: string; name: string; is_active: boolean }[]>("GET", "/kitchen/stations")

export const saveCategory = (v: { name_en: string; name_km?: string; sort_order: number; is_active: boolean }, id?: string) =>
  id ? api("PATCH", `/menu-categories/${id}`, { body: v }) : api("POST", "/menu-categories", { body: v })

/** "Mild, Extra egg +0.50" -> modifiers with price deltas. */
export const parseModifiers = (text: string) =>
  text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => {
      const m = s.match(/^(.*?)\s*\+\s*\$?\s*([\d.]+)$/)
      return m ? { name_en: m[1].trim(), price_delta: m[2] } : { name_en: s, price_delta: "0" }
    })

export const createGroup = (v: { name_en: string; name_km?: string; min_select: number; max_select: number; modifiers: { name_en: string; price_delta: string }[] }) =>
  api("POST", "/modifier-groups", { body: v })

export const setAvailability = (id: string, available: boolean) =>
  api("POST", `/menu-items/${id}/availability`, { body: { available } })
export const deactivateItem = (id: string) => api("DELETE", `/menu-items/${id}`)
export const updateItem = (id: string, patch: Record<string, unknown>) => api<ApiItem>("PATCH", `/menu-items/${id}`, { body: patch })
export const createItem = (body: Record<string, unknown>) => api<ApiItem>("POST", "/menu-items", { body })
export const attachGroups = (id: string, groupIds: string[]) => api("PUT", `/menu-items/${id}/modifier-groups`, { body: { group_ids: groupIds } })
/** New price for a variant, effective now (earlier prices stay in history, BR-048). */
export const addPrice = (itemId: string, variantId: string, price: number) =>
  api("POST", `/menu-items/${itemId}/prices`, { body: { variant_id: variantId, price: String(price), valid_from: new Date().toISOString() } })

export async function priceHistory(item: ApiItem) {
  const rows = await api<{ id: string; variant_id: string; price: string; valid_from: string | null; valid_to: string | null; created_at: string }[]>(
    "GET",
    `/menu-items/${item.id}/price-history`
  )
  const vname = Object.fromEntries(item.variants.map((v) => [v.id, v.name_en]))
  return rows.map((r) => ({
    id: r.id,
    variant: vname[r.variant_id] ?? "",
    price: num(r.price),
    from: when(r.valid_from),
    to: when(r.valid_to) || "—",
    created: when(r.created_at),
  }))
}

/** FR-MENU-005: replace a combo's slots. Orders already placed keep the items they were sold with. */
export const saveComboSlots = (
  itemId: string,
  slots: { name_en: string; min_select: number; max_select: number; options: { variant_id: string; price_delta: string }[] }[]
) => api<ApiComboSlot[]>("PUT", `/menu-items/${itemId}/combo-slots`, { body: { slots } })
