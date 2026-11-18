"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { Ban, Bike, Check, CheckCheck, Eye, PackageCheck, Pause, Play, RotateCcw, UserPlus, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { CrudTable, RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { Notice, Page, PageHeader, PageTabs, Stat, StatusBadge, useTab } from "@/components/rms/kit"
import { SettingsForm } from "@/components/rms/settings-form"
import { api } from "@/lib/api/client"
import { can, useSession } from "@/lib/api/session"
import { act, num, save, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

interface Delivery {
  id: string
  order_id: string
  order_no: string
  zone_id: string | null
  address: string
  landmark: string | null
  phone: string | null
  fee: string
  status: string
  rider_user_id: string | null
  assigned_at: string | null
  out_at: string | null
  delivered_at: string | null
  failure_reason: string | null
  customer_name: string | null
  scheduled_at: string | null
  order_total: string
  amount_due: string
  kitchen_status: string
}
interface Zone {
  id: string
  name: string
  fee: string
  free_over: string | null
  min_order: string | null
  estimated_minutes: number | null
  is_active: boolean
}
interface PerfRow {
  key: string
  orders: number
  delivered: number
  failed: number
  late: number
  avg_prep_minutes: number | null
  avg_delivery_minutes: number | null
}

const STATUS: Record<string, string> = {
  PendingAssignment: "Pending Assignment",
  OutForDelivery: "Out for Delivery",
  InPreparation: "In Preparation",
  NotSent: "Not Sent",
  PartiallyReady: "Partially Ready",
}
const label = (s: string) => STATUS[s] ?? s

export default function DeliveryPage() {
  const router = useRouter()
  const { me } = useSession()
  const [tab, setTab] = useTab("delivery")
  const deliveries = useApi(() => api<Delivery[]>("GET", "/deliveries"), [], [])
  const takeaway = useApi(
    async () =>
      (
        await api<{ data: { id: string; order_no: string; pickup_name: string | null; kitchen_status: string; payment_status: string; grand_total: string; created_at: string }[] }>(
          "GET",
          "/orders",
          { query: { status: "Open", order_type: "Takeaway", page_size: 200 } }
        )
      ).data,
    [],
    []
  )
  const online = useApi(() => api<{ id: string; order_id: string; order_no: string; source: string; fulfilment: string; status: string; tracking_status: string; customer_name: string | null; customer_phone: string | null; scheduled_at: string | null; payment_mode: string; payment_status: string; total: string; created_at: string }[]>("GET", "/online-orders", { query: { status: "Received" } }), [], [])
  const platforms = useApi(
    () =>
      api<{ order_id: string; order_no: string; business_date: string; status: string; platform: string; platform_ref: string; order_total: string; commission_amount: string; net_expected: string; settlement_status: string; acceptance: string; platform_short_no: string | null; external_state: string | null; mismatch_note: string | null }[]>(
        "GET",
        "/platform-orders"
      ),
    [tab === "platforms"],
    []
  )
  const zones = useApi(() => api<Zone[]>("GET", "/delivery-zones"), [], [])
  const perf = useApi(() => api<{ by_rider: PerfRow[]; by_zone: PerfRow[]; by_platform: PerfRow[]; note: string }>("GET", "/deliveries/performance"), [tab === "performance"], null)
  const riders = useApi(
    async () => (can(me, "users.view") ? (await api<{ data: { id: string; full_name: string }[] }>("GET", "/users", { query: { role: "RIDER", status: "Active" } })).data : []),
    [me?.id],
    []
  )
  const onlineSettings = useApi(() => api<{ value: { enabled: boolean; paused: boolean } }>("GET", "/settings/online").then((r) => r.value), [], null)
  const [assignFor, setAssignFor] = React.useState<Delivery | null>(null)
  const reload = () => [deliveries, takeaway, online, platforms].forEach((x) => x.reload())
  const riderName = (id: string | null) => riders.data.find((r) => r.id === id)?.full_name ?? (id ? "Assigned rider" : "—")
  const zoneName = (id: string | null) => zones.data.find((z) => z.id === id)?.name ?? "—"
  const op = can(me, "delivery.manage") || can(me, "delivery.operate")
  const active = deliveries.data.filter((d) => !["Delivered", "Cancelled"].includes(d.status))

  return (
    <Page>
      <PageHeader
        title="Takeaway & delivery"
        description="Collection, own delivery, online and platform orders."
        actions={
          onlineSettings.data?.enabled &&
          can(me, "settings.manage") && (
            <Button
              variant="outline"
              onClick={() =>
                void act(
                  () => api("PUT", "/online-ordering/pause", { body: { paused: !onlineSettings.data!.paused } }),
                  onlineSettings.data!.paused ? "Online ordering resumed" : "Online ordering paused",
                  onlineSettings.reload
                )
              }
            >
              {onlineSettings.data.paused ? <Play /> : <Pause />}
              {onlineSettings.data.paused ? "Resume online orders" : "Pause online orders"}
            </Button>
          )
        }
      />
      {onlineSettings.data?.paused && <Notice tone="warning">Online ordering is paused. Customers see that the restaurant isn&apos;t taking orders.</Notice>}
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "takeaway", label: "Takeaway", count: takeaway.data.length },
          { value: "delivery", label: "Deliveries", count: active.length },
          { value: "online", label: "Online orders", count: online.data.length || undefined },
          { value: "platforms", label: "Platforms" },
          { value: "zones", label: "Delivery zones" },
          { value: "performance", label: "Performance" },
          { value: "settings", label: "Online settings" },
        ]}
      />
      {tab === "takeaway" && (
        <DataTable
          rows={takeaway.data.map((o) => ({ ...o, opened: when(o.created_at).slice(11), kitchen: label(o.kitchen_status), payment: label(o.payment_status) }))}
          exportName="takeaway"
          emptyTitle="No open takeaway orders"
          onRowClick={(o) => router.push(`/orders/${o.id}`)}
          columns={[
            { key: "order_no", header: "Order" },
            { key: "pickup_name", header: "Name", render: (o) => o.pickup_name ?? "—" },
            { key: "opened", header: "Opened" },
            { key: "kitchen", header: "Kitchen", render: (o) => <StatusBadge status={o.kitchen} /> },
            { key: "payment", header: "Payment", render: (o) => <StatusBadge status={o.payment} /> },
            { key: "grand_total", header: "Total", align: "right", render: (o) => usd(num(o.grand_total)) },
          ]}
          rowActions={(o) => [
            { label: "Open order", icon: Eye, onClick: () => router.push(`/pos?order=${o.id}`) },
            {
              label: "Mark collected",
              icon: PackageCheck,
              hidden: () => o.kitchen_status !== "Ready",
              onClick: () => void act(() => api("POST", `/orders/${o.id}/serve`, { body: {} }), `${o.order_no} collected`, reload),
            },
          ]}
        />
      )}
      {tab === "delivery" && (
        <DataTable
          rows={deliveries.data.map((d) => ({
            ...d,
            state: label(d.status),
            kitchen: label(d.kitchen_status),
            rider: riderName(d.rider_user_id),
            zone: zoneName(d.zone_id),
            due: num(d.amount_due),
          }))}
          exportName="deliveries"
          emptyTitle="No deliveries"
          filters={[{ key: "state", label: "Status" }]}
          columns={[
            { key: "order_no", header: "Order" },
            { key: "customer_name", header: "Customer", render: (d) => d.customer_name ?? "—" },
            { key: "address", header: "Address", render: (d) => `${d.address}${d.landmark ? ` (${d.landmark})` : ""}` },
            { key: "zone", header: "Zone" },
            { key: "kitchen", header: "Kitchen", render: (d) => <StatusBadge status={d.kitchen} /> },
            { key: "rider", header: "Rider" },
            { key: "due", header: "To collect", align: "right", render: (d) => usd(d.due) },
            { key: "state", header: "Status", render: (d) => <StatusBadge status={d.state} /> },
          ]}
          rowActions={(d) => [
            { label: d.rider_user_id ? "Change rider" : "Assign rider", icon: UserPlus, hidden: () => !can(me, "delivery.manage") || !["PendingAssignment", "Assigned"].includes(d.status), onClick: () => setAssignFor(d) },
            { label: "Out for delivery", icon: Bike, hidden: () => !op || d.status !== "Assigned", onClick: () => void act(() => api("POST", `/deliveries/${d.id}/out`), `${d.order_no} out for delivery`, reload) },
            { label: "Delivered", icon: CheckCheck, hidden: () => !op || d.status !== "OutForDelivery", onClick: () => void act(() => api("POST", `/deliveries/${d.id}/delivered`, { body: {} }), `${d.order_no} delivered`, reload) },
            {
              label: "Delivery failed",
              icon: X,
              destructive: true,
              hidden: () => !op || d.status !== "OutForDelivery",
              onClick: () =>
                confirmAction({
                  title: `Mark ${d.order_no} as failed?`,
                  effect: "A manager then sends it again or cancels the order.",
                  reasons: ["Customer not reachable", "Wrong address", "Customer refused", "Accident or breakdown"],
                  destructive: true,
                  confirmLabel: "Mark failed",
                  onConfirm: (reason) => void act(() => api("POST", `/deliveries/${d.id}/failed`, { body: { reason } }), "Delivery marked as failed", reload),
                }),
            },
            { label: "Send again", icon: RotateCcw, hidden: () => !can(me, "delivery.manage") || d.status !== "Failed", onClick: () => void act(() => api("POST", `/deliveries/${d.id}/redeliver`), `${d.order_no} queued again`, reload) },
          ]}
        />
      )}
      {tab === "online" && (
        <DataTable
          rows={online.data.map((o) => ({ ...o, placed: when(o.created_at).slice(11), pay: o.payment_mode === "PayLater" ? "Pay on collection or delivery" : `Online · ${o.payment_status === "Paid" ? "paid" : o.payment_status === "Failed" ? "failed" : "waiting"}`, when: o.scheduled_at ? when(o.scheduled_at) : "As soon as possible" }))}
          exportName="online-orders"
          emptyTitle="No online orders waiting"
          columns={[
            { key: "order_no", header: "Order" },
            { key: "source", header: "From" },
            { key: "fulfilment", header: "Type" },
            { key: "customer_name", header: "Customer", render: (o) => `${o.customer_name ?? ""} ${o.customer_phone ?? ""}` },
            { key: "placed", header: "Placed" },
            { key: "when", header: "Wanted" },
            { key: "pay", header: "Payment" },
            { key: "total", header: "Total", align: "right", render: (o) => usd(num(o.total)) },
          ]}
          rowActions={(o) => [
            { label: "Accept", icon: Check, hidden: () => !can(me, "orders.edit"), onClick: () => void act(() => api("POST", `/online-orders/${o.id}/accept`), `${o.order_no} accepted and sent to the kitchen`, reload) },
            {
              label: "Reject",
              icon: Ban,
              destructive: true,
              hidden: () => !can(me, "orders.cancel"),
              onClick: () =>
                confirmAction({
                  title: `Reject ${o.order_no}?`,
                  effect: "The customer is told. Any online payment is refunded.",
                  reasons: ["Too busy", "Item unavailable", "Outside delivery area", "Closing soon"],
                  destructive: true,
                  confirmLabel: "Reject",
                  onConfirm: (reason) => void act(() => api("POST", `/online-orders/${o.id}/reject`, { body: { reason } }), `${o.order_no} rejected`, reload),
                }),
            },
          ]}
        />
      )}
      {tab === "platforms" && (
        <>
          <section className="grid gap-3 sm:grid-cols-3">
            <Stat label="Platform orders" value={platforms.data.length} />
            <Stat label="Commission" value={usd(platforms.data.reduce((s, p) => s + num(p.commission_amount), 0))} />
            <Stat label="Not yet settled" value={platforms.data.filter((p) => p.settlement_status !== "Settled").length} />
          </section>
          <DataTable
            rows={platforms.data.map((p) => ({ ...p, id: p.order_id, ref: p.platform_short_no ?? p.platform_ref }))}
            exportName="platform-orders"
            emptyTitle="No platform orders"
            onRowClick={(p) => router.push(`/orders/${p.order_id}`)}
            columns={[
              { key: "order_no", header: "Order" },
              { key: "business_date", header: "Date" },
              { key: "platform", header: "Platform" },
              { key: "ref", header: "Reference" },
              { key: "order_total", header: "Total", align: "right", render: (p) => usd(num(p.order_total)) },
              { key: "commission_amount", header: "Commission", align: "right", render: (p) => usd(num(p.commission_amount)) },
              { key: "net_expected", header: "Net expected", align: "right", render: (p) => usd(num(p.net_expected)) },
              { key: "acceptance", header: "Accepted", render: (p) => <StatusBadge status={p.acceptance} /> },
              { key: "settlement_status", header: "Settlement", render: (p) => <StatusBadge status={p.settlement_status} /> },
            ]}
          />
        </>
      )}
      {tab === "zones" && (
        <CrudTable
          noun="Delivery zone"
          rows={zones.data.map((z) => ({ ...z, feeN: num(z.fee), status: z.is_active ? "Active" : "Inactive" }))}
          canAdd={can(me, "settings.manage")}
          canEdit={can(me, "settings.manage")}
          onSave={(v, e) => {
            const body = {
              fee: String(v.fee),
              free_over: v.free_over ? String(v.free_over) : null,
              min_order: v.min_order ? String(v.min_order) : null,
              estimated_minutes: v.minutes ? Number(v.minutes) : null,
              is_active: v.active !== false,
            }
            return save(() => (e ? api("PATCH", `/delivery-zones/${e.id}`, { body }) : api("POST", "/delivery-zones", { body: { ...body, name: v.name } }))).then(zones.reload)
          }}
          columns={[
            { key: "name", header: "Zone" },
            { key: "feeN", header: "Fee", align: "right", render: (z) => usd(z.feeN) },
            { key: "free_over", header: "Free over", align: "right", render: (z) => (z.free_over ? usd(num(z.free_over)) : "—") },
            { key: "min_order", header: "Minimum order", align: "right", render: (z) => (z.min_order ? usd(num(z.min_order)) : "—") },
            { key: "estimated_minutes", header: "Estimate", align: "right", render: (z) => (z.estimated_minutes ? `${z.estimated_minutes} min` : "—") },
            { key: "status", header: "Status", render: (z) => <StatusBadge status={z.status} /> },
          ]}
          fields={[
            { name: "name", label: "Zone name (can't change later)", required: true },
            { name: "fee", label: "Fee (USD)", type: "number", min: 0, required: true, half: true },
            { name: "free_over", label: "Free over (USD)", type: "number", min: 0, half: true },
            { name: "min_order", label: "Minimum order (USD)", type: "number", min: 0, half: true },
            { name: "minutes", label: "Estimated minutes", type: "number", min: 5, half: true },
            { name: "active", label: "Active", type: "switch" },
          ]}
          toForm={(z) => ({
            name: z.name,
            fee: String(num(z.fee)),
            free_over: z.free_over ? String(num(z.free_over)) : "",
            min_order: z.min_order ? String(num(z.min_order)) : "",
            minutes: z.estimated_minutes ? String(z.estimated_minutes) : "",
            active: z.is_active,
          })}
        />
      )}
      {tab === "performance" && (
        <>
          {perf.data && <Notice tone="info">{perf.data.note}</Notice>}
          {(["by_rider", "by_zone", "by_platform"] as const).map((k) => (
            <DataTable
              key={k}
              rows={(perf.data?.[k] ?? []).map((r) => ({ ...r, id: r.key }))}
              exportName={`delivery-${k}`}
              emptyTitle="No deliveries in this period"
              columns={[
                { key: "key", header: k === "by_rider" ? "Rider" : k === "by_zone" ? "Zone" : "Channel" },
                { key: "orders", header: "Orders", align: "right" },
                { key: "delivered", header: "Delivered", align: "right" },
                { key: "late", header: "Late", align: "right" },
                { key: "failed", header: "Failed", align: "right" },
                { key: "avg_prep_minutes", header: "Avg prep (min)", align: "right", render: (r) => r.avg_prep_minutes ?? "—" },
                { key: "avg_delivery_minutes", header: "Avg ride (min)", align: "right", render: (r) => r.avg_delivery_minutes ?? "—" },
              ]}
            />
          ))}
        </>
      )}
      {tab === "settings" && (
        <SettingsForm
          group="online"
          title="Online ordering"
          description="Online and QR ordering stay off until a manager turns them on."
          fields={[
            { name: "enabled", label: "Online ordering is on", type: "switch", half: true },
            { name: "auto_accept", label: "Accept orders automatically", type: "switch", half: true },
            { name: "pay_later_allowed", label: "Customers may pay on collection or delivery", type: "switch" },
            { name: "lead_minutes", label: "Earliest ready time (minutes)", type: "number", min: 0, asNumber: true, half: true },
            { name: "min_order", label: "Minimum order (USD)", type: "number", min: 0, half: true },
            { name: "max_qty_per_line", label: "Most of one item per order", type: "number", min: 1, asNumber: true, half: true },
            { name: "tracking_hours", label: "Tracking link valid for (hours)", type: "number", min: 1, asNumber: true, half: true },
          ]}
        />
      )}
      <RecordDialog
        open={!!assignFor}
        onOpenChange={(o) => !o && setAssignFor(null)}
        title={`Assign rider to ${assignFor?.order_no ?? ""}`}
        fields={[{ name: "rider", label: "Rider", type: "select", options: riders.data.map((r) => r.full_name), required: true }]}
        onSubmit={(v) => {
          const r = riders.data.find((x) => x.full_name === v.rider)
          if (!r) return Promise.reject(new Error("Choose a rider"))
          return save(() => api("POST", `/deliveries/${assignFor!.id}/assign`, { body: { rider_id: r.id } })).then(() => {
            toast.success(`${r.full_name} assigned`)
            reload()
          })
        }}
      />
    </Page>
  )
}
