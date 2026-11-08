"use client"

import { useParams } from "next/navigation"
import { DataTable } from "@/components/rms/data-table"
import {
  EmptyState,
  KV,
  LinkButton,
  Notice,
  Page,
  PageHeader,
  PageTabs,
  Panel,
  Stat,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { calcBill, usd } from "@/lib/rms/billing"
import { customers } from "@/lib/rms/back-office"
import { useRms } from "@/lib/rms/store"

export default function CustomerProfilePage() {
  const { id } = useParams<{ id: string }>()
  const { orders } = useRms()
  const [tab, setTab] = useTab("profile")
  const c = customers.find((x) => x.id === id)
  if (!c)
    return (
      <Page>
        <EmptyState
          title="Customer not found"
          action={<LinkButton href="/customers">Back to customers</LinkButton>}
        />
      </Page>
    )
  const history = orders.filter((o) => o.customer === c.name)
  return (
    <Page>
      <PageHeader
        title={c.name}
        description={`${c.code} · ${c.phone}${c.email ? ` · ${c.email}` : ""}`}
        actions={
          <StatusBadge
            status={c.segment}
            tone={c.segment === "VIP" ? "info" : "neutral"}
          />
        }
      />
      {c.allergy && <Notice tone="danger">Allergy: {c.allergy}</Notice>}
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Total visits" value={c.visits} />
        <Stat label="Total spend" value={usd(c.spend)} />
        <Stat label="Last visit" value={c.last} />
        <Stat label="Loyalty points" value={c.points.toLocaleString()} />
      </section>
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "profile", label: "Profile" },
          { value: "orders", label: "Order history", count: history.length },
          { value: "loyalty", label: "Loyalty" },
        ]}
      />
      {tab === "profile" && (
        <Panel title="Details" className="max-w-xl">
          <KV
            items={[
              ["Preferred language", c.language],
              ["Preferences", c.prefs || "—"],
              ["Marketing consent", c.consent ? "Given" : "Not given"],
              ["No-shows", c.noShows],
              ["Credit balance", usd(c.credit)],
            ]}
          />
        </Panel>
      )}
      {tab === "orders" && (
        <DataTable
          rows={history}
          exportName="customer-orders"
          emptyTitle="No orders on this branch yet"
          columns={[
            { key: "no", header: "Order" },
            { key: "type", header: "Type" },
            {
              key: "status",
              header: "Status",
              render: (o) => <StatusBadge status={o.status} />,
            },
            {
              key: "total",
              header: "Total",
              align: "right",
              value: (o) => calcBill(o).total,
              render: (o) => usd(calcBill(o).total),
            },
          ]}
        />
      )}
      {tab === "loyalty" && (
        <DataTable
          rows={[
            {
              id: "1",
              date: "07/11/2026",
              type: "Earn",
              points: 24,
              ref: "#0088",
            },
            {
              id: "2",
              date: "28/10/2026",
              type: "Redeem",
              points: -100,
              ref: "#0041",
            },
            {
              id: "3",
              date: "20/10/2026",
              type: "Earn",
              points: 18,
              ref: "#0012",
            },
          ]}
          exportName="loyalty"
          columns={[
            { key: "date", header: "Date" },
            { key: "type", header: "Type" },
            { key: "points", header: "Points", align: "right" },
            { key: "ref", header: "Reference" },
          ]}
        />
      )}
    </Page>
  )
}
