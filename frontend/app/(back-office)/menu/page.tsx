"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { Ban, Check, Eye, Plus } from "lucide-react"
import { Switch } from "@/components/ui/switch"
import { CrudTable } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  LinkButton,
  MoneyText,
  Page,
  PageHeader,
  PageTabs,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { CombosTab } from "@/components/rms/combo-slots"
import { PriceListsTab, SchedulesTab } from "@/components/rms/menu-pricing"
import * as menu from "@/lib/api/menu"
import { act, num, save, useApi } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

const stations = ["Hot", "Cold", "Beverage", "Dessert", "Bar", "None"]

export default function MenuPage() {
  const router = useRouter()
  const [tab, setTab] = useTab("items")
  const items = useApi(menu.listItems, [], [])
  const cats = useApi(menu.listCategories, [], [])
  const groups = useApi(menu.listGroups, [], [])
  const rows = items.data
  const variants = rows.flatMap((m) =>
    m.raw.variants.map((v) => ({
      id: v.id,
      item: m.name,
      variant: v.name_en,
      price: v.price === null ? null : num(v.price),
      status: v.is_active ? "Active" : "Inactive",
    }))
  )
  const catRows = cats.data.map((c) => ({
    id: c.id,
    name: c.name_en,
    km: c.name_km ?? "",
    order: c.sort_order,
    active: c.is_active,
  }))
  const groupRows = groups.data.map((g) => ({
    id: g.id,
    name: g.name_en,
    km: g.name_km ?? "",
    min: g.min_select,
    max: g.max_select,
    modifiers: g.modifiers
      .filter((m) => m.is_active)
      .map((m) => (num(m.price_delta) ? `${m.name_en} +${usd(num(m.price_delta))}` : m.name_en))
      .join(", "),
  }))

  return (
    <Page>
      <PageHeader
        title="Menu"
        description="Items keep their order-time price and name, so changes here only affect new orders."
        actions={
          <LinkButton href="/menu/new">
            <Plus />
            New item
          </LinkButton>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "items", label: "Items", count: rows.length },
          { value: "categories", label: "Categories", count: catRows.length },
          { value: "variants", label: "Variants" },
          { value: "modifiers", label: "Modifiers", count: groupRows.length },
          { value: "combos", label: "Combos", count: rows.filter((m) => m.type === "Combo").length },
          { value: "prices", label: "Price lists" },
          { value: "schedules", label: "Schedules" },
          { value: "availability", label: "Availability" },
        ]}
      />
      {tab === "items" && (
        <DataTable
          rows={rows}
          exportName="menu-items"
          pageSize={12}
          emptyTitle={items.loading ? "Loading…" : "No menu items"}
          searchPlaceholder="Name (EN or ខ្មែរ) or code…"
          onRowClick={(m) => router.push(`/menu/${m.id}`)}
          searchValue={(m) => `${m.name} ${m.km} ${m.code} ${m.raw.barcode ?? ""}`}
          filters={[
            { key: "category", label: "Category", options: catRows.map((c) => c.name) },
            { key: "station", label: "Station", options: stations },
            {
              key: "active",
              label: "Status",
              options: ["Active", "Inactive"],
              value: (m) => (m.active ? "Active" : "Inactive"),
            },
          ]}
          columns={[
            { key: "code", header: "Code" },
            {
              key: "name",
              header: "Name",
              render: (m) => (
                <span>
                  <span className="font-medium">{m.name}</span>{" "}
                  <span className="text-muted-foreground">{m.km}</span>
                </span>
              ),
            },
            { key: "category", header: "Category" },
            { key: "station", header: "Station" },
            {
              key: "price",
              header: "Price",
              align: "right",
              render: (m) => <MoneyText value={m.price} />,
            },
            {
              key: "avail",
              header: "Availability",
              value: (m) => (m.available ? "Available" : "Sold out"),
              render: (m) => (
                <StatusBadge status={m.available ? "Available" : "Sold out"} tone={m.available ? "success" : "danger"} />
              ),
            },
            {
              key: "active",
              header: "Status",
              value: (m) => (m.active ? "Active" : "Inactive"),
              render: (m) => <StatusBadge status={m.active ? "Active" : "Inactive"} />,
            },
          ]}
          rowActions={(m) => [
            { label: "Open", icon: Eye, onClick: () => router.push(`/menu/${m.id}`) },
            m.active
              ? {
                  label: "Deactivate",
                  icon: Ban,
                  destructive: true,
                  onClick: () =>
                    confirmAction({
                      title: `Deactivate ${m.name}?`,
                      effect:
                        "Ordered items are never deleted. It disappears from POS but open orders keep their snapshot.",
                      destructive: true,
                      confirmLabel: "Deactivate",
                      onConfirm: () => void act(() => menu.deactivateItem(m.id), `${m.name} deactivated`, items.reload),
                    }),
                }
              : {
                  label: "Activate",
                  icon: Check,
                  onClick: () =>
                    void act(() => menu.updateItem(m.id, { is_active: true, version: m.raw.version }), `${m.name} activated`, items.reload),
                },
          ]}
        />
      )}
      {tab === "categories" && (
        <CrudTable
          noun="Category"
          rows={catRows}
          onSave={(v, e) =>
            save(() =>
              menu.saveCategory(
                { name_en: String(v.name), name_km: String(v.km ?? "") || undefined, sort_order: Number(v.order) || 0, is_active: v.active !== false },
                e?.id
              )
            ).then(cats.reload)
          }
          columns={[
            { key: "order", header: "Order", align: "right" },
            { key: "name", header: "English name" },
            { key: "km", header: "Khmer name" },
            {
              key: "active",
              header: "Status",
              value: (c) => (c.active ? "Active" : "Inactive"),
              render: (c) => <StatusBadge status={c.active ? "Active" : "Inactive"} />,
            },
          ]}
          fields={[
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", half: true },
            { name: "order", label: "Display order", type: "number", min: 0, required: true, half: true },
            { name: "active", label: "Active", type: "switch", half: true },
          ]}
          toForm={(c) => ({ name: c.name, km: c.km, order: String(c.order), active: c.active })}
        />
      )}
      {tab === "variants" && (
        <DataTable
          rows={variants}
          exportName="variants"
          columns={[
            { key: "item", header: "Item" },
            { key: "variant", header: "Variant" },
            {
              key: "price",
              header: "Current price",
              align: "right",
              render: (r) => (r.price === null ? "No price" : usd(r.price)),
            },
            { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
          ]}
        />
      )}
      {tab === "modifiers" && (
        <CrudTable
          noun="Modifier group"
          rows={groupRows}
          canEdit={false}
          description="Groups can't be edited after they are created; create a new group and attach it instead."
          onSave={(v) =>
            save(() =>
              menu.createGroup({
                name_en: String(v.name),
                name_km: String(v.km ?? "") || undefined,
                min_select: Number(v.min),
                max_select: Number(v.max),
                modifiers: menu.parseModifiers(String(v.modifiers)),
              })
            ).then(groups.reload)
          }
          columns={[
            { key: "name", header: "Group" },
            { key: "km", header: "Khmer" },
            {
              key: "rule",
              header: "Rule",
              value: (g) => (g.min > 0 ? `Required, ${g.min}–${g.max}` : `Optional, up to ${g.max}`),
            },
            { key: "modifiers", header: "Modifiers" },
          ]}
          fields={[
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", half: true },
            { name: "min", label: "Minimum", type: "number", min: 0, required: true, half: true },
            {
              name: "max",
              label: "Maximum",
              type: "number",
              min: 1,
              required: true,
              half: true,
              validate: (v, a) => (Number(a.min) > Number(v) ? "Minimum can't exceed maximum" : undefined),
            },
            {
              name: "modifiers",
              label: "Modifiers, comma separated (add a price like “Extra egg +0.50”)",
              required: true,
              type: "textarea",
            },
          ]}
        />
      )}
      {tab === "combos" && <CombosTab items={rows} onOpen={(id) => router.push(`/menu/${id}?tab=combo`)} />}
      {tab === "prices" && <PriceListsTab items={rows} />}
      {tab === "schedules" && <SchedulesTab items={rows} />}
      {tab === "availability" && (
        <DataTable
          rows={rows.filter((m) => m.active)}
          pageSize={14}
          exportName="availability"
          columns={[
            { key: "name", header: "Item", render: (m) => <span className="font-medium">{m.name}</span> },
            { key: "station", header: "Station" },
            {
              key: "state",
              header: "Today",
              value: (m) => (m.available ? "Available" : "Sold out"),
              render: (m) => (
                <StatusBadge status={m.available ? "Available" : "Sold out"} tone={m.available ? "success" : "danger"} />
              ),
            },
            {
              key: "toggle",
              header: "Available",
              sortable: false,
              align: "right",
              render: (m) => (
                <Switch
                  aria-label={`${m.name} available`}
                  checked={m.available}
                  onCheckedChange={(c) =>
                    void act(
                      () => menu.setAvailability(m.id, Boolean(c)),
                      `${m.name} ${c ? "is available" : "marked sold out until end of day"}`,
                      items.reload
                    )
                  }
                />
              ),
            },
          ]}
        />
      )}
    </Page>
  )
}
