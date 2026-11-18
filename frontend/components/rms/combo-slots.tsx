"use client"

/**
 * Combo meals (FR-MENU-005). A combo's price is shared across the chosen items in proportion to their normal
 * prices, so item sales, food cost and stock follow the real items. Slots list which items may fill each part.
 */
import * as React from "react"
import { Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Notice, Panel } from "@/components/rms/kit"
import { DataTable } from "@/components/rms/data-table"
import * as menu from "@/lib/api/menu"
import { apiMessage, num } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

interface SlotDraft {
  key: string
  name: string
  min: string
  max: string
  /** variant id -> extra charge */
  options: Record<string, string>
}

const draftOf = (s: menu.ApiComboSlot): SlotDraft => ({
  key: s.id,
  name: s.name_en,
  min: String(s.min_select),
  max: String(s.max_select),
  options: Object.fromEntries(s.options.map((o) => [o.variant_id, num(o.price_delta) ? String(num(o.price_delta)) : ""])),
})

export function ComboSlotsEditor({ item, items, onSaved }: { item: menu.ApiItem; items: menu.ItemRow[]; onSaved: () => void }) {
  const [slots, setSlots] = React.useState<SlotDraft[]>(() =>
    item.combo_slots?.length ? item.combo_slots.map(draftOf) : [{ key: "new-0", name: "Main", min: "1", max: "1", options: {} }]
  )
  const [busy, setBusy] = React.useState(false)
  const choices = items
    .filter((i) => i.active && i.type !== "Combo" && i.id !== item.id)
    .flatMap((i) =>
      i.raw.variants
        .filter((v) => v.is_active)
        .map((v) => ({ id: v.id, label: v.name_en === "Regular" ? i.name : `${i.name} (${v.name_en})`, price: v.price === null ? null : num(v.price), category: i.category }))
    )
  const patch = (key: string, p: Partial<SlotDraft>) => setSlots((s) => s.map((x) => (x.key === key ? { ...x, ...p } : x)))
  const save = async () => {
    for (const s of slots) {
      const n = Object.keys(s.options).length
      if (!s.name.trim()) return toast.error("Every slot needs a name.")
      if (!n) return toast.error(`Choose at least one item for ${s.name}.`)
      if (Number(s.min) > Number(s.max)) return toast.error(`In ${s.name}, the minimum can't exceed the maximum.`)
      if (Number(s.max) > n) return toast.error(`${s.name} allows ${s.max} choices but has only ${n} item${n === 1 ? "" : "s"}.`)
    }
    setBusy(true)
    try {
      await menu.saveComboSlots(
        item.id,
        slots.map((s) => ({
          name_en: s.name.trim(),
          min_select: Number(s.min) || 0,
          max_select: Number(s.max) || 1,
          options: Object.entries(s.options).map(([variant_id, d]) => ({ variant_id, price_delta: String(Number(d) || 0) })),
        }))
      )
      toast.success("Combo slots saved")
      onSaved()
    } catch (e) {
      toast.error(apiMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Panel
      title="Combo slots"
      description="The combo price (on Variants & prices) is shared across the chosen items in proportion to their normal prices. An extra charge is added when a premium item is chosen."
      className="max-w-3xl"
      actions={
        <Button onClick={save} disabled={busy}>
          Save slots
        </Button>
      }
    >
      {item.item_type !== "Combo" && <Notice tone="warning">Set the item type to Combo on the General tab and save before adding slots.</Notice>}
      <div className="space-y-5">
        {slots.map((s) => (
          <fieldset key={s.key} className="rounded-lg border p-3">
            <div className="flex flex-wrap items-end gap-2">
              <label className="grid gap-1 text-sm">
                Slot name
                <Input value={s.name} onChange={(e) => patch(s.key, { name: e.target.value })} className="w-40" />
              </label>
              <label className="grid gap-1 text-sm">
                Minimum
                <Input type="number" min={0} value={s.min} onChange={(e) => patch(s.key, { min: e.target.value })} className="w-20" />
              </label>
              <label className="grid gap-1 text-sm">
                Maximum
                <Input type="number" min={1} value={s.max} onChange={(e) => patch(s.key, { max: e.target.value })} className="w-20" />
              </label>
              <Button
                variant="ghost"
                size="icon"
                className="ml-auto"
                aria-label={`Remove ${s.name}`}
                disabled={slots.length === 1}
                onClick={() => setSlots((x) => x.filter((y) => y.key !== s.key))}
              >
                <Trash2 />
              </Button>
            </div>
            <ul className="mt-3 grid max-h-64 gap-1 overflow-y-auto sm:grid-cols-2">
              {choices.map((c) => {
                const on = c.id in s.options
                return (
                  <li key={c.id} className="flex items-center gap-2 text-sm">
                    <label className="flex min-w-0 flex-1 items-center gap-2">
                      <Checkbox
                        checked={on}
                        onCheckedChange={(v) => {
                          const next = { ...s.options }
                          if (v) next[c.id] = ""
                          else delete next[c.id]
                          patch(s.key, { options: next })
                        }}
                      />
                      <span className="truncate">{c.label}</span>
                      <span className="text-xs text-muted-foreground">{c.price === null ? "no price" : usd(c.price)}</span>
                    </label>
                    {on && (
                      <Input
                        aria-label={`Extra charge for ${c.label}`}
                        placeholder="+0.00"
                        type="number"
                        min={0}
                        step="0.25"
                        value={s.options[c.id]}
                        onChange={(e) => patch(s.key, { options: { ...s.options, [c.id]: e.target.value } })}
                        className="h-8 w-20"
                      />
                    )}
                  </li>
                )
              })}
            </ul>
          </fieldset>
        ))}
      </div>
      <Button
        variant="outline"
        className="mt-3"
        onClick={() => setSlots((x) => [...x, { key: `new-${Date.now()}`, name: x.length === 1 ? "Drink" : "Side", min: "1", max: "1", options: {} }])}
      >
        <Plus />
        Add slot
      </Button>
    </Panel>
  )
}

/** Menu → Combos: every combo with its price and slots. */
export function CombosTab({ items, onOpen }: { items: menu.ItemRow[]; onOpen: (id: string) => void }) {
  const combos = items.filter((i) => i.type === "Combo")
  return (
    <DataTable
      rows={combos.map((c) => ({
        ...c,
        slots: (c.raw.combo_slots ?? [])
          .map((s) => `${s.name_en}: ${s.options.map((o) => (o.variant_name === "Regular" ? o.item_name_en : `${o.item_name_en} (${o.variant_name})`)).join(" / ")}`)
          .join(" · "),
      }))}
      exportName="combos"
      emptyTitle="No combos yet"
      onRowClick={(c) => onOpen(c.id)}
      columns={[
        { key: "name", header: "Combo", render: (c) => <span className="font-medium">{c.name}</span> },
        { key: "price", header: "Price", align: "right", render: (c) => usd(c.price) },
        { key: "slots", header: "Slots", render: (c) => c.slots || <span className="text-muted-foreground">Not set up</span> },
      ]}
    />
  )
}
