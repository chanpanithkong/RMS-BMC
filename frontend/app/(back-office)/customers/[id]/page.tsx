"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { EmptyState, KV, LinkButton, Notice, Page, PageHeader, PageTabs, Panel, Stat, StatusBadge, useTab } from "@/components/rms/kit"
import * as cus from "@/lib/api/customers"
import { can, useSession } from "@/lib/api/session"
import { act, num, save, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

async function load(id: string) {
  const [c, orders, loyalty] = await Promise.all([cus.get(id), cus.orders(id), cus.loyalty(id).catch(() => null)])
  return { c, orders, loyalty }
}

export default function CustomerProfilePage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { me } = useSession()
  const [tab, setTab] = useTab("profile")
  const { data, loading, reload } = useApi(() => load(id).catch(() => null), [id], null)
  const [adjust, setAdjust] = React.useState(false)
  if (loading) return <Page><PageHeader title="Customer" description="Loading…" /></Page>
  if (!data)
    return (
      <Page>
        <EmptyState title="Customer not found" action={<LinkButton href="/customers">Back to customers</LinkButton>} />
      </Page>
    )
  const { c, orders, loyalty } = data
  return (
    <Page>
      <PageHeader
        title={c.name}
        description={`${c.code}${c.phone ? ` · ${c.phone}` : ""}${c.email ? ` · ${c.email}` : ""}`}
        actions={
          <>
            <StatusBadge status={c.classification} tone={c.classification === "VIP" ? "info" : "neutral"} />
            {can(me, "customers.manage") && !c.anonymised && (
              <Button
                variant="outline"
                onClick={() =>
                  confirmAction({
                    title: `Anonymise ${c.name}?`,
                    effect: "Name, phone, email and addresses are removed for good. Orders and payments stay under the anonymised code.",
                    requireReason: true,
                    destructive: true,
                    confirmLabel: "Anonymise",
                    onConfirm: (reason) => void act(() => cus.anonymise(c.id, reason), "Customer anonymised", () => router.push("/customers")),
                  })
                }
              >
                Anonymise
              </Button>
            )}
          </>
        }
      />
      {c.allergy_notes && <Notice tone="danger">Allergy: {c.allergy_notes}</Notice>}
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Completed visits" value={c.visits ?? 0} />
        <Stat label="Total spend" value={usd(num(c.total_spend))} />
        <Stat label="Last visit" value={c.last_visit ? when(c.last_visit).slice(0, 10) : "—"} />
        <Stat label="Loyalty points" value={(loyalty?.balance ?? c.loyalty_points).toLocaleString()} hint={loyalty ? `Worth ${usd(num(loyalty.redeemable_value))}` : undefined} />
      </section>
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "profile", label: "Profile" },
          { value: "orders", label: "Order history", count: orders.length },
          { value: "loyalty", label: "Loyalty" },
        ]}
      />
      {tab === "profile" && (
        <Panel title="Details" className="max-w-xl">
          <KV
            items={[
              ["Preferred language", c.preferred_language === "en" ? "English" : "Khmer"],
              ["Preferences", c.preferences || "—"],
              ["Marketing consent", c.consent_marketing ? "Given" : "Not given"],
              ["No-shows", c.no_show_count],
              ...c.addresses.map((a) => [a.label, `${a.address}${a.landmark ? ` (${a.landmark})` : ""}`] as [string, string]),
            ]}
          />
        </Panel>
      )}
      {tab === "orders" && (
        <DataTable
          rows={orders.map((o) => ({ ...o, total: num(o.grand_total) }))}
          exportName="customer-orders"
          emptyTitle="No orders yet"
          onRowClick={(o) => router.push(`/orders/${o.id}`)}
          columns={[
            { key: "order_no", header: "Order" },
            { key: "business_date", header: "Date" },
            { key: "order_type", header: "Type" },
            { key: "order_status", header: "Status", render: (o) => <StatusBadge status={o.order_status} /> },
            { key: "total", header: "Total", align: "right", render: (o) => usd(o.total) },
          ]}
        />
      )}
      {tab === "loyalty" && (
        <>
          {loyalty && loyalty.expiring_within_30_days > 0 && (
            <Notice tone="warning">
              {loyalty.expiring_within_30_days} points expire within 30 days{loyalty.next_expiry ? ` (next on ${when(loyalty.next_expiry).slice(0, 10)})` : ""}.
            </Notice>
          )}
          <DataTable
            rows={(loyalty?.history ?? []).map((h, i) => ({ ...h, id: String(i), date: when(h.created_at), expires: when(h.expires_at).slice(0, 10) || "—" }))}
            exportName="loyalty"
            emptyTitle="No points yet"
            toolbar={
              can(me, "promotions.manage") && (
                <Button variant="outline" onClick={() => setAdjust(true)}>
                  Adjust points
                </Button>
              )
            }
            columns={[
              { key: "date", header: "Date" },
              { key: "kind", header: "Type" },
              { key: "points", header: "Points", align: "right" },
              { key: "remaining", header: "Remaining", align: "right", render: (h) => h.remaining ?? "—" },
              { key: "expires", header: "Expires" },
              { key: "reason", header: "Reason", render: (h) => h.reason ?? "—" },
            ]}
          />
        </>
      )}
      <RecordDialog
        open={adjust}
        onOpenChange={setAdjust}
        title="Adjust loyalty points"
        description="A correction with a reason. It is audited."
        fields={[
          { name: "points", label: "Points (negative to remove)", type: "number", required: true, validate: (v) => (Number(v) === 0 ? "Can't be zero" : undefined) },
          { name: "reason", label: "Reason", required: true },
        ]}
        onSubmit={(v) => save(() => cus.adjustPoints(c.id, Math.trunc(Number(v.points)), String(v.reason))).then(reload)}
      />
    </Page>
  )
}
