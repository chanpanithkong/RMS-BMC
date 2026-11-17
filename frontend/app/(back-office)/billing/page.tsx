"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  CircleDollarSign,
  Eye,
  Printer,
  ShieldCheck,
  Undo2,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction, requestApproval } from "@/components/rms/dialog-host"
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
import { PaymentDialog } from "@/components/rms/pos-dialogs"
import { calcBill, khr, paymentStatus, usd } from "@/lib/rms/billing"
import { useRms } from "@/lib/rms/store"

const refundsSeed = [
  {
    id: "RF-0088",
    receipt: "R-2026-4402",
    payment: "Cash USD",
    amount: 12.4,
    reason: "Wrong order",
    requester: "Lina Chhay",
    approver: "—",
    status: "Pending Approval",
  },
  {
    id: "RF-0087",
    receipt: "R-2026-4387",
    payment: "KHQR",
    amount: 6.5,
    reason: "Quality issue",
    requester: "Lina Chhay",
    approver: "Dara Pich",
    status: "Approved",
  },
  {
    id: "RF-0086",
    receipt: "R-2026-4371",
    payment: "Card",
    amount: 21,
    reason: "Overcharged",
    requester: "Chenda Roeun",
    approver: "Sopheak Nou",
    status: "Rejected",
  },
]
const recon = [
  {
    id: "1",
    method: "KHQR",
    reference: "KQ-77120",
    recorded: 18.4,
    provider: 18.4,
  },
  {
    id: "2",
    method: "KHQR",
    reference: "KQ-77121",
    recorded: 42.1,
    provider: 42.1,
  },
  {
    id: "3",
    method: "Card",
    reference: "TID-0091",
    recorded: 66,
    provider: 63.5,
  },
  {
    id: "4",
    method: "Bank Transfer",
    reference: "BT-2231",
    recorded: 42,
    provider: 0,
  },
]

