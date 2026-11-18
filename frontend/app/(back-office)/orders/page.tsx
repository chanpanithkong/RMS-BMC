"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Ban, Eye, Monitor } from "lucide-react"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { LinkButton, MoneyText, Page, PageHeader, StatusBadge } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { report, withApproval } from "@/lib/api/pos"
import { can, useSession } from "@/lib/api/session"
import { act, num, useApi, when } from "@/lib/api/use-api"

const TYPE: Record<string, string> = { DineIn: "Dine-in", Takeaway: "Takeaway", Delivery: "Delivery" }
const LABEL: Record<string, string> = { NotSent: "Not Sent", InProgress: "In Progress", PartiallyReady: "Partially Ready", PartiallyPaid: "Partially Paid" }
const label = (s: string) => LABEL[s] ?? s
const reasons = ["Customer left", "Duplicate order", "Entered in error", "Kitchen unable to fulfil"]

interface Summary {
  id: string
  order_no: string
  business_date: string
  order_type: string
  order_status: string
  kitchen_status: string
  payment_status: string
  table_code: string | null
  pickup_name: string | null
  grand_total: string
  created_at: string
  held_label: string | null
}

function OrdersScreen() {
  const router = useRouter()
  const { me } = useSession()
  const q = useSearchParams().get("q") ?? ""
  const [day, setDay] = React.useState("")
  const shownDay = day || me?.business_date || ""
  const list = useApi(
    async () =>
      (await api<{ data: Summary[] }>("GET", "/orders", { query: { business_date: q ? undefined : shownDay || undefined, q: q || undefined, page_size: 200 } })).data,
    [shownDay, q],
    []
  )
  const rows = list.data.map((o) => ({
    ...o,
    type: TYPE[o.order_type] ?? o.order_type,
    where: o.table_code ? `Table ${o.table_code}` : (o.pickup_name ?? "—"),
    time: when(o.created_at).slice(11),
    kitchen: label(o.kitchen_status),
    payment: label(o.payment_status),
    total: num(o.grand_total),
  }))

  return (
    <Page>
      <PageHeader
        title="Orders"
        description={q ? `Search results for “${q}” across all days.` : "Every dine-in, takeaway, delivery and online order, with separate order, kitchen and payment status."}
        actions={
          <>
            {!q && (
              <input
                type="date"
                aria-label="Business day"
                className="h-9 rounded-md border bg-transparent px-2 text-sm"
                value={shownDay}
                onChange={(e) => setDay(e.target.value)}
              />
            )}
            <LinkButton href="/pos">
              <Monitor />
              Open POS
            </LinkButton>
          </>
        }
      />
      <DataTable
        rows={rows}
        exportName="orders"
        pageSize={14}
        emptyTitle={list.loading ? "Loading…" : "No orders"}
        onRowClick={(o) => router.push(`/orders/${o.id}`)}
        searchValue={(o) => `${o.order_no} ${o.where}`}
        filters={[
          { key: "order_status", label: "Status", options: ["Draft", "Open", "Completed", "Cancelled"] },
          { key: "type", label: "Type", options: Object.values(TYPE) },
          { key: "payment", label: "Payment", options: ["Unpaid", "Partially Paid", "Paid"] },
        ]}
        columns={[
          { key: "order_no", header: "Order", render: (o) => <span className="font-medium">{o.order_no}</span> },
          { key: "time", header: "Opened" },
          { key: "type", header: "Type" },
          { key: "where", header: "Table / name" },
          { key: "order_status", header: "Order", render: (o) => <StatusBadge status={o.held_label ? "Held" : o.order_status} /> },
          { key: "kitchen", header: "Kitchen", render: (o) => <StatusBadge status={o.kitchen} /> },
          { key: "payment", header: "Payment", render: (o) => <StatusBadge status={o.payment} /> },
          { key: "total", header: "Total", align: "right", render: (o) => <MoneyText value={o.total} /> },
        ]}
        rowActions={(o) => [
          { label: "View details", icon: Eye, onClick: () => router.push(`/orders/${o.id}`) },
          { label: "Open in POS", icon: Monitor, hidden: () => !["Open", "Draft"].includes(o.order_status), onClick: () => router.push(`/pos?order=${o.id}`) },
          {
            label: "Cancel order",
            icon: Ban,
            destructive: true,
            hidden: () => !["Open", "Draft"].includes(o.order_status) || !can(me, "orders.cancel"),
            onClick: () =>
              confirmAction({
                title: `Cancel order ${o.order_no}?`,
                effect: "Orders with payments can't be cancelled; refund first. Sent items are recorded as voids.",
                reasons,
                destructive: true,
                confirmLabel: "Cancel order",
                onConfirm: (reason) =>
                  void act(
                    () => withApproval(`Cancel order ${o.order_no}`, (approval_id) => api("POST", `/orders/${o.id}/cancel`, { body: { reason, approval_id } })),
                    `Order ${o.order_no} cancelled`,
                    list.reload
                  ).catch(report),
              }),
          },
        ]}
      />
    </Page>
  )
}

export default function OrdersPage() {
  return (
    <React.Suspense>
      <OrdersScreen />
    </React.Suspense>
  )
}
