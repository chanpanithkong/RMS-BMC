"use client"

import * as React from "react"
import { Ban, Check, Ticket } from "lucide-react"
import { CrudTable, RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { Notice, Page, PageHeader, PageTabs, StatusBadge, useTab } from "@/components/rms/kit"
import { SettingsForm } from "@/components/rms/settings-form"
import { api } from "@/lib/api/client"
import { listCategories, listItems } from "@/lib/api/menu"
import { can, useSession } from "@/lib/api/session"
import { act, num, save, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

interface ApiPromo {
  id: string
  name: string
  promo_type: string
  scope: string
  value: string
  target_ids: string[]
  buy_qty: number | null
  get_qty: number | null
  valid_from: string
  valid_to: string | null
  days_of_week: number[]
  time_from: string | null
  time_to: string | null
  order_types: string[]
  priority: number
  combinable: boolean
  auto_apply: boolean
  is_active: boolean
}
interface PromoDetail extends ApiPromo {
  codes: { id: string; code: string; max_uses: number | null; max_uses_per_customer: number | null; uses: number; is_active: boolean }[]
  redemptions: number
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const TYPES: Record<string, string> = { "Percent off": "Percent", "Amount off": "Amount", "Fixed price": "FixedPrice", "Buy X get Y": "BuyXGetY" }
const TYPE_LABEL = Object.fromEntries(Object.entries(TYPES).map(([k, v]) => [v, k]))
const LIMIT_LABEL: Record<string, string> = {
  discount_pct: "Discount up to (%)",
  discount_amount: "Discount up to (USD)",
  void: "Void up to (USD)",
  refund: "Refund up to (USD)",
  cash_variance: "Cash variance up to (USD)",
  stock_adjustment: "Stock adjustment up to (USD)",
}

const describe = (p: ApiPromo) =>
  p.promo_type === "Percent"
    ? `${num(p.value)}%`
    : p.promo_type === "BuyXGetY"
      ? `Buy ${p.buy_qty} get ${p.get_qty}`
      : p.promo_type === "FixedPrice"
        ? `${usd(num(p.value))} each`
        : usd(num(p.value))

/** Load promotions with their codes and redemption counts (one detail request each). */
async function loadPromos() {
  const list = await api<ApiPromo[]>("GET", "/promotions")
  return Promise.all(list.map((p) => api<PromoDetail>("GET", `/promotions/${p.id}`)))
}

export default function PromotionsPage() {
  const [tab, setTab] = useTab("promotions")
  const { me } = useSession()
  const manage = can(me, "promotions.manage")
  const promos = useApi(loadPromos, [], [])
  const targets = useApi(
    async () => {
      // Targets are optional: without menu.view only "Whole order" is offered.
      const [cats, items] = await Promise.all([listCategories().catch(() => []), listItems().catch(() => [])])
      return [
        ...cats.filter((c) => c.is_active).map((c) => ({ label: `Category: ${c.name_en}`, scope: "Category", id: c.id })),
        ...items.filter((m) => m.active).map((m) => ({ label: `Item: ${m.name}`, scope: "Item", id: m.id })),
      ]
    },
    [],
    [] as { label: string; scope: string; id: string }[]
  )
  const reasons = useApi(
    () => api<{ id: string; kind: string; code: string; name_en: string; name_km: string | null }[]>("GET", "/reason-codes"),
    [],
    []
  )
  const roles = useApi(
    () => api<{ id: string; code: string; name: string; limits: Record<string, string> }[]>("GET", "/roles").catch(() => []),
    [],
    []
  )
  const [codeFor, setCodeFor] = React.useState<PromoDetail | null>(null)

  const rows = promos.data.map((p) => ({
    ...p,
    type: TYPE_LABEL[p.promo_type] ?? p.promo_type,
    benefit: describe(p),
    appliesTo:
      p.scope === "Order"
        ? "Whole order"
        : p.target_ids.map((t) => targets.data.find((x) => x.id === t)?.label.replace(/^\w+: /, "") ?? "…").join(", "),
    window: `${when(p.valid_from).slice(0, 10)} – ${p.valid_to ? when(p.valid_to).slice(0, 10) : "open"}`,
    days: p.days_of_week.length ? p.days_of_week.map((d) => DAYS[d]).join(" ") : "Every day",
    hours: p.time_from ? `${p.time_from.slice(0, 5)}–${p.time_to?.slice(0, 5) ?? ""}` : "All day",
    status: !p.is_active ? "Inactive" : p.valid_to && new Date(p.valid_to) < new Date() ? "Ended" : new Date(p.valid_from) > new Date() ? "Scheduled" : "Active",
    how: p.auto_apply ? "Automatic" : "With a code",
  }))
  const codes = promos.data.flatMap((p) => p.codes.map((c) => ({ ...c, promotion: p.name, limit: c.max_uses ? `${c.uses} / ${c.max_uses}` : `${c.uses} / unlimited` })))
  const limitKeys = [...new Set(roles.data.flatMap((r) => Object.keys(r.limits)))]

  return (
    <Page>
      <PageHeader
        title="Promotions & discounts"
        description="Promotions apply automatically when an order qualifies, or with a code. Rules are fixed once created."
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "promotions", label: "Promotions", count: rows.length },
          { value: "codes", label: "Codes", count: codes.length },
          { value: "reasons", label: "Discount reasons" },
          { value: "limits", label: "Limits by role" },
          { value: "loyalty", label: "Loyalty" },
        ]}
      />
      {tab === "promotions" && (
        <CrudTable
          noun="Promotion"
          rows={rows}
          canEdit={false}
          canAdd={manage}
          description="To change a promotion's rules, end it and create a new one."
          onSave={(v) => {
            const t = targets.data.find((x) => x.label === v.target)
            const days = String(v.days ?? "")
              .split(",")
              .map((d) => DAYS.indexOf(d.trim().slice(0, 3)))
              .filter((d) => d >= 0)
            return save(() =>
              api("POST", "/promotions", {
                body: {
                  name: String(v.name),
                  promo_type: TYPES[String(v.type)],
                  scope: t ? t.scope : "Order",
                  value: String(v.value || "0"),
                  target_ids: t ? [t.id] : [],
                  buy_qty: v.type === "Buy X get Y" ? Number(v.buy) || 1 : undefined,
                  get_qty: v.type === "Buy X get Y" ? Number(v.get) || 1 : undefined,
                  valid_from: new Date(`${v.from}T00:00`).toISOString(),
                  valid_to: v.to ? new Date(`${v.to}T23:59:59`).toISOString() : undefined,
                  days_of_week: days,
                  time_from: v.time_from || undefined,
                  time_to: v.time_to || undefined,
                  priority: Number(v.priority) || 0,
                  combinable: Boolean(v.combinable),
                  auto_apply: v.how !== "With a code",
                },
              })
            ).then(promos.reload)
          }}
          filters={[{ key: "status", label: "Status", options: ["Active", "Scheduled", "Ended", "Inactive"] }]}
          columns={[
            { key: "name", header: "Promotion", render: (p) => <span className="font-medium">{p.name}</span> },
            { key: "type", header: "Type" },
            { key: "benefit", header: "Benefit", align: "right" },
            { key: "appliesTo", header: "Applies to" },
            { key: "window", header: "Dates" },
            { key: "days", header: "Days" },
            { key: "hours", header: "Hours" },
            { key: "how", header: "Applied" },
            { key: "redemptions", header: "Uses", align: "right" },
            { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
          ]}
          fields={[
            { name: "name", label: "Name", required: true },
            { name: "type", label: "Type", type: "select", options: Object.keys(TYPES), required: true, half: true },
            { name: "value", label: "Value (% or USD)", type: "number", min: 0, half: true, hint: "Not used for Buy X get Y" },
            { name: "target", label: "Applies to", type: "select", options: ["Whole order", ...targets.data.map((t) => t.label)], required: true },
            { name: "buy", label: "Buy quantity", type: "number", min: 1, half: true },
            { name: "get", label: "Free quantity", type: "number", min: 1, half: true },
            { name: "from", label: "Starts", type: "date", required: true, half: true },
            { name: "to", label: "Ends", type: "date", half: true },
            { name: "days", label: "Days (e.g. Mon, Tue; empty = every day)", half: true },
            { name: "time_from", label: "From time", type: "time", half: true },
            { name: "time_to", label: "To time", type: "time", half: true },
            { name: "priority", label: "Priority (higher wins)", type: "number", min: 0, half: true },
            { name: "how", label: "Applied", type: "select", options: ["Automatic", "With a code"], required: true, half: true },
            { name: "combinable", label: "Can combine with other promotions", type: "switch", half: true },
          ]}
          extraActions={(p) =>
            manage
              ? [
                  {
                    label: "Add code",
                    icon: Ticket,
                    onClick: () => setCodeFor(promos.data.find((x) => x.id === p.id) ?? null),
                  },
                  p.is_active
                    ? {
                        label: "Deactivate",
                        icon: Ban,
                        destructive: true,
                        onClick: () =>
                          confirmAction({
                            title: `Deactivate ${p.name}?`,
                            effect: "It stops applying to new orders. Orders that already used it keep their discount.",
                            destructive: true,
                            confirmLabel: "Deactivate",
                            onConfirm: () =>
                              void act(() => api("PATCH", `/promotions/${p.id}`, { body: { is_active: false } }), "Promotion deactivated", promos.reload),
                          }),
                      }
                    : {
                        label: "Activate",
                        icon: Check,
                        onClick: () =>
                          void act(() => api("PATCH", `/promotions/${p.id}`, { body: { is_active: true } }), "Promotion activated", promos.reload),
                      },
                ]
              : []
          }
          toForm={() => ({})}
        />
      )}
      {tab === "codes" && (
        <DataTable
          rows={codes}
          exportName="promotion-codes"
          emptyTitle="No codes. Use “Add code” on a promotion that applies with a code."
          columns={[
            { key: "code", header: "Code", render: (c) => <span className="font-mono">{c.code}</span> },
            { key: "promotion", header: "Promotion" },
            { key: "limit", header: "Used", align: "right" },
            { key: "max_uses_per_customer", header: "Per customer", align: "right", render: (c) => c.max_uses_per_customer ?? "—" },
            { key: "is_active", header: "Status", value: (c) => (c.is_active ? "Active" : "Inactive"), render: (c) => <StatusBadge status={c.is_active ? "Active" : "Inactive"} /> },
          ]}
          rowActions={(c) =>
            manage && c.is_active
              ? [
                  {
                    label: "Deactivate",
                    icon: Ban,
                    destructive: true,
                    onClick: () => void act(() => api("PATCH", `/promotion-codes/${c.id}/deactivate`), `${c.code} deactivated`, promos.reload),
                  },
                ]
              : []
          }
        />
      )}
      {tab === "reasons" && (
        <DataTable
          rows={reasons.data.map((r) => ({ ...r, kindLabel: r.kind }))}
          exportName="reason-codes"
          filters={[{ key: "kindLabel", label: "Used for" }]}
          columns={[
            { key: "kindLabel", header: "Used for" },
            { key: "code", header: "Code" },
            { key: "name_en", header: "Reason" },
            { key: "name_km", header: "Khmer", render: (r) => r.name_km ?? "—" },
          ]}
        />
      )}
      {tab === "limits" && (
        <>
          <Notice tone="info">Above these limits a manager must approve on the device. Change limits under Users &amp; roles.</Notice>
          <DataTable
            rows={roles.data}
            exportName="approval-limits"
            emptyTitle="You can't view roles"
            columns={[
              { key: "name", header: "Role" },
              ...limitKeys.map((k) => ({
                key: k,
                header: LIMIT_LABEL[k] ?? k,
                align: "right" as const,
                value: (r: (typeof roles.data)[number]) => num(r.limits[k]),
                render: (r: (typeof roles.data)[number]) => (r.limits[k] ? String(num(r.limits[k])) : "—"),
              })),
            ]}
          />
        </>
      )}
      {tab === "loyalty" && (
        <SettingsForm
          group="loyalty"
          title="Loyalty programme"
          description="Customers earn points on net sales and redeem them in fixed steps. Points expire after the set number of months."
          fields={[
            { name: "enabled", label: "Loyalty is on", type: "switch" },
            { name: "points_per_usd", label: "Points per 1 USD of net sales", type: "number", min: 0, required: true, half: true },
            { name: "redeem_step_points", label: "Points per redemption step", type: "number", min: 1, required: true, half: true, asNumber: true },
            { name: "redeem_step_value", label: "Value of one step (USD)", type: "number", min: 0, required: true, half: true },
            { name: "expiry_months", label: "Points expire after (months)", type: "number", min: 1, required: true, half: true, asNumber: true },
            { name: "earn_channels", label: "Channels that earn (comma separated)", list: true, hint: "POS, QR, Online, Platform" },
            { name: "earn_with_promotions", label: "Orders with promotions also earn", type: "switch" },
          ]}
        />
      )}
      <RecordDialog
        open={!!codeFor}
        onOpenChange={(o) => !o && setCodeFor(null)}
        title={`Add code to ${codeFor?.name ?? ""}`}
        description="Codes are not case-sensitive. Leave the limits empty for unlimited use."
        fields={[
          { name: "code", label: "Code", required: true, validate: (v) => (/^[A-Za-z0-9_-]{3,30}$/.test(String(v)) ? undefined : "3–30 letters, digits, - or _") },
          { name: "max", label: "Total uses", type: "number", min: 1, half: true },
          { name: "per", label: "Uses per customer", type: "number", min: 1, half: true },
        ]}
        onSubmit={(v) =>
          save(() =>
            api("POST", `/promotions/${codeFor!.id}/codes`, {
              body: { code: String(v.code), max_uses: v.max ? Number(v.max) : undefined, max_uses_per_customer: v.per ? Number(v.per) : undefined },
            })
          ).then(promos.reload)
        }
      />
    </Page>
  )
}
