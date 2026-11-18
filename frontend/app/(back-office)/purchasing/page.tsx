"use client"

import * as React from "react"
import { Ban, Check, CircleDollarSign, FileText, PackageCheck, Plus, Send, ShieldCheck, Truck, Undo2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { RecordDialog, type Field, type FieldValue } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { Page, PageHeader, PageTabs, StatusBadge, useTab } from "@/components/rms/kit"
import * as inv from "@/lib/api/inventory"
import * as pur from "@/lib/api/purchasing"
import { can, useSession } from "@/lib/api/session"
import { act, num, save, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

const LABEL: Record<string, string> = { PendingApproval: "Pending Approval", PartiallyReceived: "Partially Received", PartiallyPaid: "Partially Paid", ForReview: "For Review", LowStock: "Low stock" }
const label = (s: string) => LABEL[s] ?? s
const today = () => new Date().toLocaleDateString("en-CA")

async function loadRefs() {
  const [suppliers, ingredients, units, locations] = await Promise.all([pur.suppliers(), inv.ingredients(), inv.units(), inv.locations()])
  return { suppliers, ingredients, units, locations }
}
const noRefs = { suppliers: [], ingredients: [], units: [], locations: [] } as Awaited<ReturnType<typeof loadRefs>>

type Dialog =
  | { kind: "request" }
  | { kind: "po"; request?: pur.PurchaseRequest }
  | { kind: "receive"; po: pur.PO }
  | { kind: "return"; gr: pur.GR }
  | { kind: "invoice" }
  | { kind: "pay"; invoice: pur.Invoice }
  | null

export default function PurchasingPage() {
  const { me } = useSession()
  const [tab, setTab] = useTab("requests")
  const refs = useApi(loadRefs, [], noRefs)
  const reqs = useApi(pur.requests, [], [])
  const pos = useApi(pur.orders, [], [])
  const grs = useApi(pur.receipts, [], [])
  const rets = useApi(pur.returns, [], [])
  const invs = useApi(pur.invoices, [], [])
  const [dialog, setDialog] = React.useState<Dialog>(null)
  const reload = () => [reqs, pos, grs, rets, invs].forEach((x) => x.reload())

  const { suppliers, ingredients, units, locations } = refs.data
  const supName = (id: string | null) => suppliers.find((s) => s.id === id)?.name ?? "—"
  const ingName = (id: string) => ingredients.find((i) => i.id === id)?.name_en ?? "?"
  const unitCode = (id: string) => units.find((u) => u.id === id)?.code ?? ""
  const locName = (id: string) => locations.find((l) => l.id === id)?.name ?? ""
  const items = (lines: { ingredient_id: string; uom_id: string }[], qty: (l: never) => string | number) =>
    lines.map((l) => `${ingName(l.ingredient_id)} ${inv.qty(qty(l as never), unitCode(l.uom_id))}`).join(", ")
  const activeSup = suppliers.filter((s) => s.status === "Active").map((s) => s.name)
  const ingOpts = ingredients.filter((i) => i.is_active).map((i) => i.name_en)
  const locOpts = locations.filter((l) => l.is_active).map((l) => l.name)
  const unitFor = (ingNameV: FieldValue, unitV?: FieldValue) => {
    const ing = ingredients.find((i) => i.name_en === ingNameV)
    return units.find((u) => u.code === unitV)?.id ?? ing?.stock_uom_id ?? ""
  }
  const run = (fn: () => Promise<unknown>, done: string) => void act(fn, done, reload)

  // Dynamic dialog content
  const d = dialog
  let fields: Field[] = []
  let title = ""
  let description: string | undefined
  let onSubmit: (v: Record<string, FieldValue>) => Promise<unknown> = async () => undefined
  if (d?.kind === "request") {
    title = "New purchase request"
    fields = [
      { name: "ingredient", label: "Ingredient", type: "select", options: ingOpts, required: true },
      { name: "qty", label: "Quantity", type: "number", min: 0.001, required: true, half: true },
      { name: "unit", label: "Unit", type: "select", options: units.map((u) => u.code), half: true, hint: "Default: stock unit" },
      { name: "note", label: "Note" },
    ]
    onSubmit = (v) =>
      save(() =>
        pur.createRequest(
          [{ ingredient_id: ingredients.find((i) => i.name_en === v.ingredient)!.id, quantity: String(v.qty), uom_id: unitFor(v.ingredient, v.unit) }],
          String(v.note ?? "") || undefined
        )
      ).then(reload)
  } else if (d?.kind === "po") {
    const lines = d.request?.lines ?? null
    title = d.request ? `Purchase order from ${d.request.request_no}` : "New purchase order"
    description = "Enter the agreed unit price for each line. The order then goes for approval."
    fields = [
      { name: "supplier", label: "Supplier", type: "select", options: activeSup, required: true, half: true },
      { name: "location", label: "Deliver to", type: "select", options: locOpts, required: true, half: true },
      { name: "date", label: "Delivery date", type: "date", half: true },
      ...(lines
        ? lines.map((l, i) => ({
            name: `price${i}`,
            label: `${ingName(l.ingredient_id)}: ${inv.qty(l.quantity, unitCode(l.uom_id))}, unit price (USD per ${unitCode(l.uom_id)})`,
            type: "number" as const,
            min: 0,
            required: true,
          }))
        : ([
            { name: "ingredient", label: "Ingredient", type: "select", options: ingOpts, required: true },
            { name: "qty", label: "Quantity", type: "number", min: 0.001, required: true, half: true },
            { name: "unit", label: "Unit", type: "select", options: units.map((u) => u.code), half: true },
            { name: "price", label: "Unit price (USD)", type: "number", min: 0, required: true, half: true },
          ] as Field[])),
    ]
    onSubmit = (v) =>
      save(() =>
        pur.createPO({
          supplier_id: suppliers.find((s) => s.name === v.supplier)!.id,
          location_id: locations.find((l) => l.name === v.location)!.id,
          delivery_date: String(v.date ?? "") || undefined,
          request_id: d.request?.id,
          lines: lines
            ? lines.map((l, i) => ({ ingredient_id: l.ingredient_id, qty_ordered: l.quantity, uom_id: l.uom_id, unit_price: String(v[`price${i}`]) }))
            : [
                {
                  ingredient_id: ingredients.find((i) => i.name_en === v.ingredient)!.id,
                  qty_ordered: String(v.qty),
                  uom_id: unitFor(v.ingredient, v.unit),
                  unit_price: String(v.price),
                },
              ],
        })
      ).then(() => {
        reload()
        setTab("orders")
      })
  } else if (d?.kind === "receive") {
    title = `Receive ${d.po.po_no}`
    description = "Enter what arrived. Quantities beyond the receiving tolerance need a manager's approval before they are added to stock."
    fields = d.po.lines.map((l) => ({
      name: l.id,
      label: `${ingName(l.ingredient_id)}: ordered ${inv.qty(l.qty_ordered)}, received so far ${inv.qty(l.qty_received)} ${unitCode(l.uom_id)}`,
      type: "number" as const,
      min: 0,
    }))
    onSubmit = (v) =>
      save(() => pur.receive(d.po, Object.fromEntries(d.po.lines.map((l) => [l.id, Number(v[l.id] || 0)])))).then(() => {
        reload()
        setTab("receipts")
      })
  } else if (d?.kind === "return") {
    title = `Return goods from ${d.gr.gr_no}`
    fields = [
      ...d.gr.lines.map((l) => ({
        name: l.id,
        label: `${ingName(l.ingredient_id)}: received ${inv.qty(l.qty_received, unitCode(l.uom_id))}`,
        type: "number" as const,
        min: 0,
      })),
      { name: "reason", label: "Reason", required: true },
    ]
    onSubmit = (v) =>
      save(() =>
        pur.createReturn(
          d.gr.id,
          String(v.reason),
          d.gr.lines.filter((l) => Number(v[l.id]) > 0).map((l) => ({ gr_item_id: l.id, quantity: String(v[l.id]) }))
        )
      ).then(() => {
        reload()
        setTab("returns")
      })
  } else if (d?.kind === "invoice") {
    const posted = grs.data.filter((g) => g.status === "Posted")
    title = "Record supplier invoice"
    description = "The invoice is matched against the posted receipt (less returns)."
    fields = [
      { name: "supplier", label: "Supplier", type: "select", options: activeSup, required: true, half: true },
      { name: "no", label: "Invoice number", required: true, half: true },
      { name: "date", label: "Invoice date", type: "date", required: true, half: true },
      { name: "due", label: "Due date", type: "date", required: true, half: true },
      { name: "amount", label: "Amount (USD)", type: "number", min: 0.01, required: true, half: true },
      { name: "gr", label: "Goods receipt", type: "select", options: posted.map((g) => `${g.gr_no} · ${supName(g.supplier_id)} · ${usd(num(g.total_value))}`), half: true },
    ]
    onSubmit = (v) =>
      save(() =>
        pur.createInvoice({
          supplier_id: suppliers.find((s) => s.name === v.supplier)!.id,
          invoice_no: String(v.no),
          invoice_date: String(v.date),
          due_date: String(v.due),
          amount: String(v.amount),
          gr_ids: posted.filter((g) => String(v.gr ?? "").startsWith(`${g.gr_no} ·`)).map((g) => g.id),
        })
      ).then(reload)
  } else if (d?.kind === "pay") {
    title = `Pay ${d.invoice.invoice_no}`
    description = `${supName(d.invoice.supplier_id)}. Outstanding ${usd(num(d.invoice.amount) - num(d.invoice.paid_amount))}.`
    fields = [
      { name: "amount", label: "Amount (USD)", type: "number", min: 0.01, required: true, half: true },
      { name: "method", label: "Method", type: "select", options: ["BANK_TRANSFER", "CASH", "KHQR", "CHEQUE"], required: true, half: true },
      { name: "ref", label: "Reference" },
    ]
    onSubmit = (v) => save(() => pur.payInvoice(d.invoice.id, { amount: String(v.amount), method: String(v.method), reference: String(v.ref ?? "") || undefined })).then(reload)
  }

  return (
    <Page>
      <PageHeader
        title="Purchasing"
        description="Requests become purchase orders; receipts add stock exactly once; invoices are matched against what was received."
        actions={
          <>
            {can(me, "purchases.request") && (
              <Button variant="outline" onClick={() => setDialog({ kind: "request" })}>
                <Plus />
                Request
              </Button>
            )}
            {can(me, "purchases.create") && (
              <Button onClick={() => setDialog({ kind: "po" })}>
                <Plus />
                Purchase order
              </Button>
            )}
          </>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "requests", label: "Requests", count: reqs.data.filter((r) => r.status === "Submitted").length || undefined },
          { value: "orders", label: "Purchase orders", count: pos.data.length },
          { value: "receipts", label: "Goods receipts", count: grs.data.filter((g) => g.status === "PendingApproval").length || undefined },
          { value: "returns", label: "Returns" },
          { value: "invoices", label: "Invoices", count: invs.data.filter((i) => i.status !== "Paid").length || undefined },
        ]}
      />
      {tab === "requests" && (
        <DataTable
          rows={reqs.data.map((r) => ({ ...r, items: items(r.lines, (l: pur.Line) => l.quantity), state: label(r.status), from: label(r.source) }))}
          exportName="purchase-requests"
          emptyTitle="No purchase requests"
          columns={[
            { key: "request_no", header: "Request" },
            { key: "from", header: "Source" },
            { key: "items", header: "Items" },
            { key: "state", header: "Status", render: (r) => <StatusBadge status={r.state} /> },
          ]}
          rowActions={(r) => [
            { label: "Approve", icon: Check, hidden: () => r.status !== "Submitted" || !can(me, "purchases.approve"), onClick: () => run(() => pur.decideRequest(r.id, true), `${r.request_no} approved`) },
            { label: "Reject", icon: X, destructive: true, hidden: () => r.status !== "Submitted" || !can(me, "purchases.approve"), onClick: () => run(() => pur.decideRequest(r.id, false), `${r.request_no} rejected`) },
            { label: "Create purchase order", icon: FileText, hidden: () => r.status !== "Approved" || !can(me, "purchases.create"), onClick: () => setDialog({ kind: "po", request: r }) },
          ]}
        />
      )}
      {tab === "orders" && (
        <DataTable
          rows={pos.data.map((p) => ({
            ...p,
            supplier: supName(p.supplier_id),
            location: locName(p.location_id),
            items: items(p.lines, (l: pur.PO["lines"][number]) => l.qty_ordered),
            amount: num(p.total),
            state: label(p.status),
          }))}
          exportName="purchase-orders"
          emptyTitle="No purchase orders"
          filters={[{ key: "state", label: "Status" }, { key: "supplier", label: "Supplier" }]}
          columns={[
            { key: "po_no", header: "PO" },
            { key: "supplier", header: "Supplier" },
            { key: "location", header: "Deliver to" },
            { key: "delivery_date", header: "Delivery", render: (p) => p.delivery_date ?? "—" },
            { key: "items", header: "Items" },
            { key: "amount", header: "Total", align: "right", render: (p) => usd(p.amount) },
            { key: "state", header: "Status", render: (p) => <StatusBadge status={p.state} /> },
          ]}
          rowActions={(p) => [
            { label: "Submit for approval", icon: Send, hidden: () => p.status !== "Draft", onClick: () => run(() => pur.poAction(p.id, "submit"), `${p.po_no} submitted`) },
            { label: "Approve", icon: ShieldCheck, hidden: () => p.status !== "Submitted" || !can(me, "purchases.approve"), onClick: () => run(() => pur.poAction(p.id, "approve"), `${p.po_no} approved`) },
            { label: "Mark sent to supplier", icon: Truck, hidden: () => p.status !== "Approved", onClick: () => run(() => pur.poAction(p.id, "send"), `${p.po_no} sent`) },
            {
              label: "Receive goods",
              icon: PackageCheck,
              hidden: () => !["Approved", "Sent", "PartiallyReceived"].includes(p.status) || !can(me, "goods_receipts.post"),
              onClick: () => setDialog({ kind: "receive", po: p }),
            },
            {
              label: "Cancel",
              icon: Ban,
              destructive: true,
              hidden: () => !["Draft", "Submitted", "Approved", "Sent"].includes(p.status),
              onClick: () =>
                confirmAction({
                  title: `Cancel ${p.po_no}?`,
                  effect: "The supplier should be told separately. Cancelled orders stay on record.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Cancel order",
                  onConfirm: (reason) => run(() => pur.cancelPO(p.id, reason), `${p.po_no} cancelled`),
                }),
            },
          ]}
        />
      )}
      {tab === "receipts" && (
        <DataTable
          rows={grs.data.map((g) => ({
            ...g,
            po: pos.data.find((p) => p.id === g.po_id)?.po_no ?? (g.is_direct ? "Direct" : "—"),
            supplier: supName(g.supplier_id),
            items: items(g.lines, (l: pur.GR["lines"][number]) => l.qty_received),
            value: num(g.total_value),
            posted: when(g.posted_at) || "—",
            state: label(g.status),
          }))}
          exportName="goods-receipts"
          emptyTitle="No goods receipts"
          columns={[
            { key: "gr_no", header: "Receipt" },
            { key: "po", header: "PO" },
            { key: "supplier", header: "Supplier" },
            { key: "items", header: "Items" },
            { key: "value", header: "Value", align: "right", render: (g) => usd(g.value) },
            { key: "posted", header: "Posted" },
            { key: "exception_note", header: "Exception", render: (g) => g.exception_note ?? "—" },
            { key: "state", header: "Status", render: (g) => <StatusBadge status={g.state} /> },
          ]}
          rowActions={(g) => [
            { label: "Post to stock", icon: PackageCheck, hidden: () => g.status !== "Draft", onClick: () => run(() => pur.postGR(g.id), `${g.gr_no} posted`) },
            { label: "Approve and post", icon: ShieldCheck, hidden: () => g.status !== "PendingApproval", onClick: () => run(() => pur.approveGR(g.id), `${g.gr_no} posted`) },
            { label: "Return goods", icon: Undo2, hidden: () => g.status !== "Posted" || !can(me, "goods_receipts.post"), onClick: () => setDialog({ kind: "return", gr: g }) },
          ]}
        />
      )}
      {tab === "returns" && (
        <DataTable
          rows={rets.data.map((r) => ({ ...r, supplier: supName(r.supplier_id), date: when(r.created_at), value: num(r.total_value) }))}
          exportName="purchase-returns"
          emptyTitle="No returns"
          columns={[
            { key: "return_no", header: "Return" },
            { key: "date", header: "Date" },
            { key: "gr_no", header: "From receipt" },
            { key: "supplier", header: "Supplier" },
            { key: "reason", header: "Reason" },
            { key: "value", header: "Value", align: "right", render: (r) => usd(r.value) },
          ]}
        />
      )}
      {tab === "invoices" && (
        <DataTable
          rows={invs.data.map((i) => ({
            ...i,
            supplier: supName(i.supplier_id),
            amt: num(i.amount),
            matched: i.matched_value === null ? null : num(i.matched_value),
            outstanding: num(i.amount) - num(i.paid_amount),
            match: label(i.match_status),
            state: label(i.status),
          }))}
          exportName="supplier-invoices"
          emptyTitle="No supplier invoices"
          toolbar={can(me, "supplier_payments.create") && <Button onClick={() => setDialog({ kind: "invoice" })}>Record invoice</Button>}
          columns={[
            { key: "invoice_no", header: "Invoice" },
            { key: "supplier", header: "Supplier" },
            { key: "invoice_date", header: "Date" },
            { key: "due_date", header: "Due" },
            { key: "amt", header: "Amount", align: "right", render: (i) => usd(i.amt) },
            { key: "matched", header: "Received value", align: "right", render: (i) => (i.matched === null ? "—" : usd(i.matched)) },
            { key: "match", header: "Match", render: (i) => <StatusBadge status={i.match} tone={i.match === "Matched" ? "success" : "warning"} /> },
            { key: "outstanding", header: "Outstanding", align: "right", render: (i) => usd(i.outstanding) },
            { key: "state", header: "Status", render: (i) => <StatusBadge status={i.state} /> },
          ]}
          rowActions={(i) => [
            { label: "Record payment", icon: CircleDollarSign, hidden: () => i.status === "Paid" || !can(me, "supplier_payments.create"), onClick: () => setDialog({ kind: "pay", invoice: i }) },
          ]}
        />
      )}
      <RecordDialog
        open={!!dialog}
        onOpenChange={(o) => !o && setDialog(null)}
        title={title}
        description={description}
        fields={fields}
        initial={d?.kind === "invoice" ? { date: today() } : d?.kind === "pay" ? { amount: String(num(d.invoice.amount) - num(d.invoice.paid_amount)), method: "BANK_TRANSFER" } : undefined}
        onSubmit={onSubmit}
        wide={d?.kind === "po" || d?.kind === "receive"}
      />
    </Page>
  )
}
