"use client"

import { Layers, MonitorPlay, Timer } from "lucide-react"
import { DataTable } from "@/components/rms/data-table"
import {
  LinkButton,
  Page,
  PageHeader,
  PageTabs,
  Panel,
  Stat,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { mmss, ticketsFor, useClock, useRms } from "@/lib/rms/store"
import type { Station } from "@/lib/rms/types"

const stations: Station[] = ["Hot", "Cold", "Beverage", "Dessert", "Bar"]
const prep: Record<Station, [number, number, number]> = {
  Hot: [12.4, 19.2, 7],
  Cold: [6.1, 9.8, 1],
  Beverage: [3.4, 5.5, 0],
  Dessert: [5.2, 8.1, 0],
  Bar: [4.1, 6.9, 1],
  None: [0, 0, 0],
}

export default function KitchenPage() {
  const { orders } = useRms()
  const at = useClock()
  const [tab, setTab] = useTab("live")
  const live = ticketsFor(orders, at)
  const history = orders.flatMap((o) =>
    [
      ...new Set(
        o.lines
          .filter((l) => l.station !== "None" && l.sentAt !== undefined)
          .map((l) => l.station)
      ),
    ].map((s) => {
      const lines = o.lines.filter((l) => l.station === s)
      const open = lines.some(
        (l) => l.status === "Sent" || l.status === "In Preparation"
      )
      return {
        id: `${o.id}-${s}`,
        ticket: `${o.no}-${s[0]}`,
        order: o.no,
        station: s,
        items: lines.reduce((n, l) => n + l.qty, 0),
        status: lines.every((l) => l.status === "Cancelled")
          ? "Cancelled"
          : open
            ? "In Progress"
            : "Completed",
        prep: open
          ? "—"
          : `${8 + (o.lines.length % 7)}:${String((o.no.charCodeAt(4) * 7) % 60).padStart(2, "0")}`,
      }
    })
  )
  return (
    <Page>
      <PageHeader
        title="Kitchen"
        description="Station boards run full-screen. Use this page for supervision, history and timing."
        actions={
          <>
            <LinkButton href="/kds">
              <MonitorPlay />
              Station KDS
            </LinkButton>
            <LinkButton href="/kds/expo" variant="outline">
              <Layers />
              Expo screen
            </LinkButton>
            <LinkButton href="/ready-board" variant="outline">
              Ready board
            </LinkButton>
          </>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "live", label: "Live queue", count: live.length },
          { value: "history", label: "Ticket history" },
          { value: "timing", label: "Preparation time" },
        ]}
      />
      {tab === "live" && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {stations.map((s) => {
              const n = live.filter((t) => t.station === s)
              const old = n.length ? Math.max(...n.map((t) => t.age)) : 0
              return (
                <Stat
                  key={s}
                  label={s}
                  value={n.length}
                  icon={Timer}
                  tone={
                    old >= 1200 ? "danger" : old >= 600 ? "warning" : undefined
                  }
                  hint={n.length ? `Oldest ${mmss(old)}` : "Queue clear"}
                />
              )
            })}
          </section>
          <Panel title="Queue">
            <DataTable
              rows={live.map((t) => ({
                ...t,
                id: `${t.order.id}-${t.station}`,
              }))}
              exportName="kitchen-queue"
              emptyTitle="Queue is clear"
              columns={[
                { key: "order", header: "Order", value: (t) => t.order.no },
                { key: "station", header: "Station" },
                {
                  key: "where",
                  header: "Where",
                  value: (t) =>
                    t.order.table
                      ? `Table ${t.order.table}`
                      : (t.order.pickup ?? "Delivery"),
                },
                {
                  key: "items",
                  header: "Items",
                  value: (t) =>
                    t.lines.map((l) => `${l.qty}× ${l.name}`).join(", "),
                },
                {
                  key: "age",
                  header: "Age",
                  align: "right",
                  value: (t) => t.age,
                  render: (t) => mmss(t.age),
                },
                {
                  key: "state",
                  header: "State",
                  render: (t) => (
                    <StatusBadge
                      status={
                        t.age >= 1200
                          ? "Critical"
                          : t.age >= 600
                            ? "Late"
                            : "On time"
                      }
                      tone={
                        t.age >= 1200
                          ? "danger"
                          : t.age >= 600
                            ? "warning"
                            : "success"
                      }
                    />
                  ),
                },
              ]}
            />
          </Panel>
        </>
      )}
      {tab === "history" && (
        <DataTable
          rows={history}
          exportName="ticket-history"
          pageSize={12}
          filters={[
            { key: "station", label: "Station", options: stations },
            {
              key: "status",
              label: "Status",
              options: ["In Progress", "Completed", "Cancelled"],
            },
          ]}
          columns={[
            { key: "ticket", header: "Ticket" },
            { key: "order", header: "Order" },
            { key: "station", header: "Station" },
            { key: "items", header: "Items", align: "right" },
            { key: "prep", header: "Ticket time", align: "right" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
        />
      )}
      {tab === "timing" && (
        <DataTable
          rows={stations.map((s) => ({
            id: s,
            station: s,
            avg: prep[s][0],
            p90: prep[s][1],
            late: prep[s][2],
          }))}
          exportName="prep-time"
          columns={[
            { key: "station", header: "Station" },
            { key: "avg", header: "Average (min)", align: "right" },
            { key: "p90", header: "90th percentile (min)", align: "right" },
            { key: "late", header: "Late tickets", align: "right" },
          ]}
        />
      )}
    </Page>
  )
}
