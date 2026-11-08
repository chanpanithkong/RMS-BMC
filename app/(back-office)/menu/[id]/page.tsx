"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import {
  RecordForm,
  validateFields,
  type Field,
  type FieldValue,
} from "@/components/rms/crud"
import {
  LinkButton,
  Page,
  PageHeader,
  PageTabs,
  Panel,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import { categories, modifierGroups, rms, useRms } from "@/lib/rms/store"
import type { MenuItem, Station, Variant } from "@/lib/rms/types"

const blank: MenuItem = {
  id: "",
  code: "",
  name: "",
  km: "",
  cat: "rice",
  station: "Hot",
  price: 0,
  type: "Food",
  groups: [],
  available: true,
  active: true,
  tax: "VAT Standard",
  desc: "",
  channels: ["POS"],
}

const fields: Field[] = [
  { name: "name", label: "Name (English)", required: true, half: true },
  { name: "km", label: "Name (Khmer)", required: true, half: true },
  { name: "code", label: "Code", required: true, half: true },
  { name: "sku", label: "SKU / barcode", half: true },
  {
    name: "category",
    label: "Category",
    type: "select",
    options: categories.map((c) => c.name),
    required: true,
    half: true,
  },
  {
    name: "type",
    label: "Item type",
    type: "select",
    options: ["Food", "Beverage", "Other"],
    required: true,
    half: true,
  },
  {
    name: "station",
    label: "Kitchen station",
    type: "select",
    options: ["Hot", "Cold", "Beverage", "Dessert", "Bar", "None"],
    required: true,
    half: true,
  },
  {
    name: "tax",
    label: "Tax profile",
    type: "select",
    options: ["VAT Standard", "Tax inclusive", "Exempt"],
    required: true,
    half: true,
  },
  {
    name: "price",
    label: "Base price (USD)",
    type: "number",
    required: true,
    min: 0,
    half: true,
  },
  {
    name: "image",
    label: "Image (JPEG, PNG or WebP, up to 2 MB)",
    type: "file",
    half: true,
  },
  { name: "desc", label: "Description", type: "textarea" },
]

export default function MenuItemPage() {
  const { id } = useParams<{ id: string }>()
  const { menu } = useRms()
  const router = useRouter()
  const existing = menu.find((m) => m.id === id)
  const isNew = id === "new"
  const item = existing ?? blank
  const [tab, setTab] = useTab("general")
  const [values, setValues] = React.useState<Record<string, FieldValue>>({
    name: item.name,
    km: item.km,
    code: item.code,
    sku: item.sku ?? "",
    category: categories.find((c) => c.id === item.cat)?.name ?? "",
    type: item.type,
    station: item.station,
    tax: item.tax,
    price: String(item.price),
    desc: item.desc,
  })
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const [variants, setVariants] = React.useState<Variant[]>(item.variants ?? [])
  const [groups, setGroups] = React.useState<string[]>(item.groups)
  const [channels, setChannels] = React.useState(item.channels)
  const [dirty, setDirty] = React.useState(false)

  React.useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault()
    }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [dirty])

  const save = () => {
    const errs = validateFields(fields, values)
    setErrors(errs)
    if (Object.keys(errs).length) {
      setTab("general")
      return toast.error("Fix the highlighted fields")
    }
    rms.saveMenu({
      ...item,
      id: isNew ? `m-${String(values.code).toLowerCase()}` : item.id,
      name: String(values.name),
      km: String(values.km),
      code: String(values.code),
      sku: String(values.sku) || undefined,
      cat: categories.find((c) => c.name === values.category)!.id,
      type: values.type as MenuItem["type"],
      station: values.station as Station,
      tax: String(values.tax),
      price: Number(values.price),
      desc: String(values.desc ?? ""),
      variants: variants.length ? variants : undefined,
      groups,
      channels,
    })
    setDirty(false)
    toast.success("Menu item saved")
    router.push("/menu")
  }
  return (
    <Page>
      <PageHeader
        title={isNew ? "New menu item" : item.name}
        description={
          isNew
            ? "Name, station and tax profile are needed before it can appear on POS."
            : `${item.code} · ${item.km}`
        }
        actions={
          <>
            {!isNew && (
              <StatusBadge status={item.active ? "Active" : "Inactive"} />
            )}
            <LinkButton href="/menu" variant="outline">
              Cancel
            </LinkButton>
            <Button onClick={save}>Save item</Button>
          </>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "general", label: "General" },
          { value: "variants", label: "Variants", count: variants.length },
          { value: "modifiers", label: "Modifiers", count: groups.length },
          { value: "channels", label: "Branches & channels" },
        ]}
      />
      {tab === "general" && (
        <Panel title="Item details" className="max-w-3xl">
          <RecordForm
            fields={fields}
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
          title="Variants"
          description="Sizes or portions, each with its own price and optional recipe."
          className="max-w-2xl"
          actions={
            <Button
              variant="outline"
              onClick={() => setVariants([...variants, { name: "", price: 0 }])}
            >
              <Plus />
              Add variant
            </Button>
          }
        >
          {variants.length === 0 && (
            <p className="text-sm text-muted-foreground">
              This item has one size.
            </p>
          )}
          <ul className="grid gap-2">
            {variants.map((v, i) => (
              <li key={i} className="grid grid-cols-[1fr_120px_auto] gap-2">
                <Input
                  aria-label="Variant name"
                  placeholder="Name"
                  value={v.name}
                  onChange={(e) =>
                    setVariants(
                      variants.map((x, j) =>
                        j === i ? { ...x, name: e.target.value } : x
                      )
                    )
                  }
                />
                <Input
                  aria-label="Variant price"
                  inputMode="decimal"
                  value={String(v.price)}
                  onChange={(e) =>
                    setVariants(
                      variants.map((x, j) =>
                        j === i
                          ? { ...x, price: Number(e.target.value) || 0 }
                          : x
                      )
                    )
                  }
                />
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Remove variant"
                  onClick={() =>
                    setVariants(variants.filter((_, j) => j !== i))
                  }
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
          <ul className="divide-y">
            {modifierGroups.map((g) => (
              <li key={g.id}>
                <label className="flex items-start gap-3 py-2 text-sm">
                  <Checkbox
                    className="mt-0.5"
                    checked={groups.includes(g.id)}
                    onCheckedChange={(c) =>
                      setGroups(
                        c ? [...groups, g.id] : groups.filter((x) => x !== g.id)
                      )
                    }
                  />
                  <span>
                    <span className="font-medium">{g.name}</span>{" "}
                    <span className="text-xs text-muted-foreground">
                      {g.min > 0
                        ? `required ${g.min}–${g.max}`
                        : `optional, up to ${g.max}`}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {g.modifiers
                        .map((m) =>
                          m.delta ? `${m.name} +${usd(m.delta)}` : m.name
                        )
                        .join(", ")}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {tab === "channels" && (
        <Panel title="Sold through" className="max-w-md">
          <ul className="grid gap-2">
            {[
              "POS",
              "Online",
              "Delivery platforms",
              "Riverside",
              "BKK1",
              "Siem Reap",
            ].map((c) => (
              <li key={c}>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={channels.includes(c)}
                    onCheckedChange={(on) =>
                      setChannels(
                        on ? [...channels, c] : channels.filter((x) => x !== c)
                      )
                    }
                  />
                  {c}
                </label>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </Page>
  )
}
