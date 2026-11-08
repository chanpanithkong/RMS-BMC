"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { Ban, Check, Eye, Plus, Upload } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { CrudTable, newId } from "@/components/rms/crud"
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
import { usd } from "@/lib/rms/billing"
import { categories, modifierGroups, rms, useRms } from "@/lib/rms/store"
import type { MenuItem } from "@/lib/rms/types"

const catName = (id: string) => categories.find((c) => c.id === id)?.name ?? id
const stations = ["Hot", "Cold", "Beverage", "Dessert", "Bar", "None"]

export default function MenuPage() {
  const { menu } = useRms()
  const router = useRouter()
  const [tab, setTab] = useTab("items")
  const variants = menu.flatMap((m) =>
    (m.variants ?? []).map((v) => ({
      id: `${m.id}-${v.name}`,
      item: m.name,
      variant: v.name,
      price: v.price,
      recipe: "Linked",
    }))
  )
  return (
    <Page>
      <PageHeader
        title="Menu"
        description="Items keep their order-time price and name, so changes here only affect new orders."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() =>
                toast.info("Choose a filled template spreadsheet to validate")
              }
            >
              <Upload />
              Import
            </Button>
            <LinkButton href="/menu/new">
              <Plus />
              New item
            </LinkButton>
          </>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "items", label: "Items", count: menu.length },
          { value: "categories", label: "Categories" },
          { value: "variants", label: "Variants" },
          { value: "modifiers", label: "Modifiers" },
          { value: "combos", label: "Combos" },
          { value: "prices", label: "Price lists" },
          { value: "schedules", label: "Schedules" },
          { value: "availability", label: "Availability" },
          { value: "history", label: "Price history" },
        ]}
      />
      {tab === "items" && (
        <DataTable<MenuItem>
          rows={menu}
          exportName="menu-items"
          pageSize={12}
          searchPlaceholder="Name (EN or ខ្មែរ) or code…"
          onRowClick={(m) => router.push(`/menu/${m.id}`)}
          searchValue={(m) => `${m.name} ${m.km} ${m.code} ${m.sku ?? ""}`}
          filters={[
            {
              key: "cat",
              label: "Category",
              value: (m) => catName(m.cat),
              options: categories.map((c) => c.name),
            },
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
            { key: "cat", header: "Category", value: (m) => catName(m.cat) },
            { key: "station", header: "Station" },
            { key: "tax", header: "Tax profile", hidden: true },
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
                <StatusBadge
                  status={m.available ? "Available" : "Sold out"}
                  tone={m.available ? "success" : "danger"}
                />
              ),
            },
            {
              key: "active",
              header: "Status",
              value: (m) => (m.active ? "Active" : "Inactive"),
              render: (m) => (
                <StatusBadge status={m.active ? "Active" : "Inactive"} />
              ),
            },
          ]}
          rowActions={(m) => [
            {
              label: "Open",
              icon: Eye,
              onClick: () => router.push(`/menu/${m.id}`),
            },
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
                      onConfirm: () => rms.saveMenu({ ...m, active: false }),
                    }),
                }
              : {
                  label: "Activate",
                  icon: Check,
                  onClick: () => rms.saveMenu({ ...m, active: true }),
                },
          ]}
        />
      )}
      {tab === "categories" && (
        <CrudTable
          noun="Category"
          seed={categories}
          columns={[
            { key: "order", header: "Order", align: "right" },
            { key: "name", header: "English name" },
            { key: "km", header: "Khmer name" },
            {
              key: "active",
              header: "Status",
              value: (c) => (c.active ? "Active" : "Inactive"),
              render: (c) => (
                <StatusBadge status={c.active ? "Active" : "Inactive"} />
              ),
            },
          ]}
          fields={[
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", required: true, half: true },
            {
              name: "order",
              label: "Display order",
              type: "number",
              min: 1,
              required: true,
              half: true,
            },
            { name: "active", label: "Active", type: "switch", half: true },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            km: String(v.km),
            order: Number(v.order),
            active: Boolean(v.active),
          })}
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
              header: "Price",
              align: "right",
              render: (r) => usd(r.price),
            },
            {
              key: "recipe",
              header: "Recipe",
              render: (r) => <StatusBadge status={r.recipe} tone="success" />,
            },
          ]}
        />
      )}
      {tab === "modifiers" && (
        <CrudTable
          noun="Modifier group"
          seed={modifierGroups.map((g) => ({
            id: g.id,
            name: g.name,
            km: g.km,
            min: g.min,
            max: g.max,
            modifiers: g.modifiers
              .map((m) => (m.delta ? `${m.name} +${usd(m.delta)}` : m.name))
              .join(", "),
          }))}
          columns={[
            { key: "name", header: "Group" },
            { key: "km", header: "Khmer" },
            {
              key: "rule",
              header: "Rule",
              value: (g) =>
                g.min > 0
                  ? `Required, ${g.min}–${g.max}`
                  : `Optional, up to ${g.max}`,
            },
            { key: "modifiers", header: "Modifiers" },
          ]}
          fields={[
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", required: true, half: true },
            {
              name: "min",
              label: "Minimum",
              type: "number",
              min: 0,
              required: true,
              half: true,
            },
            {
              name: "max",
              label: "Maximum",
              type: "number",
              min: 1,
              required: true,
              half: true,
              validate: (v, a) =>
                Number(a.min) > Number(v)
                  ? "Minimum can't exceed maximum"
                  : undefined,
            },
            {
              name: "modifiers",
              label: "Modifiers (comma separated)",
              required: true,
              type: "textarea",
            },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            km: String(v.km),
            min: Number(v.min),
            max: Number(v.max),
            modifiers: String(v.modifiers),
          })}
        />
      )}
      {tab === "combos" && (
        <CrudTable
          noun="Combo"
          seed={[
            {
              id: "cb1",
              name: "Lunch Set",
              km: "ឈុតថ្ងៃត្រង់",
              slots:
                "Main: Fried Rice / Kuy Teav · Drink: Iced Coffee / Palm Juice",
              price: 6.5,
              status: "Active",
            },
            {
              id: "cb2",
              name: "Family Set",
              km: "ឈុតគ្រួសារ",
              slots: "2 Mains · Soup · 4 Rice · Dessert",
              price: 29,
              status: "Active",
            },
          ]}
          columns={[
            { key: "name", header: "Combo" },
            { key: "km", header: "Khmer" },
            { key: "slots", header: "Slots" },
            {
              key: "price",
              header: "Price",
              align: "right",
              render: (r) => usd(r.price),
            },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", required: true, half: true },
            {
              name: "slots",
              label: "Slots and eligible items",
              required: true,
              type: "textarea",
            },
            {
              name: "price",
              label: "Combo price",
              type: "number",
              min: 0,
              required: true,
            },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            km: String(v.km),
            slots: String(v.slots),
            price: Number(v.price),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "prices" && (
        <CrudTable
          noun="Price list"
          seed={[
            {
              id: "pl1",
              name: "Standard",
              window: "All day",
              branch: "All",
              from: "01/01/2026",
              to: "",
              status: "Active",
            },
            {
              id: "pl2",
              name: "Happy Hour",
              window: "Mon–Fri 15:00–18:00",
              branch: "Riverside",
              from: "01/10/2026",
              to: "",
              status: "Active",
            },
            {
              id: "pl3",
              name: "Delivery",
              window: "All day",
              branch: "All",
              from: "01/01/2026",
              to: "",
              status: "Active",
            },
            {
              id: "pl4",
              name: "Online",
              window: "All day",
              branch: "All",
              from: "01/06/2026",
              to: "",
              status: "Active",
            },
            {
              id: "pl5",
              name: "Staff",
              window: "Staff meal",
              branch: "All",
              from: "01/01/2026",
              to: "",
              status: "Active",
            },
          ]}
          columns={[
            { key: "name", header: "Price list" },
            { key: "window", header: "Time window" },
            { key: "branch", header: "Branch" },
            { key: "from", header: "Effective from" },
            { key: "to", header: "Effective to" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            { name: "name", label: "Name", required: true, half: true },
            {
              name: "branch",
              label: "Branch",
              type: "select",
              options: ["All", "Riverside", "BKK1", "Siem Reap"],
              required: true,
              half: true,
            },
            { name: "window", label: "Time window", required: true },
            {
              name: "from",
              label: "Effective from",
              required: true,
              half: true,
            },
            { name: "to", label: "Effective to", half: true },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            window: String(v.window),
            branch: String(v.branch),
            from: String(v.from),
            to: String(v.to ?? ""),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "schedules" && (
        <CrudTable
          noun="Menu schedule"
          seed={[
            {
              id: "ms1",
              name: "Breakfast",
              days: "Every day",
              time: "07:00–10:30",
              dates: "Always",
              status: "Active",
            },
            {
              id: "ms2",
              name: "Khmer New Year specials",
              days: "Every day",
              time: "All day",
              dates: "14/04/2027–16/04/2027",
              status: "Scheduled",
            },
          ]}
          columns={[
            { key: "name", header: "Schedule" },
            { key: "days", header: "Days" },
            { key: "time", header: "Time" },
            { key: "dates", header: "Dates" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            { name: "name", label: "Name", required: true },
            { name: "days", label: "Days of week", required: true, half: true },
            { name: "time", label: "Time window", required: true, half: true },
            { name: "dates", label: "Date range", required: true },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            days: String(v.days),
            time: String(v.time),
            dates: String(v.dates),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "availability" && (
        <DataTable<MenuItem>
          rows={menu}
          pageSize={14}
          exportName="availability"
          columns={[
            {
              key: "name",
              header: "Item",
              render: (m) => <span className="font-medium">{m.name}</span>,
            },
            { key: "station", header: "Station" },
            {
              key: "state",
              header: "Today",
              value: (m) => (m.available ? "Available" : "Sold out"),
              render: (m) => (
                <StatusBadge
                  status={m.available ? "Available" : "Sold out"}
                  tone={m.available ? "success" : "danger"}
                />
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
                  onCheckedChange={(c) => {
                    rms.setAvailable(m.id, Boolean(c))
                    toast.success(
                      `${m.name} ${c ? "is available" : "marked sold out until end of day"}`
                    )
                  }}
                />
              ),
            },
          ]}
        />
      )}
      {tab === "history" && (
        <DataTable
          rows={[
            {
              id: "1",
              item: "Beef Lok Lak",
              list: "Standard",
              old: 9,
              next: 9.5,
              effective: "01/11/2026 00:00",
              user: "Dara Pich",
              approval: "Vannak Keo",
            },
            {
              id: "2",
              item: "Iced Coffee",
              list: "Standard",
              old: 1.75,
              next: 2,
              effective: "15/10/2026 00:00",
              user: "Dara Pich",
              approval: "Vannak Keo",
            },
            {
              id: "3",
              item: "Draft Beer",
              list: "Happy Hour",
              old: 2,
              next: 1.5,
              effective: "01/10/2026 15:00",
              user: "Sopheak Nou",
              approval: "Dara Pich",
            },
          ]}
          exportName="price-history"
          columns={[
            { key: "item", header: "Item" },
            { key: "list", header: "Price list" },
            {
              key: "old",
              header: "Old",
              align: "right",
              render: (r) => usd(r.old),
            },
            {
              key: "next",
              header: "New",
              align: "right",
              render: (r) => usd(r.next),
            },
            { key: "effective", header: "Effective" },
            { key: "user", header: "Changed by" },
            { key: "approval", header: "Approved by" },
          ]}
        />
      )}
    </Page>
  )
}
