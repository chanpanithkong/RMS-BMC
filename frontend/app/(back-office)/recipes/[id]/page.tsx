"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { Lock, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  FormRow,
  KV,
  Notice,
  Page,
  PageHeader,
  Panel,
  SimpleSelect,
  StatusBadge,
  opts,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import { ingredients, recipes } from "@/lib/rms/back-office"
import { useRms } from "@/lib/rms/store"

interface Line {
  id: string
  ingredient: string
  qty: string
  unit: string
  prep: string
  cook: string
}
const dims: Record<string, string> = {
  g: "mass",
  kg: "mass",
  ml: "volume",
  L: "volume",
  piece: "count",
}
const toBase: Record<string, number> = {
  g: 0.001,
  kg: 1,
  ml: 0.001,
  L: 1,
  piece: 1,
}

export default function RecipeEditorPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { menu } = useRms()
  const r = recipes.find((x) => x.id === id)
  const [item, setItem] = React.useState(r?.item ?? "")
  const [yieldN, setYield] = React.useState(String(r?.yield ?? 1))
  const [method, setMethod] = React.useState("")
  const [lines, setLines] = React.useState<Line[]>(
    r?.lines ?? [
      { id: "n0", ingredient: "", qty: "", unit: "g", prep: "0", cook: "0" },
    ]
  )
  const locked = r?.status === "Active"
  const price = menu.find((m) => m.name === item)?.price ?? r?.price ?? 0

  const calc = lines.map((l) => {
    const ing = ingredients.find((i) => i.name === l.ingredient)
    const compatible = !ing || dims[l.unit] === dims[ing.unit]
    const loss = Math.min(Number(l.prep) + Number(l.cook), 90) / 100
    const gross = (Number(l.qty) || 0) / (1 - loss)
    const stockQty =
      ing && compatible ? (gross * toBase[l.unit]) / toBase[ing.unit] : 0
    return {
      ...l,
      compatible,
      gross,
      stockUnit: ing?.unit,
      cost: stockQty * (ing?.cost ?? 0),
      lossErr: Number(l.prep) + Number(l.cook) > 90,
    }
  })
  const batch = calc.reduce((s, l) => s + l.cost, 0)
  const portion = batch / (Number(yieldN) || 1)
  const pct = price ? (portion / price) * 100 : 0
  const invalid =
    !item ||
    calc.some(
      (l) => !l.ingredient || !(Number(l.qty) > 0) || !l.compatible || l.lossErr
    )
  const update = (i: string, patch: Partial<Line>) =>
    setLines(lines.map((l) => (l.id === i ? { ...l, ...patch } : l)))
  const unmappedOpts = opts(...menu.map((m) => m.name))

  return (
    <Page>
      <PageHeader
        title={r ? `${r.item} recipe` : "New recipe"}
        description={
          r
            ? `${r.variant} · ${r.portion}`
            : "Add ingredients to see the cost per portion."
        }
        actions={
          <>
            {r && (
              <StatusBadge
                status={r.status === "Active" ? "Published" : r.status}
              />
            )}
            {locked ? (
              <Button
                onClick={() => {
                  toast.success("Draft v-next created from this version")
                  router.push("/recipes/new")
                }}
              >
                New version
              </Button>
            ) : (
              <>
                <Button
                  variant="outline"
                  disabled={!item}
                  onClick={() => {
                    toast.success("Draft saved")
                    router.push("/recipes")
                  }}
                >
                  Save draft
                </Button>
                <Button
                  disabled={invalid}
                  onClick={() =>
                    confirmAction({
                      title: "Publish this version?",
                      effect:
                        "Published versions can't be edited. Sales will consume ingredients from this version from now on.",
                      confirmLabel: "Publish",
                      onConfirm: () => {
                        toast.success("Recipe published")
                        router.push("/recipes")
                      },
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
      {r && (
        <Notice tone={locked ? "info" : "warning"}>
          <span className="flex items-center gap-1.5">
            {locked && <Lock className="size-3.5" />}Version {r.version} ·{" "}
            {r.status} · last changed {r.updated} by {r.by}
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
                  value={item}
                  onChange={setItem}
                  options={unmappedOpts}
                  placeholder="Select…"
                />
              </FormRow>
              <FormRow label="Yield (portions)" required htmlFor="yield">
                <Input
                  id="yield"
                  disabled={locked}
                  inputMode="numeric"
                  value={yieldN}
                  onChange={(e) => setYield(e.target.value)}
                />
              </FormRow>
            </div>
          </Panel>
          <Panel
            title="Ingredients"
            actions={
              !locked && (
                <Button
                  variant="outline"
                  onClick={() =>
                    setLines([
                      ...lines,
                      {
                        id: `n${lines.length}-${Date.now()}`,
                        ingredient: "",
                        qty: "",
                        unit: "g",
                        prep: "0",
                        cook: "0",
                      },
                    ])
                  }
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
                    <th className="w-24 p-1.5 font-medium">Unit</th>
                    <th className="w-16 p-1.5 font-medium">Prep %</th>
                    <th className="w-16 p-1.5 font-medium">Cook %</th>
                    <th className="p-1.5 text-right font-medium">Gross</th>
                    <th className="p-1.5 text-right font-medium">Cost</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {calc.map((l) => (
                    <React.Fragment key={l.id}>
                      <tr className="border-t">
                        <td className="p-1.5">
                          <SimpleSelect
                            aria-label="Ingredient"
                            value={l.ingredient}
                            onChange={(v) => update(l.id, { ingredient: v })}
                            options={opts(...ingredients.map((i) => i.name))}
                            placeholder="Search…"
                          />
                        </td>
                        <td className="p-1.5">
                          <Input
                            aria-label="Quantity"
                            disabled={locked}
                            inputMode="decimal"
                            value={l.qty}
                            onChange={(e) =>
                              update(l.id, { qty: e.target.value })
                            }
                          />
                        </td>
                        <td className="p-1.5">
                          <SimpleSelect
                            aria-label="Unit"
                            invalid={!l.compatible}
                            value={l.unit}
                            onChange={(v) => update(l.id, { unit: v })}
                            options={opts("g", "kg", "ml", "L", "piece")}
                          />
                        </td>
                        <td className="p-1.5">
                          <Input
                            aria-label="Preparation loss"
                            disabled={locked}
                            inputMode="decimal"
                            value={l.prep}
                            onChange={(e) =>
                              update(l.id, { prep: e.target.value })
                            }
                          />
                        </td>
                        <td className="p-1.5">
                          <Input
                            aria-label="Cooking loss"
                            disabled={locked}
                            inputMode="decimal"
                            value={l.cook}
                            onChange={(e) =>
                              update(l.id, { cook: e.target.value })
                            }
                          />
                        </td>
                        <td className="tabular p-1.5 text-right">
                          {l.gross.toFixed(1)} {l.unit}
                        </td>
                        <td className="tabular p-1.5 text-right">
                          {usd(l.cost)}
                        </td>
                        <td>
                          {!locked && (
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label="Remove line"
                              onClick={() =>
                                setLines(lines.filter((x) => x.id !== l.id))
                              }
                            >
                              <Trash2 />
                            </Button>
                          )}
                        </td>
                      </tr>
                      {!l.compatible && (
                        <tr>
                          <td
                            colSpan={8}
                            className="px-1.5 pb-1.5 text-xs text-danger"
                          >
                            {l.unit} can&apos;t be converted to {l.stockUnit}.
                            Pick a compatible unit.
                          </td>
                        </tr>
                      )}
                      {l.lossErr && (
                        <tr>
                          <td
                            colSpan={8}
                            className="px-1.5 pb-1.5 text-xs text-danger"
                          >
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
          <p className="tabular text-3xl font-semibold">{usd(portion)}</p>
          <KV
            className="mt-3"
            items={[
              ["Selling price", usd(price)],
              [
                "Food cost",
                <span key="p" className={pct > 35 ? "text-danger" : ""}>
                  {pct.toFixed(1)}%
                </span>,
              ],
              ["Gross margin", usd(price - portion)],
              ["Batch cost", usd(batch)],
            ]}
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Uses weighted average ingredient costs as of 08/11/2026.
          </p>
        </Panel>
      </div>
    </Page>
  )
}
