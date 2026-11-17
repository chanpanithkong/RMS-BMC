"use client"

import * as React from "react"
import {
  CheckCircle2,
  FileDown,
  PackageCheck,
  Send,
  ShieldCheck,
  Undo2,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { CrudTable } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction, requestApproval } from "@/components/rms/dialog-host"
import {
  Notice,
  Page,
  PageHeader,
  PageTabs,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import {
  goodsReceipts,
  purchaseOrders,
  purchaseRequests,
  purchaseReturns,
  supplierInvoices,
  suppliers,
} from "@/lib/rms/back-office"

type PO = (typeof purchaseOrders)[number]
const poLines = [
  { name: "Beef sirloin", ordered: 30, unit: "kg", price: 9.8 },
  { name: "Pork shoulder", ordered: 20, unit: "kg", price: 5.2 },
  { name: "Eggs", ordered: 180, unit: "piece", price: 0.14 },
]
const supplierNames = suppliers.map((s) => s.name)
const seq = (p: string) => `${p}-${Math.floor(3000 + Math.random() * 6000)}`

export default function PurchasingPage() {
  const [tab, setTab] = useTab("orders")
  const [orders, setOrders] = React.useState(purchaseOrders)
  const [receiving, setReceiving] = React.useState<PO | null>(null)
  const [received, setReceived] = React.useState<Record<string, string>>({})
  const [posted, setPosted] = React.useState<string[]>([])
  const patch = (id: string, status: string) =>
    setOrders((o) => o.map((x) => (x.id === id ? { ...x, status } : x)))
  const over = receiving
    ? poLines.some((l) => Number(received[l.name] || 0) > l.ordered * 1.05)
    : false
  return (
    <Page>
      <PageHeader
        title="Purchasing"
        description="Requests become approved purchase orders. Goods post to stock exactly once."
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "requests", label: "Requests" },
          { value: "orders", label: "Purchase orders" },
          { value: "receipts", label: "Goods receipts" },
          { value: "returns", label: "Returns" },
          { value: "invoices", label: "Invoices" },
        ]}
      />
      {tab === "requests" && (
        <CrudTable
          noun="Purchase request"
          seed={purchaseRequests}
          filters={[
            {
              key: "status",
              label: "Status",
              options: ["Submitted", "Approved", "Rejected"],
            },
          ]}
          columns={[
            { key: "id", header: "Request" },
            { key: "date", header: "Date" },
            { key: "by", header: "Requested by" },
            { key: "source", header: "Source" },
            { key: "items", header: "Items" },
            {
              key: "value",
              header: "Est. value",
              align: "right",
              render: (r) => usd(r.value),
            },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            {
              name: "items",
              label: "Items and quantities",
              type: "textarea",
              required: true,
            },
            {
              name: "value",
              label: "Estimated value",
              type: "number",
              min: 0,
              required: true,
            },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? seq("PR"),
            date: e?.date ?? "08/11/2026",
            by: e?.by ?? "Dara Pich",
            source: e?.source ?? "Manual",
            items: String(v.items),
            value: Number(v.value),
            status: e?.status ?? "Submitted",
          })}
          extraActions={(r, update) => [
            {
              label: "Approve",
              icon: CheckCircle2,
              hidden: () => r.status !== "Submitted",
              onClick: () => {
                update({ status: "Approved" })
                toast.success(`${r.id} approved`)
              },
            },
            {
              label: "Convert to PO",
              icon: Send,
              hidden: () => r.status !== "Approved",
              onClick: () => {
                setOrders((o) => [
                  {
                    id: seq("PO"),
                    supplier: "Golden Grain Co.",
                    date: "08/11/2026",
                    delivery: "10/11/2026",
                    total: r.value,
                    status: "Draft",
                    by: "Malis Som",
                    received: 0,
                  },
                  ...o,
                ])
                setTab("orders")
                toast.success("Draft purchase order created")
              },
            },
            {
              label: "Reject",
              icon: XCircle,
              destructive: true,
              hidden: () => r.status !== "Submitted",
              onClick: () =>
                confirmAction({
                  title: `Reject ${r.id}?`,
                  effect: "The requester is notified.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Reject",
                  onConfirm: () => update({ status: "Rejected" }),
                }),
            },
          ]}
        />
      )}
      {tab === "orders" && (
        <DataTable
          rows={orders}
          exportName="purchase-orders"
          filters={[
            {
              key: "status",
              label: "Status",
              options: [
                "Draft",
                "Submitted",
                "Approved",
                "Sent",
                "Partially Received",
                "Received",
                "Closed",
                "Cancelled",
              ],
            },
            { key: "supplier", label: "Supplier", options: supplierNames },
          ]}
          toolbar={
            <Button
              onClick={() => {
                setOrders((o) => [
                  {
                    id: seq("PO"),
                    supplier: "Golden Grain Co.",
                    date: "08/11/2026",
                    delivery: "12/11/2026",
                    total: 0,
                    status: "Draft",
                    by: "Dara Pich",
                    received: 0,
                  },
                  ...o,
                ])
                toast.success("Draft purchase order created")
              }}
            >
              New purchase order
            </Button>
          }
          columns={[
            {
              key: "id",
              header: "PO",
              render: (r) => <span className="font-medium">{r.id}</span>,
            },
            { key: "supplier", header: "Supplier" },
            { key: "date", header: "Date" },
            { key: "delivery", header: "Delivery" },
            {
              key: "total",
              header: "Total",
              align: "right",
              render: (r) => usd(r.total),
            },
            { key: "by", header: "Created by", hidden: true },
            {
              key: "status",
              header: "Status",
              render: (r) => (
                <StatusBadge
                  status={r.status === "Sent" ? "Sent to Supplier" : r.status}
                />
              ),
            },
          ]}
          rowActions={(r) => [
            {
              label: "Submit for approval",
              icon: Send,
              hidden: () => r.status !== "Draft",
              onClick: () => patch(r.id, "Submitted"),
            },
            {
              label: "Approve",
              icon: ShieldCheck,
              hidden: () => r.status !== "Submitted",
              onClick: () =>
                requestApproval({
                  action: `Approve ${r.id}`,
                  amount: usd(r.total),
                  limit: usd(1000),
                  onApproved: (by) => {
                    patch(r.id, "Approved")
                    toast.success(`Approved by ${by}`)
                  },
                }),
            },
            {
              label: "Send to supplier",
              icon: Send,
              hidden: () => r.status !== "Approved",
              onClick: () => {
                patch(r.id, "Sent")
                toast.success("Purchase order emailed to supplier")
              },
            },
            {
              label: "Download PDF",
              icon: FileDown,
              onClick: () =>
                toast.info(`${r.id} PDF is generated by the backend`),
            },
            {
              label: "Receive goods",
              icon: PackageCheck,
              hidden: () => !["Sent", "Partially Received"].includes(r.status),
              onClick: () => {
                setReceived({})
                setReceiving(r)
              },
            },
            {
              label: "Cancel",
              icon: XCircle,
              destructive: true,
              hidden: () =>
                ["Received", "Closed", "Cancelled"].includes(r.status),
              onClick: () =>
                confirmAction({
                  title: `Cancel ${r.id}?`,
                  effect: "The supplier should be told if it was already sent.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Cancel PO",
                  onConfirm: () => patch(r.id, "Cancelled"),
                }),
            },
          ]}
        />
      )}
      {tab === "receipts" && (
        <DataTable
          rows={goodsReceipts}
          exportName="goods-receipts"
          columns={[
            { key: "id", header: "Receipt" },
            { key: "po", header: "PO" },
            { key: "supplier", header: "Supplier" },
            { key: "date", header: "Date" },
            {
              key: "value",
              header: "Value",
              align: "right",
              render: (r) => usd(r.value),
            },
            { key: "by", header: "Received by" },
            {
              key: "status",
              header: "Status",
              render: (r) => (
                <StatusBadge
                  status={posted.includes(r.id) ? "Posted" : r.status}
                />
              ),
            },
          ]}
          rowActions={(r) => [
            {
              label: "Post to stock",
              icon: PackageCheck,
              hidden: () => r.status === "Posted" || posted.includes(r.id),
              onClick: () =>
                confirmAction({
                  title: `Post ${r.id}?`,
                  effect:
                    "Stock and weighted average cost update once. Posting can't be repeated.",
                  confirmLabel: "Post receipt",
                  onConfirm: () => {
                    setPosted((p) => [...p, r.id])
                    toast.success("Posted to stock")
                  },
                }),
            },
          ]}
        />
      )}
      {tab === "returns" && (
        <CrudTable
          noun="Purchase return"
          canEdit={false}
          seed={purchaseReturns}
          columns={[
            { key: "id", header: "Return" },
            { key: "grn", header: "Receipt" },
            { key: "supplier", header: "Supplier" },
            { key: "date", header: "Date" },
            { key: "items", header: "Items" },
            {
              key: "value",
              header: "Value",
              align: "right",
              render: (r) => usd(r.value),
            },
            { key: "reason", header: "Reason" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            {
              name: "grn",
              label: "Goods receipt",
              type: "select",
              options: goodsReceipts.map((g) => g.id),
              required: true,
              half: true,
            },
            {
              name: "supplier",
              label: "Supplier",
              type: "select",
              options: supplierNames,
              required: true,
              half: true,
            },
            { name: "items", label: "Items and quantities", required: true },
            {
              name: "value",
              label: "Value",
              type: "number",
              min: 0,
              required: true,
              half: true,
            },
            { name: "reason", label: "Reason", required: true, half: true },
          ]}
          toRow={(v) => ({
            id: seq("RET"),
            grn: String(v.grn),
            supplier: String(v.supplier),
            date: "08/11/2026",
            items: String(v.items),
            value: Number(v.value),
            reason: String(v.reason),
            status: "Posted",
          })}
        />
      )}
      {tab === "invoices" && (
        <CrudTable
          noun="Supplier invoice"
          canEdit={false}
          seed={supplierInvoices}
          filters={[
            {
              key: "status",
              label: "Status",
              options: ["Unpaid", "Partially Paid", "Paid"],
            },
            { key: "age", label: "Ageing" },
          ]}
          columns={[
            { key: "id", header: "Invoice" },
            { key: "supplier", header: "Supplier" },
            { key: "date", header: "Date" },
            { key: "due", header: "Due" },
            {
              key: "amount",
              header: "Amount",
              align: "right",
              render: (r) => usd(r.amount),
            },
            {
              key: "paid",
              header: "Paid",
              align: "right",
              render: (r) => usd(r.paid),
            },
            { key: "age", header: "Ageing" },
            {
              key: "match",
              header: "Match",
              render: (r) => <StatusBadge status={r.match} />,
            },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            {
              name: "id",
              label: "Invoice number",
              required: true,
              half: true,
              validate: (v) =>
                supplierInvoices.some((i) => i.id === v)
                  ? "This invoice number already exists for the supplier"
                  : undefined,
            },
            {
              name: "supplier",
              label: "Supplier",
              type: "select",
              options: supplierNames,
              required: true,
              half: true,
            },
            {
              name: "amount",
              label: "Amount",
              type: "number",
              min: 0,
              required: true,
              half: true,
            },
            {
              name: "due",
              label: "Due date (DD/MM/YYYY)",
              required: true,
              half: true,
            },
          ]}
          toRow={(v) => ({
            id: String(v.id),
            supplier: String(v.supplier),
            date: "08/11/2026",
            due: String(v.due),
            amount: Number(v.amount),
            paid: 0,
            match: "Pending",
            status: "Unpaid",
            age: "0–30 days",
          })}
          extraActions={(r, update) => [
            {
              label: "Record payment",
              icon: Undo2,
              hidden: () => r.status === "Paid",
              onClick: () => {
                update({ paid: r.amount, status: "Paid", age: "—" })
                toast.success("Supplier payment recorded")
              },
            },
          ]}
        />
      )}
      <Dialog open={!!receiving} onOpenChange={(o) => !o && setReceiving(null)}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Receive against {receiving?.id}</DialogTitle>
            <DialogDescription>
              {receiving?.supplier}. Quantities over 5% tolerance need approval.
            </DialogDescription>
          </DialogHeader>
          <ul className="grid gap-2">
            {poLines.map((l) => (
              <li
                key={l.name}
                className="grid grid-cols-[1fr_auto_100px_120px] items-center gap-2 text-sm"
              >
                <span className="font-medium">{l.name}</span>
                <span className="tabular text-xs text-muted-foreground">
                  {l.ordered} {l.unit}
                </span>
                <Input
                  aria-label={`${l.name} received`}
                  inputMode="decimal"
                  placeholder="Received"
                  value={received[l.name] ?? ""}
                  onChange={(e) =>
                    setReceived({ ...received, [l.name]: e.target.value })
                  }
                />
                <Input
                  aria-label={`${l.name} batch`}
                  placeholder="Batch / expiry"
                />
              </li>
            ))}
          </ul>
          {over && (
            <Notice tone="warning">
              Over-receipt beyond tolerance. Approval will be requested.
            </Notice>
          )}
          <DialogFooter>
            <Button
              onClick={() => {
                const r = receiving!
                const finish = () => {
                  const full = poLines.every(
                    (l) => Number(received[l.name] || 0) >= l.ordered
                  )
                  patch(r.id, full ? "Received" : "Partially Received")
                  setReceiving(null)
                  toast.success("Goods receipt posted to stock")
                }
                if (over)
                  requestApproval({
                    action: `Over-receipt on ${r.id}`,
                    onApproved: finish,
                  })
                else finish()
              }}
            >
              Post receipt
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Page>
  )
}
