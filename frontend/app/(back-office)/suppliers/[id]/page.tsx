"use client"

import { useParams } from "next/navigation"
import { DataTable } from "@/components/rms/data-table"
import {
  EmptyState,
  KV,
  LinkButton,
  Page,
  PageHeader,
  PageTabs,
  Panel,
  Stat,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import {
  goodsReceipts,
  ingredients,
  purchaseOrders,
  purchaseReturns,
  supplierInvoices,
  suppliers,
} from "@/lib/rms/back-office"

export default function SupplierProfilePage() {
  const { id } = useParams<{ id: string }>()
  const [tab, setTab] = useTab("profile")
  const s = suppliers.find((x) => x.id === id)
  if (!s)
    return (
      <Page>
        <EmptyState
          title="Supplier not found"
          action={<LinkButton href="/suppliers">Back to suppliers</LinkButton>}
        />
      </Page>
    )
  const pos = purchaseOrders.filter((p) => p.supplier === s.name)
  const grn = goodsReceipts.filter((p) => p.supplier === s.name)
  const inv = supplierInvoices.filter((p) => p.supplier === s.name)
  const ret = purchaseReturns.filter((p) => p.supplier === s.name)
  const items = ingredients.filter((i) => i.supplier === s.name)
  return (
    <Page>
      <PageHeader
        title={s.name}
        description={`${s.contact} · ${s.phone}`}
        actions={<StatusBadge status={s.status} />}
      />
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Balance owed" value={usd(s.balance)} />
        <Stat label="On-time delivery" value={`${s.onTime}%`} />
        <Stat label="Purchase orders" value={pos.length} />
        <Stat label="Items supplied" value={items.length} />
      </section>
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "profile", label: "Profile" },
          { value: "orders", label: "POs", count: pos.length },
          { value: "receipts", label: "Receipts", count: grn.length },
          { value: "invoices", label: "Invoices", count: inv.length },
          { value: "returns", label: "Returns", count: ret.length },
          { value: "prices", label: "Price history" },
        ]}
      />
      {tab === "profile" && (
        <Panel title="Details" className="max-w-xl">
          <KV
            items={[
              ["Address", s.address],
              ["Email", s.email || "—"],
              ["Tax ID", s.tin || "Not provided"],
              ["Payment terms", s.terms],
              ["Currency", s.currency],
            ]}
          />
        </Panel>
      )}
      {tab === "orders" && (
        <DataTable
          rows={pos}
          exportName="supplier-pos"
          columns={[
            { key: "id", header: "PO" },
            { key: "date", header: "Date" },
            {
              key: "total",
              header: "Total",
              align: "right",
              render: (r) => usd(r.total),
            },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
        />
      )}
      {tab === "receipts" && (
        <DataTable
          rows={grn}
          exportName="supplier-receipts"
          columns={[
            { key: "id", header: "Receipt" },
            { key: "po", header: "PO" },
            { key: "date", header: "Date" },
            {
              key: "value",
              header: "Value",
              align: "right",
              render: (r) => usd(r.value),
            },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
        />
      )}
      {tab === "invoices" && (
        <DataTable
          rows={inv}
          exportName="supplier-invoices"
          columns={[
            { key: "id", header: "Invoice" },
            { key: "due", header: "Due" },
            {
              key: "amount",
              header: "Amount",
              align: "right",
              render: (r) => usd(r.amount),
            },
            { key: "age", header: "Ageing" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
        />
      )}
      {tab === "returns" && (
        <DataTable
          rows={ret}
          exportName="supplier-returns"
          columns={[
            { key: "id", header: "Return" },
            { key: "items", header: "Items" },
            {
              key: "value",
              header: "Value",
              align: "right",
              render: (r) => usd(r.value),
            },
            { key: "reason", header: "Reason" },
          ]}
        />
      )}
      {tab === "prices" && (
        <DataTable
          rows={items.map((i) => ({
            id: i.id,
            name: i.name,
            last: i.cost,
            prev: +(i.cost * 0.96).toFixed(2),
            unit: i.unit,
          }))}
          exportName="supplier-prices"
          columns={[
            { key: "name", header: "Item" },
            {
              key: "prev",
              header: "Previous",
              align: "right",
              render: (r) => usd(r.prev),
            },
            {
              key: "last",
              header: "Latest",
              align: "right",
              render: (r) => usd(r.last),
            },
            { key: "unit", header: "Per" },
          ]}
        />
      )}
    </Page>
  )
}