export default function BillingPage() {
  const { orders } = useRms()
  const router = useRouter()
  const [tab, setTab] = useTab("bills")
  const [pay, setPay] = React.useState<string | null>(null)
  const [refunds, setRefunds] = React.useState(refundsSeed)
  const bills = orders.filter(
    (o) => o.status !== "Draft" && o.status !== "Cancelled"
  )
  const payments = orders.flatMap((o) =>
    o.payments.map((p) => ({
      ...p,
      order: o.no,
      orderId: o.id,
      receipt: o.receiptNo ?? "—",
    }))
  )
  const collected = payments.reduce((s, p) => s + p.applied, 0)
  const setRefund = (
    id: string,
    patch: Partial<(typeof refundsSeed)[number]>
  ) => setRefunds((r) => r.map((x) => (x.id === id ? { ...x, ...patch } : x)))
  return (
    <Page>
      <PageHeader
        title="Bills & payments"
        description="Orders, bills, payments, refunds and receipts are separate records. Finalised records are never edited."
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "bills", label: "Bills" },
          { value: "payments", label: "Payments", count: payments.length },
          { value: "receipts", label: "Receipts" },
          {
            value: "refunds",
            label: "Refunds",
            count: refunds.filter((r) => r.status === "Pending Approval")
              .length,
          },
          { value: "reconciliation", label: "Reconciliation" },
        ]}
      />
      {tab === "bills" && (
        <DataTable
          rows={bills}
          pageSize={12}
          exportName="bills"
          onRowClick={(o) => router.push(`/orders/${o.id}`)}
          filters={[
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
            {
              key: "where",
              header: "Table / pickup",
              value: (o) => o.table ?? o.pickup ?? o.customer ?? "—",
            },
            {
              key: "sub",
              header: "Subtotal",
              align: "right",
              value: (o) => calcBill(o).subtotal,
              render: (o) => usd(calcBill(o).subtotal),
            },
            {
              key: "svc",
              header: "Service",
              align: "right",
              value: (o) => calcBill(o).service,
              render: (o) => usd(calcBill(o).service),
            },
            {
              key: "tax",
              header: "Tax",
              align: "right",
              value: (o) => calcBill(o).tax,
              render: (o) => usd(calcBill(o).tax),
            },
            {
              key: "total",
              header: "Total",
              align: "right",
              value: (o) => calcBill(o).total,
              render: (o) => <MoneyText value={calcBill(o).total} dual />,
            },
            {
              key: "bal",
              header: "Balance",
              align: "right",
              value: (o) => calcBill(o).balance,
              render: (o) => usd(calcBill(o).balance),
            },
            {
              key: "payment",
              header: "Payment",
              value: paymentStatus,
              render: (o) => <StatusBadge status={paymentStatus(o)} />,
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
              hidden: () => calcBill(o).balance === 0,
              onClick: () => setPay(o.id),
            },
          ]}
        />
      )}
      {tab === "payments" && (
        <>
          <section className="grid gap-3 sm:grid-cols-3">
            <Stat
              label="Collected today"
              value={usd(collected)}
              hint="Collections, not sales"
            />
            <Stat label="Pending electronic" value={1} tone="warning" />
            <Stat label="Failed" value={0} />
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
              { key: "order", header: "Order" },
              { key: "method", header: "Method" },
              {
                key: "tendered",
                header: "Tendered",
                align: "right",
                render: (p) =>
                  p.currency === "USD" ? usd(p.tendered) : khr(p.tendered),
              },
              {
                key: "applied",
                header: "Applied",
                align: "right",
                render: (p) => usd(p.applied),
              },
              {
                key: "change",
                header: "Change",
                align: "right",
                render: (p) =>
                  p.changeCurrency === "USD" ? usd(p.change) : khr(p.change),
              },
              {
                key: "reference",
                header: "Reference",
                render: (p) => p.reference ?? "—",
              },
              { key: "session", header: "Session" },
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
                onClick: () =>
                  confirmAction({
                    title: "Void this payment?",
                    effect:
                      "Only unfinalised payments in the same session can be voided. A reversal record is created.",
                    requireReason: true,
                    destructive: true,
                    confirmLabel: "Void",
                    onConfirm: () =>
                      requestApproval({
                        action: `Void payment on ${p.order}`,
                        amount: usd(p.applied),
                        onApproved: () => toast.success("Payment voided"),
                      }),
                  }),
              },
            ]}
          />
        </>
      )}
      {tab === "receipts" && (
        <DataTable
          rows={orders.filter((o) => o.receiptNo)}
          exportName="receipts"
          columns={[
            { key: "receiptNo", header: "Receipt" },
            { key: "no", header: "Order" },
            {
              key: "total",
              header: "Total",
              align: "right",
              value: (o) => calcBill(o).total,
              render: (o) => usd(calcBill(o).total),
            },
            { key: "business", header: "Business day" },
          ]}
          rowActions={(o) => [
            {
              label: "Reprint (COPY)",
              icon: Printer,
              onClick: () =>
                toast.success(
                  `${o.receiptNo} reprint queued, marked COPY; audit entry added`
                ),
            },
          ]}
        />
      )}
      {tab === "refunds" && (
        <DataTable
          rows={refunds}
          exportName="refunds"
          columns={[
            { key: "id", header: "Refund" },
            { key: "receipt", header: "Receipt" },
            { key: "payment", header: "Original payment" },
            {
              key: "amount",
              header: "Amount",
              align: "right",
              render: (r) => usd(r.amount),
            },
            { key: "reason", header: "Reason" },
            { key: "requester", header: "Requested by" },
            { key: "approver", header: "Approver" },
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
              hidden: () => r.status !== "Pending Approval",
              onClick: () =>
                requestApproval({
                  action: `Refund ${r.id}`,
                  amount: usd(r.amount),
                  reason: r.reason,
                  onApproved: (by) => {
                    setRefund(r.id, { status: "Approved", approver: by })
                    toast.success(`Refund approved by ${by}`)
                  },
                }),
            },
            {
              label: "Reject",
              icon: Undo2,
              destructive: true,
              hidden: () => r.status !== "Pending Approval",
              onClick: () =>
                confirmAction({
                  title: `Reject ${r.id}?`,
                  effect: "The requester is notified.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Reject",
                  onConfirm: () => setRefund(r.id, { status: "Rejected" }),
                }),
            },
          ]}
        />
      )}
      {tab === "reconciliation" && (
        <>
          <Notice tone="info">
            Compares recorded electronic payments with provider or bank
            references for business day 08/11/2026.
          </Notice>
          <DataTable
            rows={recon}
            exportName="reconciliation"
            columns={[
              { key: "method", header: "Method" },
              { key: "reference", header: "Reference" },
              {
                key: "recorded",
                header: "Recorded",
                align: "right",
                render: (r) => usd(r.recorded),
              },
              {
                key: "provider",
                header: "Provider",
                align: "right",
                render: (r) => usd(r.provider),
              },
              {
                key: "diff",
                header: "Difference",
                align: "right",
                value: (r) => r.recorded - r.provider,
                render: (r) => usd(r.recorded - r.provider),
              },
              {
                key: "state",
                header: "State",
                value: (r) =>
                  r.recorded === r.provider ? "Matched" : "Difference",
                render: (r) => (
                  <StatusBadge
                    status={
                      r.recorded === r.provider ? "Matched" : "Difference"
                    }
                  />
                ),
              },
            ]}
          />
        </>
      )}
      {pay && <PaymentDialog orderId={pay} open onClose={() => setPay(null)} />}
    </Page>
  )
}
