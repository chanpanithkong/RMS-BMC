"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import {
  BellRing,
  CircleDollarSign,
  Monitor,
  ReceiptText,
  Undo2,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { confirmAction, requestApproval } from "@/components/rms/dialog-host"
import {
  EmptyState,
  KV,
  LinkButton,
  MoneyText,
  Page,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/rms/kit"
import { PaymentDialog } from "@/components/rms/pos-dialogs"
import {
  calcBill,
  khr,
  kitchenStatus,
  lineGross,
  paymentStatus,
  toKhr,
  usd,
} from "@/lib/rms/billing"
import { minLabel, rms, useClock, useRms } from "@/lib/rms/store"

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { orders } = useRms()
  const at = useClock()
  const [pay, setPay] = React.useState(false)
  const o = orders.find((x) => x.id === id)
  if (!o)
    return (
      <Page>
        <EmptyState
          title="Order not found"
          description="It may belong to another branch."
          action={<LinkButton href="/orders">Back to orders</LinkButton>}
        />
      </Page>
    )
  const t = calcBill(o)
  const closed = o.status === "Completed" || o.status === "Cancelled"
  return (
    <Page>
      <PageHeader
        title={`Order ${o.no}`}
        description={`${o.type.replace("_", " ")} · ${o.channel} · ${o.table ? `Table ${o.table}` : (o.pickup ?? o.customer ?? "")} · ${o.guests} guest(s) · Server ${o.server}`}
        actions={
          <>
            {!closed && (
              <LinkButton href={`/pos?order=${o.id}`} variant="outline">
                <Monitor />
                Open in POS
              </LinkButton>
            )}
            {!closed && o.lines.some((l) => l.status === "Ready") && (
              <Button
                variant="outline"
                onClick={() => {
                  rms.serveAll(o.id)
                  toast.success("Ready items handed over")
                }}
              >
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
              <Button
                variant="outline"
                onClick={() =>
                  confirmAction({
                    title: "Request refund",
                    effect: `Refund of up to ${usd(t.paid)} against the original payment. It goes to a manager for approval.`,
                    reasons: [
                      "Quality issue",
                      "Wrong order",
                      "Overcharged",
                      "Customer complaint",
                    ],
                    confirmLabel: "Request approval",
                    onConfirm: (r) =>
                      requestApproval({
                        action: `Refund on ${o.no}`,
                        amount: usd(t.paid),
                        reason: r,
                        onApproved: (by) =>
                          toast.success(`Refund approved by ${by}`),
                      }),
                  })
                }
              >
                <Undo2 />
                Request refund
              </Button>
            )}
            {o.receiptNo && (
              <Button
                variant="outline"
                onClick={() =>
                  toast.success(`Reprint of ${o.receiptNo} queued, marked COPY`)
                }
              >
                <ReceiptText />
                Reprint receipt
              </Button>
            )}
          </>
        }
      />
      <div className="flex flex-wrap gap-2 text-sm">
        <span className="flex items-center gap-1.5">
          Order <StatusBadge status={o.status} />
        </span>
        <span className="flex items-center gap-1.5">
          Kitchen{" "}
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
        </span>
        <span className="flex items-center gap-1.5">
          Payment <StatusBadge status={paymentStatus(o)} />
        </span>
        {o.receiptNo && (
          <span className="tabular text-muted-foreground">
            Receipt {o.receiptNo}
          </span>
        )}
      </div>
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
        <Panel title="Items" className="lg:col-span-2">
          <ul className="divide-y">
            {o.lines.map((l) => (
              <li
                key={l.id}
                className="flex items-start justify-between gap-3 py-2 text-sm"
              >
                <div className="min-w-0">
                  <p
                    className={
                      l.status === "Cancelled"
                        ? "line-through opacity-60"
                        : "font-medium"
                    }
                  >
                    {l.qty} × {l.name}
                    {l.variant && ` (${l.variant})`}{" "}
                    <span className="font-normal text-muted-foreground">
                      {l.km}
                    </span>
                  </p>
                  {l.modifiers.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      {l.modifiers
                        .map((m) =>
                          m.delta ? `${m.name} +${usd(m.delta)}` : m.name
                        )
                        .join(", ")}
                    </p>
                  )}
                  {l.note && (
                    <p
                      className={
                        l.allergy
                          ? "text-xs font-semibold text-danger"
                          : "text-xs text-warning"
                      }
                    >
                      {l.note}
                    </p>
                  )}
                  {l.voidReason && (
                    <p className="text-xs text-danger">
                      {l.voidType}: {l.voidReason}
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {l.station === "None"
                      ? "No kitchen routing"
                      : `${l.station} station`}
                    {l.sentAt !== undefined &&
                      ` · sent ${minLabel(at - l.sentAt)} ago`}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="tabular font-medium">
                    {usd(lineGross(l))}
                  </span>
                  <StatusBadge status={l.status} />
                </div>
              </li>
            ))}
          </ul>
        </Panel>
        <div className="grid gap-4">
          <Panel title="Bill">
            <KV
              className="tabular"
              items={[
                ["Gross", usd(t.gross)],
                ["Item discounts", `−${usd(t.itemDiscounts)}`],
                ["Order discount", `−${usd(t.orderDiscount)}`],
                ["Discounted subtotal", usd(t.subtotal)],
                ["Service charge (5%)", usd(t.service)],
                ["Tax (10%)", usd(t.tax)],
                ...(t.deliveryFee
                  ? [["Delivery fee", usd(t.deliveryFee)] as [string, string]]
                  : []),
                [
                  "Total",
                  <MoneyText key="t" value={t.total} className="font-bold" />,
                ],
                ["Total KHR", khr(toKhr(t.total))],
                ["Paid", usd(t.paid)],
                [
                  "Balance",
                  <span key="b" className="font-bold">
                    {usd(t.balance)}
                  </span>,
                ],
              ]}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Rates are illustrative, pending verification (V-01).
            </p>
          </Panel>
          {o.payments.length > 0 && (
            <Panel title="Payments">
              <ul className="divide-y text-sm">
                {o.payments.map((p) => (
                  <li key={p.id} className="flex justify-between py-1.5">
                    <span>
                      {p.method}{" "}
                      <span className="text-xs text-muted-foreground">
                        {p.time}
                      </span>
                    </span>
                    <MoneyText value={p.applied} />
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title="Timeline">
            <ol className="relative space-y-3 border-l pl-4 text-sm">
              {[...o.timeline].reverse().map((e, i) => (
                <li key={i}>
                  <span className="absolute -left-1 mt-1.5 size-2 rounded-full bg-primary" />
                  <p className="font-medium">{e.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {e.user} · {e.time ?? `${minLabel(at - e.at)} ago`}
                  </p>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
      <PaymentDialog orderId={o.id} open={pay} onClose={() => setPay(false)} />
    </Page>
  )
}
