"use client"

import { Layers, MonitorPlay, RotateCcw, Timer } from "lucide-react"
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
import { api } from "@/lib/api/client"
import { useLiveSync } from "@/lib/api/pos"
import { act, useApi, when } from "@/lib/api/use-api"
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
          { value: "history", label: "History" },
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
      {tab === "history" && <TicketHistory />}
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

interface Done {
  ticket_id: string
  ticket_no: number
  station_code: string
  order_no: string
  order_type: string
  where: string | null
  items: string
  cancelled_items: number
  created_at: string
  bumped_at: string
  prep_seconds: number
  order_open: boolean
}
const STATION_NAME: Record<string, string> = { HOT: "Hot", COLD: "Cold", BEV: "Beverage", DESSERT: "Dessert", BAR: "Bar" }

/** Today's finished (bumped) tickets with preparation time; Recall puts one back on its station screen. */
function TicketHistory() {
  const list = useApi(() => api<Done[]>("GET", "/kitchen/tickets/history"), [], [])
  return (
    <DataTable
      rows={list.data.map((t) => ({ ...t, id: t.ticket_id, station: STATION_NAME[t.station_code] ?? t.station_code, prep: mmss(t.prep_seconds) }))}
      exportName="kitchen-history"
      emptyTitle={list.loading ? "Loading…" : "No finished tickets yet today"}
      searchValue={(t) => `${t.order_no} ${t.where ?? ""} ${t.items}`}
      filters={[{ key: "station", label: "Station", options: stations }]}
      columns={[
        { key: "ticket_no", header: "Ticket", align: "right" },
        { key: "order_no", header: "Order" },
        { key: "where", header: "Table / name", value: (t) => t.where ?? "" },
        { key: "station", header: "Station" },
        { key: "items", header: "Items", render: (t) => <span>{t.items}{t.cancelled_items > 0 && <span className="text-muted-foreground"> · {t.cancelled_items} cancelled</span>}</span> },
        { key: "created_at", header: "Sent", value: (t) => when(t.created_at) },
        { key: "bumped_at", header: "Bumped", value: (t) => when(t.bumped_at) },
        { key: "prep", header: "Time", align: "right", value: (t) => t.prep_seconds, render: (t) => <span className="tabular">{t.prep}</span> },
      ]}
      rowActions={(t) =>
        t.order_open
          ? [{ label: "Recall to the screen", icon: RotateCcw, onClick: () => void act(() => api("POST", `/kitchen/tickets/${t.ticket_id}/recall`), `Ticket ${t.ticket_no} recalled`, list.reload) }]
          : []
      }
    />
  )
}
