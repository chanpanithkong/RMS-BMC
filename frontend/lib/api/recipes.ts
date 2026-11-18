/** Recipes and food cost (SRS §6.6). Costs are calculated by the server from weighted-average ingredient costs. */
import { api } from "./client"
import { num, when } from "./use-api"

export interface ApiLine {
  ingredient_id: string
  quantity: string
  uom_id: string
  prep_loss_pct: string
  cook_loss_pct: string
}
export interface ApiVersion {
  id: string
  version_no: number
  status: string
  effective_from: string | null
  yield_qty: string
  method_text: string | null
  published_at: string | null
  lines: ApiLine[]
}
export interface ApiRecipe {
  id: string
  name: string
  variant_id: string | null
  modifier_id: string | null
  active_version_id: string | null
  versions: ApiVersion[]
}
export interface FoodCost {
  recipe_id: string
  name: string
  version_no?: number
  cost_per_portion: string
  incomplete: boolean
  selling_price_ex_tax?: string | null
  food_cost_pct?: string | null
  gross_margin?: string | null
  target_pct?: string
  above_target?: boolean
  lines: { ingredient_id: string; ingredient: string; gross_qty_stock_unit: string; stock_unit: string; avg_cost: string | null; cost: string; cost_missing: boolean }[]
}
export interface Unit {
  id: string
  code: string
  name: string
  dimension: string
}
export interface Ingredient {
  id: string
  code: string
  name_en: string
  stock_uom_id: string
  is_active: boolean
}

export const listRecipes = () => api<ApiRecipe[]>("GET", "/recipes")
export const getRecipe = (id: string) => api<ApiRecipe>("GET", `/recipes/${id}`)
export const recipeCost = (id: string) => api<FoodCost>("GET", `/recipes/${id}/cost`)
export const versionCost = (versionId: string) => api<FoodCost>("GET", `/recipes/versions/${versionId}/cost`)
export const listUnits = () => api<Unit[]>("GET", "/inventory/units")
export const listIngredients = () => api<Ingredient[]>("GET", "/inventory/items")
export const unmapped = () =>
  api<{ variant_id: string; item: string; variant: string; quantity_sold: string; recipe_id: string | null }[]>("GET", "/recipes/unmapped-items")

export const createRecipe = (variantId: string) => api<ApiRecipe>("POST", "/recipes", { body: { variant_id: variantId } })
export const addVersion = (recipeId: string, v: { yield_qty: string; method_text?: string; lines: ApiLine[] }) =>
  api<ApiVersion>("POST", `/recipes/${recipeId}/versions`, { body: v })
export const updateDraft = (versionId: string, v: { yield_qty: string; method_text?: string; lines: ApiLine[] }) =>
  api<ApiVersion>("PATCH", `/recipes/versions/${versionId}`, { body: v })
export const publish = (versionId: string) => api<ApiVersion>("POST", `/recipes/versions/${versionId}/publish`, { body: {} })

/** The version to show: the latest draft if there is one, else the one in effect, else the newest. */
export function currentVersion(r: ApiRecipe) {
  const sorted = [...r.versions].sort((a, b) => b.version_no - a.version_no)
  return sorted.find((v) => v.status === "Draft") ?? sorted.find((v) => v.id === r.active_version_id) ?? sorted[0]
}

export interface RecipeRow {
  id: string
  name: string
  version: string
  status: string
  cost: number
  price: number | null
  pct: number | null
  margin: number | null
  incomplete: boolean
  above: boolean
  target: number | null
  updated: string
}

/** Recipes with the cost of the version in effect (one cost request per recipe). */
export async function listRecipeRows(): Promise<RecipeRow[]> {
  const recipes = await listRecipes()
  const costs = await Promise.all(recipes.map((r) => (r.active_version_id ? recipeCost(r.id).catch(() => null) : Promise.resolve(null))))
  return recipes.map((r, i) => {
    const v = currentVersion(r)
    const c = costs[i]
    return {
      id: r.id,
      name: r.name,
      version: v ? `v${v.version_no}` : "—",
      status: v?.status === "Published" && v.id !== r.active_version_id ? "Scheduled" : (v?.status ?? "Draft"),
      cost: num(c?.cost_per_portion),
      price: c?.selling_price_ex_tax ? num(c.selling_price_ex_tax) : null,
      pct: c?.food_cost_pct ? num(c.food_cost_pct) : null,
      margin: c?.gross_margin ? num(c.gross_margin) : null,
      incomplete: !!c?.incomplete,
      above: !!c?.above_target,
      target: c?.target_pct ? num(c.target_pct) : null,
      updated: when(v?.published_at),
    }
  })
}
