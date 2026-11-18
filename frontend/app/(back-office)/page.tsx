"use client"

import * as React from "react"
import Link from "next/link"
import { Armchair, Banknote, ChefHat, ClipboardCheck, ClipboardList, Percent, RefreshCw, TrendingUp, Undo2, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ChartCard } from "@/components/rms/chart-card"
import { DataTable } from "@/components/rms/data-table"
import { MoneyText, Notice, Page, PageHeader, PageTabs, Panel, SimpleSelect, Stat, StatusBadge, useTab } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { METHOD_LABEL } from "@/lib/api/billing"
import { can, useSession } from "@/lib/api/session"
import { num, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

interface Dashboard {
  business_date: string
  from: string
  to: string
  calculated_at: string
  widgets: {
    sales?: { gross_sales: number; discounts: number; refunds: number; net_sales: number; service_charges: number; taxes: number; delivery_fees: number; finalised_bills: number }
    payments_by_method?: { method: string; currency: string; count: number; amount_in_currency: number; amount_base: number; refunds_base: number; net_collected_base: number }[]
    top_items?: { by_quantity: { item: string; quantity: number }[] }
    indicative_operating_result?: { value: number; label: string }
    costs?: { theoretical_food_cost: number; theoretical_food_cost_percent: number; approved_expenses: number; platform_commissions: number }
    trends?: { grain: string; series: { period_start: string; orders: number; net_sales: number }[] }
    orders?: { received: number; completed: number; cancelled: number; open: number; average_order_value: number }
    table_occupancy?: { occupied: number; active: number; percent: number }
    kitchen?: { station_code: string; pending_tickets: number; oldest_age_minutes: number }[]
    stock?: { low_stock_count: number; valuation: number }
    cashier_sessions?: { session_id: string; user_id: string; status: string; expected: Record<string, string> | null; results: { currency: string; variance: string }[] | null }[]
    my_session?: { session_id: string; opened_at: string } | null
  }
}

const RANGES = ["Today", "Yesterday", "Last 7 days", "This month", "Last 30 days"] as const
/** Business-date range for a named period, counted back from the branch's current business date. */
function range(name: string, today: string) {
  const d = (offset: number) => {
    const x = new Date(`${today}T12:00`)
    x.setDate(x.getDate() + offset)
    return x.toLocaleDateString("en-CA")
  }
  switch (name) {
    case "Yesterday":
      return { from: d(-1), to: d(-1), grain: "day" }
    case "Last 7 days":
      return { from: d(-6), to: today, grain: "day" }
    case "This month":
      return { from: `${today.slice(0, 8)}01`, to: today, grain: "day" }
    case "Last 30 days":
      return { from: d(-29), to: today, grain: "week" }
    default:
      return { from: today, to: today, grain: "day" }
  }
}

export default function DashboardPage() {
  const { me } = useSession()
  const [period, setPeriod] = React.useState<string>("Today")
  const [tab, setTab] = useTab("overview")
  const today = me?.business_date ?? new Date().toLocaleDateString("en-CA")
  const r = range(period, today)
  const dash = useApi(() => api<Dashboard>("GET", "/dashboard", { query: { date_from: r.from, date_to: r.to, trend: r.grain } }), [r.from, r.to, r.grain], null)
  // Trends need more than one day to be useful: always show the last 7 days.
  const week = range("Last 7 days", today)
  const trend = useApi(
    () => api<Dashboard>("GET", "/dashboard", { query: { date_from: week.from, date_to: week.to, trend: "day" } }).then((d) => d.widgets.trends?.series ?? []),
    [week.from],
    [] as { period_start: string; orders: number; net_sales: number }[]
  )
  const crossBranch = can(me, "report.cross_branch")
  const compare = useApi(
    () =>
      crossBranch && tab === "branches"
        ? api<{ rows: { branch_id: string; name: string; net_sales: string; orders: number; average_order_value: string; food_cost_percent: string; labour_hours: string; approved_expenses: string }[] }>("GET", "/branch-comparison", {
            query: { date_from: r.from, date_to: r.to },
          })
        : Promise.resolve(null),
    [crossBranch, tab, r.from, r.to],
    null
  )
  const users = useApi(
    async () => (can(me, "users.view") ? (await api<{ data: { id: string; full_name: string }[] }>("GET", "/users", { query: { page_size: 200 } })).data : []),
    [me?.id],
    []
  )
  const w = dash.data?.widgets ?? {}
  const financial = !!w.sales
  const nothing = dash.data && Object.keys(w).length === 0

  return (
    <Page>
      <PageHeader
        title="Dashboard"
        description={`${me?.current_branch.name_en ?? ""} · ${r.from === r.to ? r.from : `${r.from} – ${r.to}`}${dash.data ? ` · calculated ${when(dash.data.calculated_at).slice(11)}` : ""}`}
        actions={
          <>
            <SimpleSelect aria-label="Period" className="w-40" value={period} onChange={setPeriod} options={RANGES.map((x) => ({ value: x, label: x }))} />
            <Button variant="outline" onClick={() => [dash, trend, compare].forEach((x) => x.reload())}>
              <RefreshCw />
              Refresh
            </Button>
          </>
        }
      />
      {crossBranch && (
        <PageTabs
          tabs={[
            { value: "overview", label: "Overview" },
            { value: "branches", label: "Branch comparison" },
          ]}
          value={tab}
          onChange={setTab}
        />
      )}
      {tab === "branches" && crossBranch ? (
        <div className="grid gap-4">
          <ChartCard
            title="Net sales by branch"
            data={(compare.data?.rows ?? []).map((x) => ({ branch: x.name, net: num(x.net_sales) }))}
            xKey="branch"
            series={[{ key: "net", label: "Net sales" }]}
            format={(v) => `$${v.toLocaleString()}`}
          />
          <Panel title="Branch comparison">
            <DataTable
              rows={(compare.data?.rows ?? []).map((x) => ({ ...x, id: x.branch_id }))}
              exportName="branch-comparison"
              columns={[
                { key: "name", header: "Branch" },
                { key: "net_sales", header: "Net sales", align: "right", render: (x) => usd(num(x.net_sales)) },
                { key: "orders", header: "Orders", align: "right" },
                { key: "average_order_value", header: "AOV", align: "right", render: (x) => usd(num(x.average_order_value)) },
                { key: "food_cost_percent", header: "Food cost %", align: "right", render: (x) => `${num(x.food_cost_percent)}%` },
                { key: "labour_hours", header: "Labour hours", align: "right", render: (x) => num(x.labour_hours).toFixed(1) },
                { key: "approved_expenses", header: "Expenses", align: "right", render: (x) => usd(num(x.approved_expenses)) },
              ]}
            />
          </Panel>
        </div>
      ) : (
        <>
          {w.sales && (
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Sales">
              <Stat label="Gross sales" value={usd(w.sales.gross_sales)} icon={Banknote} href="/reports/RPT-01" hint="Before discounts" />
              <Stat label="Discounts" value={usd(w.sales.discounts)} icon={Percent} href="/reports/RPT-13" />
              <Stat label="Refunds" value={usd(w.sales.refunds)} icon={Undo2} href="/reports/RPT-12" />
              <Stat label="Net sales" value={usd(w.sales.net_sales)} icon={TrendingUp} href="/reports/RPT-01" hint="Gross − discounts − refunds" />
              <Stat label="Service charges" value={usd(w.sales.service_charges)} href="/reports/RPT-14" hint="Not part of net sales" />
              <Stat label="Taxes" value={usd(w.sales.taxes)} href="/reports/RPT-14" hint="Not part of net sales" />
              <Stat
                label="Payments collected"
                value={usd((w.payments_by_method ?? []).reduce((s, p) => s + num(p.net_collected_base), 0))}
                href="/billing?tab=payments"
                hint="Collections, separate from sales"
              />
              <Stat label="Average order value" value={usd(num(w.orders?.average_order_value))} href="/reports/RPT-08" />
            </section>
          )}
          {w.orders && (
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Orders">
              <Stat label="Orders received" value={w.orders.received} icon={ClipboardList} href="/orders" hint={`${w.orders.open} still open`} />
              <Stat label="Orders completed" value={w.orders.completed} icon={ClipboardCheck} href="/orders" />
              <Stat label="Orders cancelled" value={w.orders.cancelled} icon={XCircle} href="/reports/RPT-11" />
              {w.table_occupancy && (
                <Stat
                  label="Table occupancy"
                  value={`${Math.round(num(w.table_occupancy.percent))}%`}
                  icon={Armchair}
                  href="/tables"
                  hint={`${w.table_occupancy.occupied} of ${w.table_occupancy.active} tables, now`}
                />
              )}
            </section>
          )}
          <div className="grid gap-4 xl:grid-cols-3">
            {w.kitchen && (
              <Panel
                title="Pending kitchen tickets"
                description="Right now"
                actions={
                  <Link href="/kds" className="text-sm text-primary hover:underline">
                    Open KDS
                  </Link>
                }
              >
                {w.kitchen.length === 0 && <p className="text-sm text-muted-foreground">All stations are clear.</p>}
                <ul className="divide-y text-sm">
                  {w.kitchen.map((s) => (
                    <li key={s.station_code} className="flex items-center justify-between py-1.5">
                      <span className="flex items-center gap-2">
                        <ChefHat className="size-3.5 text-muted-foreground" />
                        {s.station_code}
                      </span>
                      <span className="flex items-center gap-3">
                        <span className="tabular text-xs text-muted-foreground">oldest {s.oldest_age_minutes} min</span>
                        {s.oldest_age_minutes >= 20 ? <StatusBadge status={`${s.pending_tickets} late`} tone="danger" /> : <span className="tabular w-8 text-right font-semibold">{s.pending_tickets}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
            {w.stock && (
              <Panel
                title="Stock"
                actions={
                  <Link href="/inventory" className="text-sm text-primary hover:underline">
                    Inventory
                  </Link>
                }
              >
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs text-muted-foreground">Low-stock items</p>
                    <p className="tabular text-2xl font-semibold">{w.stock.low_stock_count}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Valuation</p>
                    <p className="tabular text-2xl font-semibold">{usd(w.stock.valuation)}</p>
                  </div>
                </div>
              </Panel>
            )}
            {w.cashier_sessions && (
              <Panel
                title="Cashier sessions"
                actions={
                  <Link href="/shifts" className="text-sm text-primary hover:underline">
                    Shifts
                  </Link>
                }
              >
                {w.cashier_sessions.length === 0 && <p className="text-sm text-muted-foreground">No sessions yet.</p>}
                <ul className="divide-y text-sm">
                  {w.cashier_sessions.slice(0, 5).map((s) => (
                    <li key={s.session_id} className="flex items-center justify-between gap-2 py-1.5">
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{users.data.find((u) => u.id === s.user_id)?.full_name ?? "Cashier"}</span>
                        <span className="tabular text-xs text-muted-foreground">
                          {s.status === "Open"
                            ? s.expected
                              ? `Expected ${usd(num(s.expected.USD))}`
                              : "Open"
                            : `Variance ${usd(num(s.results?.find((x) => x.currency === "USD")?.variance))}`}
                        </span>
                      </span>
                      <StatusBadge status={s.status === "ClosingPendingApproval" ? "Pending Approval" : s.status} />
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
            {w.my_session !== undefined && (
              <Panel title="My cashier session">
                {w.my_session ? (
                  <p className="text-sm">Open since {when(w.my_session.opened_at).slice(11)}.</p>
                ) : (
                  <p className="text-sm">
                    No session open.{" "}
                    <Link className="underline" href="/shifts">
                      Open one
                    </Link>{" "}
                    before taking cash.
                  </p>
                )}
              </Panel>
            )}
          </div>
          {financial && (
            <>
              <div className="grid gap-4 xl:grid-cols-2">
                <ChartCard
                  title="Net sales trend"
                  description="Last 7 business days"
                  type="line"
                  data={trend.data.map((t) => ({ label: t.period_start.slice(5), sales: num(t.net_sales) }))}
                  xKey="label"
                  series={[{ key: "sales", label: "Net sales" }]}
                  format={(v) => `$${v.toLocaleString()}`}
                />
                <ChartCard
                  title="Orders trend"
                  description="Last 7 business days"
                  data={trend.data.map((t) => ({ label: t.period_start.slice(5), orders: t.orders }))}
                  xKey="label"
                  series={[{ key: "orders", label: "Orders" }]}
                />
                <ChartCard
                  title="Top 10 items by quantity"
                  horizontal
                  height={300}
                  data={(w.top_items?.by_quantity ?? []).map((t) => ({ item: t.item, qty: num(t.quantity) }))}
                  xKey="item"
                  series={[{ key: "qty", label: "Quantity" }]}
                />
                <Panel title="Payments by method">
                  {(w.payments_by_method ?? []).length === 0 && <p className="text-sm text-muted-foreground">No payments in this period.</p>}
                  <ul className="divide-y text-sm">
                    {(w.payments_by_method ?? []).map((p) => (
                      <li key={`${p.method}-${p.currency}`} className="flex justify-between py-1.5">
                        <span>
                          {METHOD_LABEL[p.method] ?? p.method} <span className="text-xs text-muted-foreground">{p.count} payments</span>
                        </span>
                        <MoneyText value={num(p.net_collected_base)} />
                      </li>
                    ))}
                  </ul>
                </Panel>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                {w.costs && (
                  <Panel title="Cost indicators">
                    <ul className="divide-y text-sm">
                      <li className="flex justify-between py-1.5">
                        <span>Theoretical food cost</span>
                        <span className="tabular font-medium">
                          {usd(w.costs.theoretical_food_cost)} ({num(w.costs.theoretical_food_cost_percent)}%)
                        </span>
                      </li>
                      <li className="flex justify-between py-1.5">
                        <span>Approved expenses</span>
                        <MoneyText value={w.costs.approved_expenses} />
                      </li>
                      <li className="flex justify-between py-1.5">
                        <span>Platform commissions</span>
                        <MoneyText value={w.costs.platform_commissions} />
                      </li>
                    </ul>
                  </Panel>
                )}
                {w.indicative_operating_result && (
                  <Panel title="Indicative operating result">
                    <p className="tabular text-3xl font-semibold">{usd(w.indicative_operating_result.value)}</p>
                    <Notice tone="neutral" className="mt-2">
                      {w.indicative_operating_result.label}
                    </Notice>
                  </Panel>
                )}
              </div>
            </>
          )}
          {nothing && <Notice tone="info">Your role has no dashboard widgets. Use the menu to open your screens.</Notice>}
        </>
      )}
    </Page>
  )
}
