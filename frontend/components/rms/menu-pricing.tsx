"use client"

/** Menu → Price lists and Schedules (FR-MENU-008, BR-003). Rules are checked in the branch's local time by the server. */
import * as React from "react"
import { Ban, Check, Eye, Tag } from "lucide-react"
import { CrudTable, RecordDialog, type FieldValue } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { Panel, StatusBadge } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import type { ItemRow } from "@/lib/api/menu"
import { can, useSession } from "@/lib/api/session"
import { act, num, save, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const CHANNELS = ["POS", "Online", "QR", "Platform"]
const TYPES = ["DineIn", "Takeaway", "Delivery"]

const daysText = (d: number[]) => (d.length ? d.map((x) => DAYS[x]).join(" ") : "Every day")
const hoursText = (f: string | null, t: string | null) => (f && t ? `${f.slice(0, 5)}–${t.slice(0, 5)}` : "All day")
const parseDays = (v: FieldValue | undefined) =>
  String(v ?? "")
    .split(/[ ,]+/)
    .map((x) => DAYS.findIndex((d) => d.toLowerCase() === x.trim().slice(0, 3).toLowerCase()))
    .filter((x) => x >= 0)
const parseList = (v: FieldValue | undefined, allowed: string[]) =>
  String(v ?? "")
    .split(/[ ,]+/)
    .map((x) => allowed.find((a) => a.toLowerCase() === x.trim().toLowerCase()))
    .filter((x): x is string => !!x)
const time = (v: FieldValue | undefined) => (v ? String(v) : null)

interface PriceList {
  id: string
  code: string
  name: string
  is_active: boolean
  priority: number
  days_of_week: number[]
  time_from: string | null
  time_to: string | null
  channels: string[]
  order_types: string[]
  branch_ids: string[]
  auto_apply: boolean
}
interface Schedule {
  id: string
  name: string
  days_of_week: number[]
  time_from: string | null
  time_to: string | null
  date_from: string | null
  date_to: string | null
  is_active: boolean
  item_ids: string[]
}

export function PriceListsTab({ items }: { items: ItemRow[] }) {
  const { me } = useSession()
  const manage = can(me, "menu.manage")
  const lists = useApi(() => api<PriceList[]>("GET", "/price-lists"), [], [])
  const [viewing, setViewing] = React.useState<PriceList | null>(null)
  const prices = useApi(
    () =>
      viewing
        ? api<{ menu_item_id: string; item: string; variant_id: string; variant: string; price: string; valid_from: string | null; valid_to: string | null }[]>(
            "GET",
            `/price-lists/${viewing.id}/prices`
          )
        : Promise.resolve([]),
    [viewing?.id],
    []
  )
  const [priceFor, setPriceFor] = React.useState<PriceList | null>(null)
  const variantOpts = items.flatMap((m) =>
    m.raw.variants.filter((v) => v.is_active).map((v) => ({ label: v.name_en === "Regular" ? m.name : `${m.name} (${v.name_en})`, item: m.id, variant: v.id }))
  )

  return (
    <>
      <CrudTable
        noun="Price list"
        rows={lists.data.map((l) => ({
          ...l,
          when: l.auto_apply ? `${daysText(l.days_of_week)} · ${hoursText(l.time_from, l.time_to)}` : "Only where chosen",
          where: [l.channels.join(", ") || "All channels", l.order_types.join(", ") || "all order types"].join(" · "),
          status: l.is_active ? "Active" : "Inactive",
        }))}
        canAdd={manage}
        canEdit={manage}
        description="Automatic lists apply while their days, hours, channels and order types match; the highest priority wins. Items without a price on the list keep their Standard price."
        onSave={(v, e) => {
          const body = {
            name: v.name,
            priority: Number(v.priority) || 10,
            days_of_week: parseDays(v.days),
            time_from: time(v.time_from),
            time_to: time(v.time_to),
            channels: parseList(v.channels, CHANNELS),
            order_types: parseList(v.types, TYPES),
            auto_apply: v.auto !== false,
            is_active: v.active !== false,
          }
          return save(() =>
            e ? api("PATCH", `/price-lists/${e.id}`, { body: e.code === "STANDARD" ? { name: v.name } : body }) : api("POST", "/price-lists", { body: { ...body, code: String(v.code).toUpperCase() } })
          ).then(lists.reload)
        }}
        columns={[
          { key: "name", header: "Price list", render: (l) => <span className="font-medium">{l.name}</span> },
          { key: "code", header: "Code" },
          { key: "when", header: "When" },
          { key: "where", header: "Applies to" },
          { key: "priority", header: "Priority", align: "right" },
          { key: "status", header: "Status", render: (l) => <StatusBadge status={l.code === "STANDARD" ? "Base" : l.status} /> },
        ]}
        fields={[
          { name: "name", label: "Name", required: true, half: true },
          { name: "code", label: "Code (capitals, can't change later)", required: true, half: true, validate: (x) => (/^[A-Za-z0-9_]{2,30}$/.test(String(x)) ? undefined : "2–30 letters, digits or _") },
          { name: "auto", label: "Apply automatically while the rules match", type: "switch", half: true },
          { name: "priority", label: "Priority (higher wins)", type: "number", min: 1, max: 1000, half: true },
          { name: "days", label: "Days (e.g. Mon Tue Fri; empty = every day)" },
          { name: "time_from", label: "From", type: "time", half: true },
          { name: "time_to", label: "To", type: "time", half: true, hint: "May pass midnight" },
          { name: "channels", label: "Channels (POS, Online, QR, Platform; empty = all)", half: true },
          { name: "types", label: "Order types (DineIn, Takeaway, Delivery; empty = all)", half: true },
          { name: "active", label: "Active", type: "switch" },
        ]}
        toForm={(l) => ({
          name: l.name,
          code: l.code,
          auto: l.auto_apply,
          priority: String(l.priority),
          days: l.days_of_week.map((d) => DAYS[d]).join(" "),
          time_from: l.time_from?.slice(0, 5) ?? "",
          time_to: l.time_to?.slice(0, 5) ?? "",
          channels: l.channels.join(", "),
          types: l.order_types.join(", "),
          active: l.is_active,
        })}
        extraActions={(l) => [
          { label: "View prices", icon: Eye, onClick: () => setViewing(l) },
          ...(manage
            ? [
                { label: "Set an item price", icon: Tag, onClick: () => setPriceFor(l) },
                ...(l.code === "STANDARD"
                  ? []
                  : [
                      l.is_active
                        ? { label: "Deactivate", icon: Ban, destructive: true, onClick: () => void act(() => api("PATCH", `/price-lists/${l.id}`, { body: { is_active: false } }), `${l.name} deactivated`, lists.reload) }
                        : { label: "Activate", icon: Check, onClick: () => void act(() => api("PATCH", `/price-lists/${l.id}`, { body: { is_active: true } }), `${l.name} activated`, lists.reload) },
                    ]),
              ]
            : []),
        ]}
      />
      {viewing && (
        <Panel title={`${viewing.name} prices`} description="Prices in effect now. Items not listed use their Standard price.">
          <DataTable
            rows={prices.data.map((p) => ({ ...p, id: p.variant_id, label: p.variant === "Regular" ? p.item : `${p.item} (${p.variant})`, from: when(p.valid_from), to: when(p.valid_to) || "open" }))}
            exportName={`prices-${viewing.code}`}
            emptyTitle="No prices on this list yet"
            columns={[
              { key: "label", header: "Item" },
              { key: "price", header: "Price", align: "right", render: (p) => usd(num(p.price)) },
              { key: "from", header: "Since" },
              { key: "to", header: "Until" },
            ]}
          />
        </Panel>
      )}
      <RecordDialog
        open={!!priceFor}
        onOpenChange={(o) => !o && setPriceFor(null)}
        title={`Price on ${priceFor?.name ?? ""}`}
        description="Takes effect from the time given. Earlier prices stay in the history; orders already placed keep their price."
        fields={[
          { name: "item", label: "Item", type: "select", options: variantOpts.map((x) => x.label), required: true },
          { name: "price", label: "Price (USD)", type: "number", min: 0, required: true, half: true },
          { name: "from", label: "From (empty = now)", type: "date", half: true },
        ]}
        onSubmit={(v) => {
          const target = variantOpts.find((x) => x.label === v.item)!
          const from = v.from ? new Date(`${v.from}T00:00`) : new Date()
          return save(() =>
            api("POST", `/menu-items/${target.item}/prices`, {
              body: { variant_id: target.variant, price: String(v.price), valid_from: from.toISOString(), price_list: priceFor!.code },
            })
          ).then(prices.reload)
        }}
      />
    </>
  )
}

export function SchedulesTab({ items }: { items: ItemRow[] }) {
  const { me } = useSession()
  const manage = can(me, "menu.manage")
  const list = useApi(() => api<Schedule[]>("GET", "/menu-schedules"), [], [])
  const name = (id: string) => items.find((i) => i.id === id)?.name ?? "?"
  const toBody = (v: Record<string, FieldValue>) => ({
    name: v.name,
    days_of_week: parseDays(v.days),
    time_from: time(v.time_from),
    time_to: time(v.time_to),
    date_from: v.date_from || null,
    date_to: v.date_to || null,
    is_active: v.active !== false,
    item_ids: String(v.items ?? "")
      .split(",")
      .map((s) => items.find((i) => i.name.toLowerCase() === s.trim().toLowerCase() || i.code.toLowerCase() === s.trim().toLowerCase())?.id)
      .filter((x): x is string => !!x),
  })
  return (
    <CrudTable
      noun="Menu schedule"
      rows={list.data.map((s) => ({
        ...s,
        when: `${daysText(s.days_of_week)} · ${hoursText(s.time_from, s.time_to)}`,
        dates: s.date_from || s.date_to ? `${s.date_from ?? "…"} – ${s.date_to ?? "…"}` : "Always",
        itemNames: s.item_ids.map(name).join(", "),
        status: s.is_active ? "Active" : "Inactive",
      }))}
      canAdd={manage}
      canEdit={manage}
      description="Items on a schedule can be ordered only while one of their schedules is in effect. Items on no schedule are always available."
      onSave={(v, e) => save(() => (e ? api("PUT", `/menu-schedules/${e.id}`, { body: toBody(v) }) : api("POST", "/menu-schedules", { body: toBody(v) }))).then(list.reload)}
      columns={[
        { key: "name", header: "Schedule", render: (s) => <span className="font-medium">{s.name}</span> },
        { key: "when", header: "When" },
        { key: "dates", header: "Dates" },
        { key: "itemNames", header: "Items" },
        { key: "status", header: "Status", render: (s) => <StatusBadge status={s.status} /> },
      ]}
      fields={[
        { name: "name", label: "Name", required: true },
        { name: "days", label: "Days (e.g. Sat Sun; empty = every day)" },
        { name: "time_from", label: "From", type: "time", half: true },
        { name: "time_to", label: "To", type: "time", half: true },
        { name: "date_from", label: "First day", type: "date", half: true },
        { name: "date_to", label: "Last day", type: "date", half: true },
        { name: "items", label: "Items, comma separated (names or codes)", type: "textarea", hint: items.slice(0, 6).map((i) => i.code).join(", ") + "…" },
        { name: "active", label: "Active", type: "switch" },
      ]}
      toForm={(s) => ({
        name: s.name,
        days: s.days_of_week.map((d) => DAYS[d]).join(" "),
        time_from: s.time_from?.slice(0, 5) ?? "",
        time_to: s.time_to?.slice(0, 5) ?? "",
        date_from: s.date_from ?? "",
        date_to: s.date_to ?? "",
        items: s.item_ids.map(name).join(", "),
        active: s.is_active,
      })}
    />
  )
}
