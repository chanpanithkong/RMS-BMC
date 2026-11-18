"use client"

import { Layers, MonitorPlay, Timer } from "lucide-react"
import { DataTable } from "@/components/rms/data-table"
import Link from "next/link"
import {
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
import { useLiveSync } from "@/lib/api/pos"
import { mmss, ticketsFor, useClock, useRms } from "@/lib/rms/store"
import type { Station } from "@/lib/rms/types"

const stations: Station[] = ["Hot", "Cold", "Beverage", "Dessert", "Bar"]
const STATION_CODES = ["HOT", "COLD", "BEV", "DESSERT", "BAR"]

export default function KitchenPage() {
  const { orders } = useRms()
  const at = useClock()
  const [tab, setTab] = useTab("live")
  const live = ticketsFor(orders, at)
  // Live tickets of every station, kept current over the WebSocket.
  useLiveSync(STATION_CODES)
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
      {tab === "timing" && (
        <Notice tone="info">
          Ticket times by station, with averages and late tickets, are in the report{" "}
          <Link className="underline" href="/reports/RPT-15">
            Kitchen preparation time
          </Link>
          .
        </Notice>
      )}
    </Page>
  )
}
