"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  CircleDollarSign,
  Eye,
  Printer,
  RotateCcw,
  ShieldCheck,
  Undo2,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  MoneyText,
  Notice,
  Page,
  PageHeader,
  PageTabs,
  Stat,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { ReconciliationTab } from "@/components/rms/operations"
import { PaymentDialog } from "@/components/rms/pos-dialogs"
import * as billing from "@/lib/api/billing"
import { refreshOrder, report, withApproval } from "@/lib/api/pos"
import { can, useSession } from "@/lib/api/session"
import { khr, usd } from "@/lib/rms/billing"

const money = (cur: string, v: number) => (cur === "KHR" ? khr(v) : usd(v))

export default function BillingPage() {
  const router = useRouter()
  const { me } = useSession()
  const day = me?.business_date
  const canRefund = can(me, "refunds.request")
  const canDecide = can(me, "refunds.approve")
  const [tab, setTab] = useTab("bills")
  const [pay, setPay] = React.useState<string | null>(null)
  const [refundFor, setRefundFor] = React.useState<billing.PaymentRow | null>(null)
  const [orders, setOrders] = React.useState<billing.OrderRow[]>([])
  const [payments, setPayments] = React.useState<billing.PaymentRow[]>([])
  const [refunds, setRefunds] = React.useState<billing.RefundRow[]>([])

  /** Everything on this page is read from the server for the current business day. */
  const reload = React.useCallback(() => {
    if (!day) return
    Promise.all([billing.listOrders(day), billing.listPayments(day), billing.listRefunds()]).then(([o, p, r]) => {
      setOrders(o)
      setPayments(p)
      setRefunds(r)
    }, report)
  }, [day])
  React.useEffect(reload, [reload])

  const run = (fn: () => Promise<unknown>, done: string) =>
    fn().then(() => {
      toast.success(done)
      reload()
    }, report)

  const confirmed = payments.filter((p) => p.state === "Confirmed")
  const collected = confirmed.reduce((s, p) => s + p.base, 0)
  const receipts = [...new Map(payments.filter((p) => p.receipt !== "—").map((p) => [p.receipt, p])).values()]

  return (
    <Page>
      <PageHeader
        title="Bills & payments"
        description={`Orders, bills, payments, refunds and receipts are separate records. Finalised records are never edited.${day ? ` Business day ${day}.` : ""}`}
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "bills", label: "Bills", count: orders.length },
          { value: "payments", label: "Payments", count: payments.length },
          { value: "receipts", label: "Receipts" },
          {
            value: "refunds",
            label: "Refunds",
            count: refunds.filter((r) => r.status === "Requested").length,
          },
          { value: "reconciliation", label: "Reconciliation" },
        ]}
      />
      {tab === "bills" && (
        <DataTable
          rows={orders}
          pageSize={12}
          exportName="bills"
          onRowClick={(o) => router.push(`/orders/${o.id}`)}
          filters={[
            {
              key: "payment",
              label: "Payment",
              options: ["Unpaid", "Partially Paid", "Paid"],
            },
          ]}
          columns={[
            {
              key: "no",
              header: "Order",
              render: (o) => <span className="font-medium">{o.no}</span>,
            },
            { key: "where", header: "Table / pickup" },
            { key: "created", header: "Opened" },
            { key: "status", header: "Order", render: (o) => <StatusBadge status={o.status} /> },
            {
              key: "total",
              header: "Total",
              align: "right",
              render: (o) => <MoneyText value={o.total} dual />,
            },
            {
              key: "payment",
              header: "Payment",
              render: (o) => <StatusBadge status={o.payment} />,
            },
          ]}
          rowActions={(o) => [
            {
              label: "View order",
              icon: Eye,
              onClick: () => router.push(`/orders/${o.id}`),
            },
            {
              label: "Take payment",
              icon: CircleDollarSign,
              hidden: () => o.payment === "Paid" || o.status !== "Open",
              // The payment dialog works on the order held in the store, so load it first.
              onClick: () => refreshOrder(o.id).then(() => setPay(o.id), report),
            },
          ]}
        />
      )}
      {tab === "payments" && (
        <>
          <section className="grid gap-3 sm:grid-cols-3">
            <Stat label="Collected today" value={usd(collected)} hint="Collections, not sales" />
            <Stat
              label="Pending electronic"
              value={payments.filter((p) => p.state === "Pending").length}
              tone="warning"
            />
            <Stat label="Failed or voided" value={payments.filter((p) => p.state === "Failed" || p.state === "Voided").length} />
          </section>
          <DataTable
            rows={payments}
            exportName="payments"
            filters={[
              { key: "method", label: "Method" },
              {
                key: "state",
                label: "State",
                options: ["Confirmed", "Pending", "Failed", "Voided"],
              },
            ]}
            columns={[
              { key: "time", header: "Time" },
              { key: "billNo", header: "Bill" },
              { key: "method", header: "Method" },
              {
                key: "tendered",
                header: "Tendered",
                align: "right",
                render: (p) => money(p.currency, p.tendered),
              },
              {
                key: "base",
                header: "Applied (USD)",
                align: "right",
                render: (p) => usd(p.base),
              },
              {
                key: "change",
                header: "Change",
                align: "right",
                render: (p) => (p.change ? money(p.changeCurrency, p.change) : "—"),
              },
              { key: "receipt", header: "Receipt" },
              {
                key: "state",
                header: "State",
                render: (p) => <StatusBadge status={p.state} />,
              },
            ]}
            rowActions={(p) => [
              {
                label: "Void payment",
                icon: X,
                destructive: true,
                hidden: () => p.state !== "Confirmed" || p.billStatus === "Paid",
                onClick: () =>
                  confirmAction({
                    title: "Void this payment?",
                    effect:
                      "Only unfinalised payments in the same session can be voided. A reversal record is created.",
                    requireReason: true,
                    destructive: true,
                    confirmLabel: "Void",
                    onConfirm: (reason) =>
                      void run(
                        () => withApproval(`Void ${p.method} payment on ${p.billNo}`, (approvalId) => billing.voidPayment(p.id, reason, approvalId)),
                        "Payment voided"
                      ),
                  }),
              },
              {
                label: "Request refund",
                icon: RotateCcw,
                hidden: () => p.state !== "Confirmed" || !canRefund,
                onClick: () => setRefundFor(p),
              },
            ]}
          />
        </>
      )}
      {tab === "receipts" && (
        <DataTable
          rows={receipts}
          exportName="receipts"
          emptyTitle="No receipts today"
          columns={[
            { key: "receipt", header: "Receipt" },
            { key: "billNo", header: "Bill" },
            { key: "time", header: "Time" },
            { key: "method", header: "Last payment" },
          ]}
          rowActions={(p) => [
            {
              label: "Reprint (COPY)",
              icon: Printer,
              onClick: () =>
                billing.reprintReceipt(p.billId).then((r) => toast.success(`${r.receipt_no} reprint queued, marked ${r.label}`), report),
            },
          ]}
        />
      )}
      {tab === "refunds" && (
        <DataTable
          rows={refunds}
          exportName="refunds"
          emptyTitle="No refunds"
          columns={[
            { key: "refundNo", header: "Refund" },
            { key: "created", header: "Requested" },
            { key: "method", header: "Original payment" },
            {
              key: "amount",
              header: "Amount",
              align: "right",
              render: (r) => money(r.currency, r.amount),
            },
            { key: "reason", header: "Reason" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          rowActions={(r) => [
            {
              label: "Approve",
              icon: ShieldCheck,
              hidden: () => !canDecide || r.status !== "Requested",
              onClick: () =>
                confirmAction({
                  title: `Approve ${r.refundNo}?`,
                  effect: `${money(r.currency, r.amount)} goes back by ${r.method}. Approval is recorded under your name.`,
                  confirmLabel: "Approve refund",
                  onConfirm: () => void run(() => billing.decideRefund(r.id, true), `${r.refundNo} approved`),
                }),
            },
            {
              label: "Reject",
              icon: Undo2,
              destructive: true,
              hidden: () => !canDecide || r.status !== "Requested",
              onClick: () =>
                confirmAction({
                  title: `Reject ${r.refundNo}?`,
                  effect: "The requester is notified.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Reject",
                  onConfirm: (note) => void run(() => billing.decideRefund(r.id, false, note), `${r.refundNo} rejected`),
                }),
            },
          ]}
        />
      )}
      {tab === "reconciliation" &&
        (can(me, "payments.reconcile") ? (
          <ReconciliationTab />
        ) : (
          <Notice tone="info">Reconciling payments with bank statements needs the accountant or a manager. GrabFood payouts are reconciled under Delivery.</Notice>
        ))}
      <RecordDialog
        open={!!refundFor}
        onOpenChange={(o) => !o && setRefundFor(null)}
        title="Request refund"
        description={refundFor ? `${refundFor.method} payment on ${refundFor.billNo}, ${usd(refundFor.base)} applied. A manager approves it.` : ""}
        fields={[
          { name: "amount", label: "Amount (USD)", type: "number", min: 0.01, required: true },
          { name: "reason", label: "Reason", required: true },
        ]}
        initial={{ amount: String(refundFor?.base ?? "") }}
        onSubmit={(v) => {
          const p = refundFor
          if (p) void run(() => billing.requestRefund(p.id, Number(v.amount), String(v.reason)), "Refund requested")
        }}
      />
      {pay && (
        <PaymentDialog
          orderId={pay}
          open
          onClose={() => {
            setPay(null)
            reload()
          }}
        />
      )}
    </Page>
  )
}
