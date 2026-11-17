"use client"

import * as React from "react"
import Link from "next/link"
import {
  Armchair,
  Banknote,
  ChefHat,
  ClipboardCheck,
  ClipboardList,
  Percent,
  TrendingUp,
  Undo2,
  XCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { ChartCard } from "@/components/rms/chart-card"
import { DataTable } from "@/components/rms/data-table"
import {
  DateRangeFilter,
  MoneyText,
  Notice,
  Page,
  PageHeader,
  PageTabs,
  Panel,
  Stat,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import { ingredients } from "@/lib/rms/back-office"
import { financialRoles, roleLabels } from "@/lib/rms/nav"
import {
  expectedCash,
  mmss,
  ticketsFor,
  useClock,
  useRms,
} from "@/lib/rms/store"
import type { Station } from "@/lib/rms/types"

const scale: Record<string, number> = {
  Today: 1,
  Yesterday: 1.08,
  "This week": 6.4,
  "This month": 26.5,
  Custom: 12,
}
const trend = [
  ["Mon", 1820, 118],
  ["Tue", 1695, 109],
  ["Wed", 2040, 131],
  ["Thu", 2210, 142],
  ["Fri", 2860, 186],
  ["Sat", 3240, 214],
  ["Sun", 2480, 163],
].map(([label, sales, orders]) => ({ label, sales, orders })) as {
  label: string
  sales: number
  orders: number
}[]
const topQty = [
  ["Fried Rice", 38],
  ["Iced Coffee", 34],
  ["Beef Lok Lak", 26],
  ["Fish Amok", 22],
  ["Kuy Teav", 21],
  ["Draft Beer", 19],
  ["Latte", 15],
  ["Mango Salad", 12],
  ["Spring Rolls", 11],
  ["Palm Juice", 9],
].map(([item, qty]) => ({ item, qty })) as { item: string; qty: number }[]
const byCategory = [
  ["Khmer Mains", 742],
  ["Rice & Noodles", 498],
  ["Coffee & Tea", 214],
  ["Beer & Cocktails", 186],
  ["Soups", 142],
  ["Starters", 96],
  ["Desserts", 64],
].map(([category, net]) => ({ category, net })) as {
  category: string
  net: number
}[]
const payments = [
  { id: "1", method: "Cash USD", currency: "USD", amount: 742.5 },
  { id: "2", method: "Cash KHR", currency: "KHR", amount: 312.3 },
  { id: "3", method: "KHQR", currency: "USD", amount: 684.2 },
  { id: "4", method: "Card", currency: "USD", amount: 196 },
  { id: "5", method: "Bank Transfer", currency: "USD", amount: 42 },
]
const branchRows = [
  {
    id: "b1",
    branch: "Riverside",
    net: 2142,
    orders: 151,
    aov: 14.19,
    food: 31.4,
    expenses: 412,
    labour: 186,
  },
  {
    id: "b2",
    branch: "BKK1",
    net: 1688,
    orders: 124,
    aov: 13.61,
    food: 33.8,
    expenses: 305,
    labour: 142,
  },
  {
    id: "b3",
    branch: "Siem Reap",
    net: 1294,
    orders: 88,
    aov: 14.7,
    food: 29.6,
    expenses: 261,
    labour: 118,
  },
]
const stations: Station[] = ["Hot", "Cold", "Beverage", "Dessert", "Bar"]

export default function DashboardPage() {
  const { role, orders, tables, sessions, branch } = useRms()
  const at = useClock()
  const [range, setRange] = React.useState("Today")
  const [tab, setTab] = useTab("overview")
  const k = scale[range]
  const m = (n: number) => usd(n * k)
  const financial = financialRoles.includes(role)
  const ops = financial || role === "SUPV"
  const showKitchen = ops || role === "KMGR"
  const showStock = financial || ["INVOFF", "KMGR", "PUROFF"].includes(role)

  const active = tables.filter((t) => !t.outOfService)
  const occupied = active.filter((t) =>
    ["Seated", "Ordering", "Served", "Awaiting Payment"].includes(t.state)
  )
  const low = ingredients.filter((i) => i.onHand <= i.reorder)
  const value = ingredients.reduce(
    (s, i) => s + Math.max(i.onHand, 0) * i.cost,
    0
  )
  const kitchen = stations.map((s) => {
    const list = ticketsFor(orders, at, s)
    return {
      station: s,
      count: list.length,
      oldest: list.length ? Math.max(...list.map((t) => t.age)) : 0,
    }
  })

  return (
    <Page>
      <PageHeader
        title="Dashboard"
        description={`${roleLabels[role]} view for ${branch}, calculated at 13:02. Values are illustrative.`}
        actions={
          <>
            <DateRangeFilter value={range} onChange={setRange} />
            <Button variant="outline" onClick={() => setRange(range)}>
              Refresh
            </Button>
          </>
        }
      />
      {financial && (
        <PageTabs
          tabs={[
            { value: "overview", label: "Overview" },
            { value: "branches", label: "Branch comparison" },
          ]}
          value={tab}
          onChange={setTab}
        />
      )}
      {tab === "branches" && financial ? (
        <div className="grid gap-4">
          <ChartCard
            title="Net sales by branch"
            data={branchRows}
            xKey="branch"
            series={[{ key: "net", label: "Net sales" }]}
            format={(v) => `$${v.toLocaleString()}`}
          />
          <Panel title="Branch comparison">
            <DataTable
              rows={branchRows}
              exportName="branch-comparison"
              columns={[
                { key: "branch", header: "Branch" },
                {
                  key: "net",
                  header: "Net sales",
                  align: "right",
                  render: (r) => usd(r.net),
                },
                { key: "orders", header: "Orders", align: "right" },
                {
                  key: "aov",
                  header: "AOV",
                  align: "right",
                  render: (r) => usd(r.aov),
                },
                {
                  key: "food",
                  header: "Food cost %",
                  align: "right",
                  render: (r) => `${r.food}%`,
                },
                { key: "labour", header: "Labour hours", align: "right" },
                {
                  key: "expenses",
                  header: "Expenses",
                  align: "right",
                  render: (r) => usd(r.expenses),
                },
              ]}
            />
          </Panel>
        </div>
      ) : (
        <>
          {financial && (
            <section
              className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
              aria-label="Sales"
            >
              <Stat
                label="Gross sales"
                value={m(2318.4)}
                icon={Banknote}
                href="/reports/RPT-01"
                hint="Before discounts"
              />
              <Stat
                label="Discounts"
                value={m(98.2)}
                icon={Percent}
                href="/reports/RPT-13"
              />
              <Stat
                label="Refunds"
                value={m(12.4)}
                icon={Undo2}
                href="/reports/RPT-12"
              />
              <Stat
                label="Net sales"
                value={m(2207.8)}
                icon={TrendingUp}
                href="/reports/RPT-01"
                hint="Gross − discounts − refunds"
              />
              <Stat
                label="Service charges"
                value={m(102.4)}
                href="/reports/RPT-14"
                hint="Not part of net sales"
              />
              <Stat
                label="Taxes"
                value={m(231.0)}
                href="/reports/RPT-14"
                hint="Not part of net sales"
              />
              <Stat
                label="Payments collected"
                value={m(1977)}
                href="/billing?tab=payments"
                hint="Collections, separate from sales"
              />
              <Stat
                label="Average order value"
                value={usd(14.62)}
                href="/reports/RPT-08"
              />
            </section>
          )}
          {ops && (
            <section
              className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
              aria-label="Orders"
            >
              <Stat
                label="Orders received"
                value={Math.round(163 * k)}
                icon={ClipboardList}
                href="/orders"
              />
              <Stat
                label="Orders completed"
                value={Math.round(151 * k)}
                icon={ClipboardCheck}
                href="/orders"
              />
              <Stat
                label="Orders cancelled"
                value={Math.round(4 * k)}
                icon={XCircle}
                href="/reports/RPT-11"
              />
              <Stat
                label="Table occupancy"
                value={`${Math.round((occupied.length / active.length) * 100)}%`}
                icon={Armchair}
                href="/tables"
                hint={`${occupied.length} of ${active.length} tables, live`}
              />
            </section>
          )}
          <div className="grid gap-4 xl:grid-cols-3">
            {showKitchen && (
              <Panel
                title="Pending kitchen tickets"
                description="Live, refreshed automatically"
                actions={
                  <Link
                    href="/kds"
                    className="text-sm text-primary hover:underline"
                  >
                    Open KDS
                  </Link>
                }
              >
                <ul className="divide-y text-sm">
                  {kitchen.map((s) => (
                    <li
                      key={s.station}
                      className="flex items-center justify-between py-1.5"
                    >
                      <span className="flex items-center gap-2">
                        <ChefHat className="size-3.5 text-muted-foreground" />
                        {s.station}
                      </span>
                      <span className="flex items-center gap-3">
                        <span className="tabular text-xs text-muted-foreground">
                          {s.count ? `oldest ${mmss(s.oldest)}` : "clear"}
                        </span>
                        {s.oldest >= 1200 ? (
                          <StatusBadge
                            status={`${s.count} late`}
                            tone="danger"
                          />
                        ) : (
                          <span className="tabular w-8 text-right font-semibold">
                            {s.count}
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
            {showStock && (
              <Panel
                title="Stock"
                actions={
                  <Link
                    href="/inventory"
                    className="text-sm text-primary hover:underline"
                  >
                    Inventory
                  </Link>
                }
              >
                <div className="grid grid-cols-2 gap-3 pb-2">
                  <div>
                    <p className="text-xs text-muted-foreground">
                      Low-stock items
                    </p>
                    <p className="tabular text-2xl font-semibold">
                      {low.length}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Valuation</p>
                    <p className="tabular text-2xl font-semibold">
                      {usd(value)}
                    </p>
                  </div>
                </div>
                <ul className="divide-y text-sm">
                  {low.slice(0, 4).map((i) => (
                    <li
                      key={i.id}
                      className="flex items-center justify-between py-1.5"
                    >
                      <span>{i.name}</span>
                      <span className="tabular text-xs text-muted-foreground">
                        {i.onHand} / {i.reorder} {i.unit}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
            {(financial || role === "SUPV" || role === "CASHIER") && (
              <Panel
                title="Cashier sessions"
                actions={
                  <Link
                    href="/shifts"
                    className="text-sm text-primary hover:underline"
                  >
                    Shifts
                  </Link>
                }
              >
                <ul className="divide-y text-sm">
                  {sessions.slice(0, 4).map((s) => {
                    const e = expectedCash(s)
                    return (
                      <li
                        key={s.id}
                        className="flex items-center justify-between gap-2 py-1.5"
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-medium">
                            {s.cashier}
                          </span>
                          <span className="tabular text-xs text-muted-foreground">
                            {s.status === "Open"
                              ? `Expected ${usd(e.usd)}`
                              : `Variance ${usd(s.varianceUSD ?? 0)}`}
                          </span>
                        </span>
                        <StatusBadge status={s.status} />
                      </li>
                    )
                  })}
                </ul>
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
                  data={trend}
                  xKey="label"
                  series={[{ key: "sales", label: "Net sales" }]}
                  format={(v) => `$${v.toLocaleString()}`}
                />
                <ChartCard
                  title="Orders trend"
                  description="Last 7 business days"
                  data={trend}
                  xKey="label"
                  series={[{ key: "orders", label: "Orders" }]}
                />
                <ChartCard
                  title="Top 10 items by quantity"
                  horizontal
                  height={300}
                  data={topQty}
                  xKey="item"
                  series={[{ key: "qty", label: "Quantity" }]}
                />
                <ChartCard
                  title="Net sales by category"
                  horizontal
                  height={300}
                  data={byCategory}
                  xKey="category"
                  series={[{ key: "net", label: "Net sales" }]}
                  format={(v) => `$${v}`}
                />
              </div>
              <div className="grid gap-4 xl:grid-cols-3">
                <Panel title="Payments by method" className="xl:col-span-1">
                  <ul className="divide-y text-sm">
                    {payments.map((p) => (
                      <li key={p.id} className="flex justify-between py-1.5">
                        <span>
                          {p.method}{" "}
                          <span className="text-xs text-muted-foreground">
                            {p.currency}
                          </span>
                        </span>
                        <MoneyText value={p.amount * k} />
                      </li>
                    ))}
                  </ul>
                </Panel>
                <Panel title="Cost indicators">
                  <ul className="divide-y text-sm">
                    <li className="flex justify-between py-1.5">
                      <span>Theoretical food cost</span>
                      <span className="tabular font-medium">31.4%</span>
                    </li>
                    <li className="flex justify-between py-1.5">
                      <span>Approved expenses</span>
                      <MoneyText value={412.6 * k} />
                    </li>
                    <li className="flex justify-between py-1.5">
                      <span>Inventory valuation</span>
                      <MoneyText value={value} />
                    </li>
                  </ul>
                </Panel>
                <Panel title="Indicative operating result">
                  <p className="tabular text-3xl font-semibold">{m(1102.4)}</p>
                  <Notice tone="neutral" className="mt-2">
                    Indicative — not accounting profit.
                  </Notice>
                </Panel>
              </div>
            </>
          )}
          {!financial && !showKitchen && !showStock && role !== "CASHIER" && (
            <Notice tone="info">
              <span>
                Your role has only technical dashboard widgets.{" "}
                <Link className="underline" href="/settings?tab=devices">
                  View devices
                </Link>
              </span>
            </Notice>
          )}
        </>
      )}
    </Page>
  )
}
