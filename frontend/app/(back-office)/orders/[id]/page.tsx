"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import { BellRing, CircleDollarSign, Monitor, ReceiptText, Undo2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { EmptyState, KV, LinkButton, MoneyText, Page, PageHeader, Panel, StatusBadge } from "@/components/rms/kit"
import { PaymentDialog } from "@/components/rms/pos-dialogs"
import { api } from "@/lib/api/client"
import { refreshOrder, serveAll } from "@/lib/api/pos"
import { act, apiMessage, num, useApi, when } from "@/lib/api/use-api"
import { calcBill, khr, kitchenStatus, lineGross, paymentStatus, toKhr, usd } from "@/lib/rms/billing"
import { useRms } from "@/lib/rms/store"

const EVENT: Record<string, string> = {
  created: "Order created",
  item_added: "Item added",
  item_updated: "Item changed",
  item_cancelled: "Item cancelled",
  item_status: "Kitchen status changed",
  sent: "Sent to kitchen",
  ticket_bumped: "Ticket bumped",
  ticket_recalled: "Ticket recalled",
  served: "Served",
  transferred: "Moved to another table",
  discount_applied: "Discount applied",
  promotions_changed: "Promotions updated",
  customer_attached: "Customer attached",
  loyalty_redeemed: "Loyalty points redeemed",
  qr_items_added: "Items added by QR",
  bill_printed: "Bill printed",
  billed: "Bill created",
  payment: "Payment recorded",
  refund: "Refund",
  completed: "Completed",
  cancelled: "Order cancelled",
}

interface Bill {
  id: string
  bill_no: string
  status: string
  total: string
  paid_total: string
  balance: string
  receipt_no: string | null
  split_index: number
  split_count: number
}

