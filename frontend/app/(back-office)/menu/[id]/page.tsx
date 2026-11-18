"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { RecordForm, validateFields, type Field, type FieldValue } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { LinkButton, Notice, Page, PageHeader, PageTabs, Panel, StatusBadge, useTab } from "@/components/rms/kit"
import { ComboSlotsEditor } from "@/components/rms/combo-slots"
import * as menu from "@/lib/api/menu"
import { apiMessage, num, useApi } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

const CHANNELS = [
  { code: "POS", label: "POS" },
  { code: "Online", label: "Online ordering" },
  { code: "Platform", label: "Delivery platforms" },
]

interface VariantDraft {
  id?: string
  name: string
  price: string
  /** Price when loaded, to send a new effective-dated price only when it changed. */
  was?: string
}

/** Everything the editor needs; a new item has no `item`. */
async function loadEditor(id: string) {
  const [cats, groups, taxes, stations, item] = await Promise.all([
    menu.listCategories(),
    menu.listGroups(),
    menu.listTaxProfiles(),
    menu.listStations(),
    id === "new" ? Promise.resolve(null) : menu.getItem(id),
  ])
  const history = item ? await menu.priceHistory(item) : []
  return { cats, groups, taxes, stations, item, history }
}

export default function MenuItemPage() {
  const { id } = useParams<{ id: string }>()
  const isNew = id === "new"
  const { data, loading } = useApi(() => loadEditor(id), [id], null)
  if (loading || !data) return <Page><PageHeader title={isNew ? "New menu item" : "Menu item"} description="Loading…" /></Page>
  if (!isNew && !data.item) return <Page><PageHeader title="Menu item not found" /></Page>
  return <Editor key={data.item?.version ?? "new"} data={data} />
}

