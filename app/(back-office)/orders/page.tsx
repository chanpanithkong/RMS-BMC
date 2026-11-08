"use client"

import { useRouter, useSearchParams } from "next/navigation"
import { Eye, Monitor, XCircle } from "lucide-react"
import { toast } from "sonner"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  LinkButton,
  MoneyText,
  Page,
  PageHeader,
  StatusBadge,
} from "@/components/rms/kit"
import { calcBill, kitchenStatus, paymentStatus } from "@/lib/rms/billing"
import { rms, useRms } from "@/lib/rms/store"
import type { Order } from "@/lib/rms/types"

const typeLabel = {
  DINE_IN: "Dine-in",
  TAKEAWAY: "Takeaway",
  DELIVERY: "Delivery",
} as const
const statuses = ["Draft", "Open", "Completed", "Cancelled"]
const reasons = [
  "Customer left",
  "Duplicate order",
  "Entered in error",
  "Kitchen unable to fulfil",
]

export default function OrdersPage() {
  const { orders } = useRms()
  const router = useRouter()
  const q = useSearchParams().get("q") ?? ""
  return (
    <Page>
      <PageHeader
        title="Orders"
        description="Every dine-in, takeaway, delivery and online order, with separate order, kitchen and payment status."
        actions={
          <LinkButton href="/pos">
            <Monitor />
            Open POS
          </LinkButton>
        }
      />
      <DataTable<Order>
        key={q}
        rows={orders}
        initialQuery={q}
        pageSize={12}
        exportName="orders"
        searchPlaceholder="Number, table, customer…"
        onRowClick={(o) => router.push(`/orders/${o.id}`)}
        searchValue={(o) =>
          `${o.no} ${o.table ?? ""} ${o.customer ?? ""} ${o.pickup ?? ""} ${o.delivery?.phone ?? ""} ${o.server}`
        }
        filters={[
          { key: "status", label: "Status", options: statuses },
          {
            key: "type",
            label: "Type",
            options: Object.values(typeLabel),
            value: (o) => typeLabel[o.type],
          },
          { key: "server", label: "Server" },
          {
            key: "payment",
            label: "Payment",
            options: ["Unpaid", "Partially Paid", "Paid"],
            value: paymentStatus,
          },
        ]}
        columns={[
          {
            key: "no",
            header: "Order",
            render: (o) => <span className="font-medium">{o.no}</span>,
          },
          { key: "type", header: "Type", value: (o) => typeLabel[o.type] },
          {
            key: "where",
            header: "Table / pickup",
            value: (o) => o.table ?? o.pickup ?? o.customer ?? "—",
          },
          { key: "channel", header: "Channel", hidden: true },
          { key: "guests", header: "Guests", align: "right", hidden: true },
          { key: "server", header: "Server" },
          {
            key: "status",
            header: "Order",
            render: (o) => <StatusBadge status={o.held ? "Held" : o.status} />,
          },
          {
            key: "kitchen",
            header: "Kitchen",
            value: kitchenStatus,
            render: (o) => (
              <StatusBadge
                status={kitchenStatus(o)}
                tone={
                  kitchenStatus(o) === "In Progress"
                    ? "info"
                    : kitchenStatus(o) === "Not Sent"
                      ? "neutral"
                      : "success"
                }
              />
            ),
          },
          {
            key: "payment",
            header: "Payment",
            value: paymentStatus,
            render: (o) => <StatusBadge status={paymentStatus(o)} />,
          },
          {
            key: "total",
            header: "Total",
            align: "right",
            value: (o) => calcBill(o).total,
            render: (o) => <MoneyText value={calcBill(o).total} />,
          },
        ]}
        rowActions={() => [
          {
            label: "View details",
            icon: Eye,
            onClick: (o) => router.push(`/orders/${o.id}`),
          },
          {
            label: "Open in POS",
            icon: Monitor,
            onClick: (o) => router.push(`/pos?order=${o.id}`),
            hidden: (o) => o.status === "Completed" || o.status === "Cancelled",
          },
          {
            label: "Cancel order",
            icon: XCircle,
            destructive: true,
            hidden: (o) =>
              o.status === "Completed" ||
              o.status === "Cancelled" ||
              calcBill(o).paid > 0,
            onClick: (o) =>
              confirmAction({
                title: `Cancel ${o.no}?`,
                effect:
                  "All remaining items are cancelled and the kitchen is notified. This can't be undone.",
                reasons,
                destructive: true,
                confirmLabel: "Cancel order",
                onConfirm: (r) => {
                  rms.cancelOrder(o.id, r)
                  toast.success(`${o.no} cancelled`)
                },
              }),
          },
        ]}
      />
    </Page>
  )
}