async function load(id: string) {
  const [, bills, events] = await Promise.all([
    refreshOrder(id),
    api<Bill[]>("GET", `/orders/${id}/bills`).catch(() => []),
    api<{ id: string; event_type: string; data: Record<string, unknown> | null; occurred_at: string }[]>("GET", `/orders/${id}/timeline`).catch(() => []),
  ])
  return { bills, events }
}

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { orders } = useRms()
  const [pay, setPay] = React.useState(false)
  const { data, loading, reload } = useApi(() => load(id).catch(() => null), [id], null)
  const o = orders.find((x) => x.id === id)
  if (loading) return <Page><PageHeader title="Order" description="Loading…" /></Page>
  if (!o || !data)
    return (
      <Page>
        <EmptyState title="Order not found" description="It may belong to another branch." action={<LinkButton href="/orders">Back to orders</LinkButton>} />
      </Page>
    )
  const t = calcBill(o)
  const closed = o.status === "Completed" || o.status === "Cancelled"
  return (
    <Page>
      <PageHeader
        title={`Order ${o.no}`}
        description={`${o.type.replace("_", " ").toLowerCase()} · ${o.channel} · ${o.table ? `Table ${o.table}` : (o.pickup ?? o.customer ?? "")}${o.guests ? ` · ${o.guests} guest(s)` : ""} · ${o.business}`}
        actions={
          <>
            {!closed && (
              <LinkButton href={`/pos?order=${o.id}`} variant="outline">
                <Monitor />
                Open in POS
              </LinkButton>
            )}
            {!closed && o.lines.some((l) => l.status === "Ready") && (
              <Button variant="outline" onClick={() => void act(() => serveAll(o.id), "Ready items handed over", reload)}>
                <BellRing />
                Mark {o.type === "DINE_IN" ? "served" : "collected"}
              </Button>
            )}
            {!closed && t.balance > 0 && (
              <Button onClick={() => setPay(true)}>
                <CircleDollarSign />
                Take payment
              </Button>
            )}
            {t.paid > 0 && (
              <LinkButton href="/billing?tab=payments" variant="outline">
                <Undo2 />
                Refund from payments
              </LinkButton>
            )}
          </>
        }
      />
      <div className="flex flex-wrap gap-2 text-sm">
        <span className="flex items-center gap-1.5">
          Order <StatusBadge status={o.held ? "Held" : o.status} />
        </span>
        <span className="flex items-center gap-1.5">
          Kitchen <StatusBadge status={kitchenStatus(o)} tone={kitchenStatus(o) === "In Progress" ? "info" : kitchenStatus(o) === "Not Sent" ? "neutral" : "success"} />
        </span>
        <span className="flex items-center gap-1.5">
          Payment <StatusBadge status={paymentStatus(o)} />
        </span>
      </div>
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
        <Panel title="Items" className="lg:col-span-2">
          <ul className="divide-y">
            {o.lines.map((l) => (
              <li key={l.id} className="flex items-start justify-between gap-3 py-2 text-sm">
                <div className="min-w-0">
                  <p className={l.status === "Cancelled" ? "line-through opacity-60" : "font-medium"}>
                    {l.qty} × {l.name}
                    {l.variant && ` (${l.variant})`} <span className="font-normal text-muted-foreground">{l.km}</span>
                  </p>
                  {l.modifiers.length > 0 && (
                    <p className="text-xs text-muted-foreground">{l.modifiers.map((m) => (m.delta ? `${m.name} +${usd(m.delta)}` : m.name)).join(", ")}</p>
                  )}
                  {l.note && <p className={l.allergy ? "text-xs font-semibold text-danger" : "text-xs text-warning"}>{l.note}</p>}
                  {l.voidReason && (
                    <p className="text-xs text-danger">
                      {l.voidType}: {l.voidReason}
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">{l.station === "None" ? "No kitchen routing" : `${l.station} station`}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="tabular font-medium">{usd(lineGross(l))}</span>
                  <StatusBadge status={l.status} />
                </div>
              </li>
            ))}
          </ul>
        </Panel>
        <div className="grid gap-4">
          <Panel title="Totals">
            <KV
              className="tabular"
              items={[
                ["Gross", usd(t.gross)],
                ["Discounts", `−${usd(t.itemDiscounts + t.orderDiscount)}`],
                ["Subtotal", usd(t.subtotal)],
                ["Service charge", usd(t.service)],
                ["Tax", usd(t.tax)],
                ...(t.deliveryFee ? [["Delivery fee", usd(t.deliveryFee)] as [string, string]] : []),
                ["Total", <MoneyText key="t" value={t.total} className="font-bold" />],
                ["Total KHR", khr(toKhr(t.total))],
                ["Paid", usd(t.paid)],
                ["Balance", <span key="b" className="font-bold">{usd(t.balance)}</span>],
              ]}
            />
            <p className="mt-2 text-xs text-muted-foreground">Calculated by the server from the configured tax and service rules.</p>
          </Panel>
          {data.bills.length > 0 && (
            <Panel title="Bills">
              <ul className="divide-y text-sm">
                {data.bills.map((b) => (
                  <li key={b.id} className="flex items-center justify-between gap-2 py-1.5">
                    <span>
                      {b.bill_no}
                      {b.split_count > 1 && ` (${b.split_index}/${b.split_count})`}
                      {b.receipt_no && <span className="block text-xs text-muted-foreground">Receipt {b.receipt_no}</span>}
                    </span>
                    <span className="flex items-center gap-2">
                      <MoneyText value={num(b.total)} />
                      <StatusBadge status={b.status} />
                      {b.receipt_no && (
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label={`Reprint ${b.receipt_no}`}
                          onClick={() =>
                            api<{ receipt_no: string; label: string }>("POST", `/bills/${b.id}/receipt/reprint`).then(
                              (r) => toast.success(`${r.receipt_no} reprint queued, marked ${r.label}`),
                              (e) => toast.error(apiMessage(e))
                            )
                          }
                        >
                          <ReceiptText />
                        </Button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title="Timeline">
            {data.events.length === 0 ? (
              <p className="text-sm text-muted-foreground">No events recorded.</p>
            ) : (
              <ol className="relative space-y-3 border-l pl-4 text-sm">
                {[...data.events].reverse().map((e) => (
                  <li key={e.id}>
                    <span className="absolute -left-1 mt-1.5 size-2 rounded-full bg-primary" />
                    <p className="font-medium">{EVENT[e.event_type] ?? e.event_type}</p>
                    <p className="text-xs text-muted-foreground">{when(e.occurred_at)}</p>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      </div>
      <PaymentDialog
        orderId={o.id}
        open={pay}
        onClose={() => {
          setPay(false)
          reload()
        }}
      />
    </Page>
  )
}