function Editor({ data }: { data: Awaited<ReturnType<typeof loadEditor>> }) {
  const router = useRouter()
  const { cats, groups: allGroups, taxes, stations, item, history } = data
  const isNew = !item
  const [tab, setTab] = useTab("general")
  const stationName = (code: string | null) => (code ? (stations.find((s) => s.code === code)?.name ?? code) : "None")

  const fields: Field[] = [
    { name: "name", label: "Name (English)", required: true, half: true },
    { name: "km", label: "Name (Khmer)", half: true },
    { name: "code", label: "Code", required: true, half: true },
    { name: "sku", label: "SKU / barcode", half: true },
    { name: "category", label: "Category", type: "select", options: cats.map((c) => c.name_en), required: true, half: true },
    { name: "type", label: "Item type", type: "select", options: ["Food", "Beverage", "Other", "Combo"], required: true, half: true },
    {
      name: "station",
      label: "Kitchen station",
      type: "select",
      options: [...stations.filter((s) => s.is_active).map((s) => s.name), "None"],
      required: true,
      half: true,
    },
    { name: "tax", label: "Tax profile", type: "select", options: taxes.filter((t) => t.is_active).map((t) => t.name), required: true, half: true },
    { name: "desc", label: "Description", type: "textarea" },
  ]
  const [values, setValues] = React.useState<Record<string, FieldValue>>({
    name: item?.name_en ?? "",
    km: item?.name_km ?? "",
    code: item?.code ?? "",
    sku: item?.barcode ?? "",
    category: item?.category_name_en ?? cats[0]?.name_en ?? "",
    type: item?.item_type ?? "Food",
    station: item ? stationName(item.station_code) : (stations[0]?.name ?? "None"),
    tax: taxes.find((t) => t.id === item?.tax_profile_id)?.name ?? taxes[0]?.name ?? "",
    desc: item?.description ?? "",
  })
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const [variants, setVariants] = React.useState<VariantDraft[]>(
    item
      ? item.variants.filter((v) => v.is_active).map((v) => ({ id: v.id, name: v.name_en, price: v.price === null ? "" : String(num(v.price)), was: v.price === null ? "" : String(num(v.price)) }))
      : [{ name: "Regular", price: "" }]
  )
  const [groups, setGroups] = React.useState<string[]>(item?.modifier_groups.map((g) => g.id) ?? [])
  const [channels, setChannels] = React.useState<string[]>(item?.channels ?? ["POS"])
  const [dirty, setDirty] = React.useState(false)
  const [saving, setSaving] = React.useState(false)

  React.useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault()
    }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [dirty])

  const submit = async () => {
    const errs = validateFields(fields, values)
    setErrors(errs)
    if (Object.keys(errs).length) {
      setTab("general")
      return toast.error("Fix the highlighted fields")
    }
    if (variants.some((v) => !v.name.trim() || v.price === "" || !(Number(v.price) >= 0)))
      return (setTab("variants"), toast.error("Every variant needs a name and a price"))
    if (!channels.length) return (setTab("channels"), toast.error("Choose at least one channel"))
    const common = {
      name_en: String(values.name),
      name_km: String(values.km ?? "") || null,
      description: String(values.desc ?? "") || null,
      category_id: cats.find((c) => c.name_en === values.category)!.id,
      item_type: values.type,
      station_code: stations.find((s) => s.name === values.station)?.code ?? null,
      tax_profile_id: taxes.find((t) => t.name === values.tax)!.id,
      barcode: String(values.sku ?? "") || null,
      channels,
    }
    setSaving(true)
    try {
      let itemId = item?.id
      if (!item) {
        const made = await menu.createItem({
          ...common,
          code: String(values.code),
          variants: variants.map((v) => ({ name_en: v.name.trim(), price: v.price })),
        })
        itemId = made.id
      } else {
        await menu.updateItem(item.id, { ...common, version: item.version })
        // Prices are effective-dated: a changed price becomes a new price from now on (BR-048).
        for (const v of variants) if (v.id && v.price !== v.was) await menu.addPrice(item.id, v.id, Number(v.price))
      }
      const before = item?.modifier_groups.map((g) => g.id).sort().join() ?? ""
      if (groups.slice().sort().join() !== before) await menu.attachGroups(itemId!, groups)
      setDirty(false)
      toast.success("Menu item saved")
      router.push("/menu")
    } catch (e) {
      toast.error(apiMessage(e))
      setSaving(false)
    }
  }

  return (
    <Page>
      <PageHeader
        title={isNew ? "New menu item" : item.name_en}
        description={
          isNew ? "Name, station and tax profile are needed before it can appear on POS." : `${item.code} · ${item.name_km ?? ""}`
        }
        actions={
          <>
            {item && <StatusBadge status={item.is_active ? "Active" : "Inactive"} />}
            <LinkButton href="/menu" variant="outline">
              Cancel
            </LinkButton>
            <Button onClick={() => void submit()} disabled={saving}>
              {saving ? "Saving…" : "Save item"}
            </Button>
          </>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "general", label: "General" },
          { value: "variants", label: "Variants & prices", count: variants.length },
          { value: "modifiers", label: "Modifiers", count: groups.length },
          ...(item?.item_type === "Combo" ? [{ value: "combo", label: "Combo slots", count: item.combo_slots?.length ?? 0 }] : []),
          { value: "channels", label: "Channels" },
          ...(item ? [{ value: "history", label: "Price history", count: history.length }] : []),
        ]}
      />
      {tab === "general" && (
        <Panel title="Item details" className="max-w-3xl">
          <RecordForm
            fields={item ? fields.map((f) => (f.name === "code" ? { ...f, disabled: true } : f)) : fields}
            values={values}
            errors={errors}
            setValue={(k, v) => {
              setValues((s) => ({ ...s, [k]: v }))
              setDirty(true)
            }}
          />
        </Panel>
      )}
      {tab === "variants" && (
        <Panel
          title="Variants & prices"
          description={
            item
              ? "A changed price takes effect now; the old price stays in the history. New sizes can be added when the item is created."
              : "Sizes or portions, each with its own price. Use one “Regular” variant for a single size."
          }
          className="max-w-2xl"
          actions={
            !item && (
              <Button variant="outline" onClick={() => setVariants([...variants, { name: "", price: "" }])}>
                <Plus />
                Add variant
              </Button>
            )
          }
        >
          <ul className="grid gap-2">
            {variants.map((v, i) => (
              <li key={v.id ?? i} className="grid grid-cols-[1fr_120px_auto] gap-2">
                <Input
                  aria-label="Variant name"
                  placeholder="Name"
                  value={v.name}
                  disabled={!!v.id}
                  onChange={(e) => {
                    setVariants(variants.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
                    setDirty(true)
                  }}
                />
                <Input
                  aria-label={`${v.name || "Variant"} price (USD)`}
                  inputMode="decimal"
                  value={v.price}
                  onChange={(e) => {
                    setVariants(variants.map((x, j) => (j === i ? { ...x, price: e.target.value } : x)))
                    setDirty(true)
                  }}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Remove variant"
                  disabled={!!v.id || variants.length === 1}
                  onClick={() => setVariants(variants.filter((_, j) => j !== i))}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {tab === "modifiers" && (
        <Panel title="Modifier groups" className="max-w-2xl">
          {allGroups.length === 0 && <p className="text-sm text-muted-foreground">No modifier groups yet. Create them on the Menu page.</p>}
          <ul className="divide-y">
            {allGroups.map((g) => (
              <li key={g.id}>
                <label className="flex items-start gap-3 py-2 text-sm">
                  <Checkbox
                    className="mt-0.5"
                    checked={groups.includes(g.id)}
                    onCheckedChange={(c) => {
                      setGroups(c ? [...groups, g.id] : groups.filter((x) => x !== g.id))
                      setDirty(true)
                    }}
                  />
                  <span>
                    <span className="font-medium">{g.name_en}</span>{" "}
                    <span className="text-xs text-muted-foreground">
                      {g.min_select > 0 ? `required ${g.min_select}–${g.max_select}` : `optional, up to ${g.max_select}`}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {g.modifiers
                        .map((m) => (num(m.price_delta) ? `${m.name_en} +${usd(num(m.price_delta))}` : m.name_en))
                        .join(", ")}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {tab === "combo" && item && <ComboTab item={item} />}
      {tab === "channels" && (
        <Panel title="Sold through" className="max-w-md">
          <ul className="grid gap-2">
            {CHANNELS.map((c) => (
              <li key={c.code}>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={channels.includes(c.code)}
                    onCheckedChange={(on) => {
                      setChannels(on ? [...channels, c.code] : channels.filter((x) => x !== c.code))
                      setDirty(true)
                    }}
                  />
                  {c.label}
                </label>
              </li>
            ))}
          </ul>
          <Notice tone="info" className="mt-3">
            Items are sold at every branch unless a branch stops selling them.
          </Notice>
        </Panel>
      )}
      {tab === "history" && (
        <DataTable
          rows={history}
          exportName="price-history"
          emptyTitle="No price history"
          columns={[
            { key: "variant", header: "Variant" },
            { key: "price", header: "Price", align: "right", render: (r) => usd(r.price) },
            { key: "from", header: "Effective from" },
            { key: "to", header: "Effective to" },
            { key: "created", header: "Recorded" },
          ]}
        />
      )}
    </Page>
  )
}

function ComboTab({ item }: { item: menu.ApiItem }) {
  const router = useRouter()
  const items = useApi(menu.listItems, [], [])
  if (items.loading) return <p className="text-sm text-muted-foreground">Loading items…</p>
  return <ComboSlotsEditor item={item} items={items.data} onSaved={() => router.refresh()} />
}
