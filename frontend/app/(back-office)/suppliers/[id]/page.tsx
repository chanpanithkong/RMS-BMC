"use client"

import { useParams } from "next/navigation"
import { DataTable } from "@/components/rms/data-table"
import { EmptyState, KV, LinkButton, Page, PageHeader, PageTabs, Panel, Stat, StatusBadge, useTab } from "@/components/rms/kit"
import * as inv from "@/lib/api/inventory"
import { api } from "@/lib/api/client"
import type { Invoice, Supplier } from "@/lib/api/purchasing"
import { num, useApi } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

interface History {
  supplier: Supplier
  balance: string
  ageing: Record<string, string>
  purchase_orders: { id: string; po_no: string; status: string; total: string }[]
  receipts: { id: string; gr_no: string; status: string; value: string }[]
  returns: { id: string; return_no: string; value: string }[]
  invoices: Invoice[]
  item_prices: { ingredient_id: string; unit_price: string; uom_id: string }[]
}

async function load(id: string) {
  const [h, ingredients, units] = await Promise.all([api<History>("GET", `/suppliers/${id}/history`), inv.ingredients(), inv.units()])
  return { h, ingredients, units }
}

export default function SupplierProfilePage() {
  const { id } = useParams<{ id: string }>()
  const [tab, setTab] = useTab("profile")
  const { data, loading } = useApi(() => load(id).catch(() => null), [id], null)
  if (loading) return <Page><PageHeader title="Supplier" description="Loading…" /></Page>
  if (!data)
    return (
      <Page>
        <EmptyState title="Supplier not found" action={<LinkButton href="/suppliers">Back to suppliers</LinkButton>} />
      </Page>
    )
  const { h, ingredients, units } = data
  const s = h.supplier
  const ing = (i: string) => ingredients.find((x) => x.id === i)?.name_en ?? "?"
  const unit = (u: string) => units.find((x) => x.id === u)?.code ?? ""
  return (
    <Page>
      <PageHeader title={s.name} description={`${s.contact_person} · ${s.phone}`} actions={<StatusBadge status={s.status} />} />
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Balance owed" value={usd(num(h.balance))} />
        <Stat label="Overdue" value={usd(Object.entries(h.ageing).filter(([k]) => k !== "current").reduce((a, [, v]) => a + num(v), 0))} />
        <Stat label="Purchase orders" value={h.purchase_orders.length} />
        <Stat label="Items supplied" value={h.item_prices.length} />
      </section>
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "profile", label: "Profile" },
          { value: "orders", label: "POs", count: h.purchase_orders.length },
          { value: "receipts", label: "Receipts", count: h.receipts.length },
          { value: "invoices", label: "Invoices", count: h.invoices.length },
          { value: "returns", label: "Returns", count: h.returns.length },
          { value: "prices", label: "Prices" },
        ]}
      />
      {tab === "profile" && (
        <Panel title="Details" className="max-w-xl">
          <KV
            items={[
              ["Address", s.address ?? "—"],
              ["Email", s.email ?? "—"],
              ["Tax ID", s.tax_id ?? "Not provided"],
              ["Payment terms", s.payment_terms],
              ["Currency", s.currency],
              ...Object.entries(h.ageing).map(([k, v]) => [`Owed: ${k.replace("_", " ")}`, usd(num(v))] as [string, string]),
            ]}
          />
        </Panel>
      )}
      {tab === "orders" && (
        <DataTable
          rows={h.purchase_orders}
          exportName="supplier-pos"
          columns={[
            { key: "po_no", header: "PO" },
            { key: "total", header: "Total", align: "right", render: (p) => usd(num(p.total)) },
            { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
          ]}
        />
      )}
      {tab === "receipts" && (
        <DataTable
          rows={h.receipts}
          exportName="supplier-receipts"
          columns={[
            { key: "gr_no", header: "Receipt" },
            { key: "value", header: "Value", align: "right", render: (g) => usd(num(g.value)) },
            { key: "status", header: "Status", render: (g) => <StatusBadge status={g.status} /> },
          ]}
        />
      )}
      {tab === "invoices" && (
        <DataTable
          rows={h.invoices}
          exportName="supplier-invoices"
          columns={[
            { key: "invoice_no", header: "Invoice" },
            { key: "invoice_date", header: "Date" },
            { key: "due_date", header: "Due" },
            { key: "amount", header: "Amount", align: "right", render: (i) => usd(num(i.amount)) },
            { key: "paid_amount", header: "Paid", align: "right", render: (i) => usd(num(i.paid_amount)) },
            { key: "match_status", header: "Match", render: (i) => <StatusBadge status={i.match_status} /> },
            { key: "status", header: "Status", render: (i) => <StatusBadge status={i.status} /> },
          ]}
        />
      )}
      {tab === "returns" && (
        <DataTable
          rows={h.returns}
          exportName="supplier-returns"
          columns={[
            { key: "return_no", header: "Return" },
            { key: "value", header: "Value", align: "right", render: (r) => usd(num(r.value)) },
          ]}
        />
      )}
      {tab === "prices" && (
        <DataTable
          rows={h.item_prices.map((p) => ({ ...p, id: p.ingredient_id, item: ing(p.ingredient_id), per: unit(p.uom_id) }))}
          exportName="supplier-prices"
          emptyTitle="No prices recorded yet; they are taken from purchase orders."
          columns={[
            { key: "item", header: "Ingredient" },
            { key: "unit_price", header: "Last price", align: "right", render: (p) => `${usd(num(p.unit_price))} / ${p.per}` },
          ]}
        />
      )}
    </Page>
  )
}
