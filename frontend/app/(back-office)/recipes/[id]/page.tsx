"use client"

import * as React from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { Lock, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { confirmAction } from "@/components/rms/dialog-host"
import { FormRow, KV, Notice, Page, PageHeader, Panel, SimpleSelect, StatusBadge } from "@/components/rms/kit"
import { listItems } from "@/lib/api/menu"
import * as rcp from "@/lib/api/recipes"
import { apiMessage, num, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

interface Line {
  key: string
  ingredient: string
  qty: string
  unit: string
  prep: string
  cook: string
}

async function loadEditor(id: string) {
  const [ingredients, units, items, recipe] = await Promise.all([
    rcp.listIngredients(),
    rcp.listUnits(),
    listItems(),
    id === "new" ? Promise.resolve(null) : rcp.getRecipe(id),
  ])
  const version = recipe ? rcp.currentVersion(recipe) : undefined
  const cost = version ? await rcp.versionCost(version.id).catch(() => null) : null
  const food = recipe?.active_version_id ? await rcp.recipeCost(recipe.id).catch(() => null) : null
  return { ingredients, units, items, recipe, version, cost, food }
}

export default function RecipeEditorPage() {
  const { id } = useParams<{ id: string }>()
  const { data, loading, reload } = useApi(() => loadEditor(id), [id], null)
  if (loading || !data) return <Page><PageHeader title="Recipe" description="Loading…" /></Page>
  if (id !== "new" && !data.recipe) return <Page><PageHeader title="Recipe not found" /></Page>
  return <Editor key={`${data.version?.id ?? "new"}-${data.version?.status ?? ""}`} data={data} reload={reload} />
}

function Editor({ data, reload }: { data: Awaited<ReturnType<typeof loadEditor>>; reload: () => void }) {
  const router = useRouter()
  const preset = useSearchParams().get("variant") ?? ""
  const { ingredients, units, items, recipe, version, cost, food } = data
  const locked = !!version && version.status !== "Draft"
  const unitById = Object.fromEntries(units.map((u) => [u.id, u]))
  const ingById = Object.fromEntries(ingredients.map((i) => [i.id, i]))

  // Variants that can get a recipe: one option per item size.
  const variantOpts = items.flatMap((m) =>
    m.raw.variants
      .filter((v) => v.is_active)
      .map((v) => ({ value: v.id, label: v.name_en === "Regular" ? m.name : `${m.name} (${v.name_en})` }))
  )
  const [variant, setVariant] = React.useState(recipe?.variant_id ?? preset)
  const [yieldN, setYield] = React.useState(version?.yield_qty ? String(num(version.yield_qty)) : "1")
  const [method, setMethod] = React.useState(version?.method_text ?? "")
  const [lines, setLines] = React.useState<Line[]>(
    version?.lines.map((l, i) => ({
      key: `l${i}`,
      ingredient: l.ingredient_id,
      qty: String(num(l.quantity)),
      unit: l.uom_id,
      prep: String(num(l.prep_loss_pct)),
      cook: String(num(l.cook_loss_pct)),
    })) ?? [{ key: "n0", ingredient: "", qty: "", unit: "", prep: "0", cook: "0" }]
  )
  const [busy, setBusy] = React.useState(false)

  const checked = lines.map((l) => {
    const ing = ingById[l.ingredient]
    const stock = ing ? unitById[ing.stock_uom_id] : undefined
    const unit = unitById[l.unit]
    const compatible = !stock || !unit || stock.dimension === unit.dimension
    const lossErr = Number(l.prep) + Number(l.cook) > 90
    return { ...l, compatible, lossErr, stockUnit: stock?.code }
  })
  const invalid =
    !variant ||
    !(Number(yieldN) > 0) ||
    checked.some((l) => !l.ingredient || !l.unit || !(Number(l.qty) > 0) || !l.compatible || l.lossErr)
  const update = (key: string, patch: Partial<Line>) => setLines(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)))
  const payload = () => ({
    yield_qty: yieldN,
    method_text: method || undefined,
    lines: lines.map((l) => ({ ingredient_id: l.ingredient, quantity: l.qty, uom_id: l.unit, prep_loss_pct: l.prep || "0", cook_loss_pct: l.cook || "0" })),
  })

  /** Save the draft (creating the recipe and version as needed). Returns the version id. */
  const saveDraft = async () => {
    if (version && version.status === "Draft") return (await rcp.updateDraft(version.id, payload())).id
    const r = recipe ?? (await rcp.createRecipe(variant))
    const v = await rcp.addVersion(r.id, payload())
    if (!recipe) router.replace(`/recipes/${r.id}`)
    return v.id
  }
  const run = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true)
    try {
      await fn()
      toast.success(done)
      reload()
    } catch (e) {
      toast.error(apiMessage(e))
    } finally {
      setBusy(false)
    }
  }
  /** A published version is never edited: copy it into a new draft (FR-RCP-005). */
  const newVersion = () =>
    run(async () => {
      await rcp.addVersion(recipe!.id, {
        yield_qty: version!.yield_qty,
        method_text: version!.method_text ?? undefined,
        lines: version!.lines,
      })
    }, `Draft v${(recipe!.versions.length || 0) + 1} created from this version`)

  const portion = num(cost?.cost_per_portion)
  const price = food?.selling_price_ex_tax ? num(food.selling_price_ex_tax) : null

  return (
    <Page>
      <PageHeader
        title={recipe ? `${recipe.name} recipe` : "New recipe"}
        description={recipe ? `Version ${version?.version_no ?? "—"}` : "Choose the item, add ingredients, then save a draft to see the cost."}
        actions={
          <>
            {version && <StatusBadge status={version.status} />}
            {locked ? (
              <Button disabled={busy} onClick={() => void newVersion()}>
                New version
              </Button>
            ) : (
              <>
                <Button variant="outline" disabled={invalid || busy} onClick={() => void run(saveDraft, "Draft saved")}>
                  Save draft
                </Button>
                <Button
                  disabled={invalid || busy}
                  onClick={() =>
                    confirmAction({
                      title: "Publish this version?",
                      effect: "Published versions can't be edited. Sales will consume ingredients from this version from now on.",
                      confirmLabel: "Publish",
                      onConfirm: () =>
                        void run(async () => {
                          const vid = await saveDraft()
                          await rcp.publish(vid)
                        }, "Recipe published"),
                    })
                  }
                >
                  Publish
                </Button>
              </>
            )}
          </>
        }
      />
      {version && (
        <Notice tone={locked ? "info" : "warning"}>
          <span className="flex items-center gap-1.5">
            {locked && <Lock className="size-3.5" />}Version {version.version_no} · {version.status}
            {version.published_at && ` · published ${when(version.published_at)}`}
            {version.status === "Published" && version.id !== recipe?.active_version_id && version.effective_from &&
              ` · takes effect ${when(version.effective_from)}`}
          </span>
        </Notice>
      )}
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1fr_300px]">
        <div className="grid gap-4">
          <Panel title="Details">
            <div className="grid gap-3 sm:grid-cols-2">
              <FormRow label="Menu item" required>
                <SimpleSelect
                  aria-label="Menu item"
                  value={variant}
                  onChange={setVariant}
                  disabled={!!recipe}
                  options={variantOpts}
                  placeholder="Select…"
                />
              </FormRow>
              <FormRow label="Yield (portions)" required htmlFor="yield">
                <Input id="yield" disabled={locked} inputMode="decimal" value={yieldN} onChange={(e) => setYield(e.target.value)} />
              </FormRow>
            </div>
          </Panel>
          <Panel
            title="Ingredients"
            actions={
              !locked && (
                <Button
                  variant="outline"
                  onClick={() => setLines([...lines, { key: `n${Date.now()}`, ingredient: "", qty: "", unit: "", prep: "0", cook: "0" }])}
                >
                  <Plus />
                  Add line
                </Button>
              )
            }
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-2xl text-sm">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="p-1.5 font-medium">Ingredient</th>
                    <th className="w-20 p-1.5 font-medium">Net qty</th>
                    <th className="w-28 p-1.5 font-medium">Unit</th>
                    <th className="w-16 p-1.5 font-medium">Prep %</th>
                    <th className="w-16 p-1.5 font-medium">Cook %</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {checked.map((l) => (
                    <React.Fragment key={l.key}>
                      <tr className="border-t">
                        <td className="p-1.5">
                          <SimpleSelect
                            aria-label="Ingredient"
                            disabled={locked}
                            value={l.ingredient}
                            onChange={(v) => update(l.key, { ingredient: v, unit: l.unit || ingById[v]?.stock_uom_id || "" })}
                            options={ingredients.filter((i) => i.is_active || i.id === l.ingredient).map((i) => ({ value: i.id, label: i.name_en }))}
                            placeholder="Search…"
                          />
                        </td>
                        <td className="p-1.5">
                          <Input aria-label="Quantity" disabled={locked} inputMode="decimal" value={l.qty} onChange={(e) => update(l.key, { qty: e.target.value })} />
                        </td>
                        <td className="p-1.5">
                          <SimpleSelect
                            aria-label="Unit"
                            disabled={locked}
                            invalid={!l.compatible}
                            value={l.unit}
                            onChange={(v) => update(l.key, { unit: v })}
                            options={units.map((u) => ({ value: u.id, label: u.code }))}
                            placeholder="Unit"
                          />
                        </td>
                        <td className="p-1.5">
                          <Input aria-label="Preparation loss" disabled={locked} inputMode="decimal" value={l.prep} onChange={(e) => update(l.key, { prep: e.target.value })} />
                        </td>
                        <td className="p-1.5">
                          <Input aria-label="Cooking loss" disabled={locked} inputMode="decimal" value={l.cook} onChange={(e) => update(l.key, { cook: e.target.value })} />
                        </td>
                        <td>
                          {!locked && (
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label="Remove line"
                              disabled={lines.length === 1}
                              onClick={() => setLines(lines.filter((x) => x.key !== l.key))}
                            >
                              <Trash2 />
                            </Button>
                          )}
                        </td>
                      </tr>
                      {!l.compatible && (
                        <tr>
                          <td colSpan={6} className="px-1.5 pb-1.5 text-xs text-danger">
                            {unitById[l.unit]?.code} can&apos;t be converted to {l.stockUnit}. Pick a compatible unit.
                          </td>
                        </tr>
                      )}
                      {l.lossErr && (
                        <tr>
                          <td colSpan={6} className="px-1.5 pb-1.5 text-xs text-danger">
                            Total loss can&apos;t be more than 90%.
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel title="Preparation method">
            <textarea
              aria-label="Preparation method"
              disabled={locked}
              className="min-h-24 w-full rounded-lg border bg-transparent p-2 text-sm"
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              placeholder="Steps shown to kitchen staff"
            />
          </Panel>
        </div>
        <Panel title="Cost per portion" className="lg:sticky lg:top-18">
          {cost ? (
            <>
              <p className="tabular text-3xl font-semibold">{usd(portion)}</p>
              <KV
                className="mt-3"
                items={[
                  ...(price !== null
                    ? ([
                        ["Selling price excl. tax", usd(price)],
                        [
                          "Food cost",
                          <span key="p" className={food?.above_target ? "text-danger" : ""}>
                            {food?.food_cost_pct}%
                          </span>,
                        ],
                        ["Gross margin", usd(num(food?.gross_margin))],
                      ] as [string, React.ReactNode][])
                    : []),
                  ...cost.lines.map((l) => [l.ingredient, l.cost_missing ? "No cost yet" : usd(num(l.cost))] as [string, React.ReactNode]),
                ]}
              />
              {cost.incomplete && (
                <p className="mt-2 text-xs text-warning">Some ingredients have no cost yet, so this is incomplete.</p>
              )}
              <p className="mt-2 text-xs text-muted-foreground">
                Version {cost.version_no} at current weighted average costs.{price === null && " Food cost % shows once a version is in effect."}
              </p>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Save a draft to see the cost.</p>
          )}
        </Panel>
      </div>
    </Page>
  )
}
