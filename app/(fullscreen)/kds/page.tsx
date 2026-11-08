"use client"

import * as React from "react"
import {
  AlertOctagon,
  ArrowUpToLine,
  History,
  Layers,
  Undo2,
  Wifi,
  WifiOff,
  Menu as MenuIcon,
} from "lucide-react"
import { toast } from "sonner"
import { confirmAction } from "@/components/rms/dialog-host"
import { LinkButton } from "@/components/rms/kit"
import {
  mmss,
  rms,
  ticketsFor,
  useClock,
  useRms,
  type Ticket,
} from "@/lib/rms/store"
import type { OrderLine, Station } from "@/lib/rms/types"
import { cn } from "@/lib/utils"

const WARN = 600
const CRIT = 1200
const stations: (Station | "All")[] = [
  "All",
  "Hot",
  "Cold",
  "Beverage",
  "Dessert",
  "Bar",
]

function TicketCard({ t }: { t: Ticket }) {
  const crit = t.age >= CRIT,
    warn = t.age >= WARN
  const modified = t.lines.some((l) => l.modified || l.status === "Cancelled")
  const tap = (l: OrderLine) => {
    if (l.status === "Sent")
      rms.setLineStatus(t.order.id, l.id, "In Preparation")
    else if (l.status === "In Preparation")
      rms.setLineStatus(t.order.id, l.id, "Ready")
    else if (l.status === "Cancelled" && l.voidType === "After preparation")
      confirmAction({
        title: `${l.name} was prepared`,
        effect:
          "Record what happens to this prepared item. Waste will reduce stock.",
        reasons: ["Wastage", "Reusable"],
        onConfirm: (r) => toast.success(`Marked as ${r.toLowerCase()}`),
      })
  }
  return (
    <article
      className={cn(
        "flex w-72 shrink-0 flex-col overflow-hidden rounded-xl border-2 bg-zinc-900 text-zinc-50",
        crit ? "border-red-500" : warn ? "border-yellow-400" : "border-zinc-600"
      )}
    >
      <header
        className={cn(
          "flex items-center justify-between px-3 py-2",
          crit
            ? "bg-red-600 text-white"
            : warn
              ? "bg-yellow-400 text-zinc-950"
              : "bg-zinc-100 text-zinc-950"
        )}
      >
        <div>
          <p className="text-xl leading-none font-bold">{t.order.no}</p>
          <p className="mt-0.5 text-xs font-medium">
            {t.order.type === "DINE_IN"
              ? `Table ${t.order.table}`
              : `${t.order.type === "TAKEAWAY" ? "Takeaway" : "Delivery"} · ${t.order.pickup ?? "—"}`}{" "}
            · {t.order.server}
          </p>
        </div>
        <div className="text-right">
          <p className="tabular text-2xl leading-none font-bold">
            {mmss(t.age)}
          </p>
          <p className="text-[11px] font-semibold">
            {crit ? "CRITICAL" : warn ? "LATE" : "NEW"} · {t.station}
          </p>
        </div>
      </header>
      {t.rush && (
        <p className="flex items-center gap-1 bg-orange-500 px-3 py-0.5 text-sm font-bold text-zinc-950">
          <ArrowUpToLine className="size-4" />
          RUSH
        </p>
      )}
      {modified && (
        <p className="bg-blue-500 px-3 py-0.5 text-sm font-bold text-white">
          ORDER MODIFIED
        </p>
      )}
      <ul className="flex-1 divide-y divide-zinc-700">
        {t.lines.map((l) => (
          <li key={l.id}>
            <button
              onClick={() => tap(l)}
              className={cn(
                "w-full px-3 py-2 text-left hover:bg-zinc-800",
                l.status === "Cancelled" && "text-zinc-500 line-through",
                l.status === "Ready" && "bg-emerald-950 text-emerald-300",
                l.status === "In Preparation" && "bg-zinc-800"
              )}
            >
              <span className="flex items-baseline justify-between gap-2">
                <span className="text-lg font-semibold">
                  <span className="tabular mr-1.5">{l.qty}×</span>
                  {l.name}
                  {l.variant && ` (${l.variant})`}
                </span>
                <span className="shrink-0 text-[11px] font-semibold uppercase">
                  {l.status === "In Preparation"
                    ? "Cooking"
                    : l.status === "Sent"
                      ? ""
                      : l.status}
                </span>
              </span>
              {l.modifiers.length > 0 && (
                <span className="block text-base font-bold text-amber-300">
                  {l.modifiers.map((m) => m.name).join(" · ")}
                </span>
              )}
              {l.note && (
                <span
                  className={cn(
                    "mt-0.5 flex items-center gap-1 text-base",
                    l.allergy
                      ? "rounded bg-red-600 px-1.5 font-bold text-white"
                      : "text-sky-300"
                  )}
                >
                  {l.allergy && <AlertOctagon className="size-4 shrink-0" />}
                  {l.note}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      <footer className="grid grid-cols-[auto_1fr_1fr] gap-1 border-t border-zinc-700 p-1.5">
        <button
          aria-label={t.rush ? "Remove rush" : "Mark rush"}
          aria-pressed={t.rush}
          onClick={() => rms.toggleRush(t.order.id, t.station)}
          className={cn(
            "touch-target rounded-lg px-2 text-sm font-semibold",
            t.rush ? "bg-orange-500 text-zinc-950" : "bg-zinc-800"
          )}
        >
          <ArrowUpToLine className="mx-auto size-5" />
        </button>
        <button
          className="touch-target rounded-lg bg-zinc-700 font-semibold hover:bg-zinc-600"
          onClick={() => rms.startTicket(t.order.id, t.station)}
        >
          Start
        </button>
        <button
          className="touch-target rounded-lg bg-emerald-500 font-bold text-zinc-950 hover:bg-emerald-400"
          onClick={() => rms.bump(t.order.id, t.station)}
        >
          Bump
        </button>
      </footer>
    </article>
  )
}

export default function KdsPage() {
  const { orders, recalled } = useRms()
  const at = useClock()
  const [station, setStation] = React.useState<Station | "All">("All")
  const [connected, setConnected] = React.useState(true)
  const tickets = ticketsFor(
    orders,
    at,
    station === "All" ? undefined : station
  )

  const allDay = new Map<string, number>()
  tickets.forEach((t) =>
    t.lines
      .filter((l) => l.status === "Sent" || l.status === "In Preparation")
      .forEach((l) => allDay.set(l.name, (allDay.get(l.name) ?? 0) + l.qty))
  )

  return (
    <div className="dark flex h-svh flex-col bg-zinc-950 text-zinc-50">
      <header className="flex flex-wrap items-center gap-2 border-b border-zinc-800 p-2">
        <LinkButton
          href="/kitchen"
          variant="outline"
          size="icon-lg"
          aria-label="Back office menu"
        >
          <MenuIcon />
        </LinkButton>
        <nav className="flex gap-1" aria-label="Stations">
          {stations.map((s) => {
            const n = ticketsFor(orders, at, s === "All" ? undefined : s).length
            return (
              <button
                key={s}
                aria-current={station === s ? "true" : undefined}
                onClick={() => setStation(s)}
                className={cn(
                  "touch-target rounded-lg px-4 text-base font-semibold",
                  station === s
                    ? "bg-zinc-100 text-zinc-950"
                    : "bg-zinc-800 text-zinc-100"
                )}
              >
                {s} <span className="tabular opacity-70">{n}</span>
              </button>
            )
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <LinkButton href="/kds/expo" variant="outline" className="h-11">
            <Layers />
            Expo
          </LinkButton>
          <LinkButton
            href="/kitchen?tab=history"
            variant="outline"
            className="h-11"
          >
            <History />
            History
          </LinkButton>
          <button
            disabled={!recalled.length}
            onClick={() => {
              const r = rms.recall()
              if (r) toast.success("Last ticket recalled")
            }}
            className="touch-target flex items-center gap-1.5 rounded-lg bg-zinc-800 px-3 font-semibold disabled:opacity-40"
          >
            <Undo2 className="size-4" />
            Recall
          </button>
          <button
            onClick={() => setConnected(!connected)}
            aria-label="Toggle connection (demo)"
            className={cn(
              "touch-target flex items-center gap-1.5 rounded-lg px-3 text-sm font-semibold",
              connected ? "text-emerald-400" : "bg-red-600 text-white"
            )}
          >
            {connected ? (
              <Wifi className="size-4" />
            ) : (
              <WifiOff className="size-4" />
            )}
            {connected ? "Connected" : "Offline: backup printer"}
          </button>
        </div>
      </header>
      {allDay.size > 0 && (
        <div
          className="flex gap-4 overflow-x-auto border-b border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm"
          aria-label="All-day counts"
        >
          <span className="shrink-0 font-semibold text-zinc-400">All day</span>
          {[...allDay].map(([n, q]) => (
            <span key={n} className="shrink-0">
              <b className="tabular text-amber-300">{q}×</b> {n}
            </span>
          ))}
        </div>
      )}
      <main className="flex min-h-0 flex-1 items-start gap-3 overflow-x-auto p-3">
        {tickets.length === 0 ? (
          <p className="m-auto text-2xl font-semibold text-zinc-500">
            All clear. No tickets in the queue.
          </p>
        ) : (
          tickets.map((t) => (
            <TicketCard key={`${t.order.id}-${t.station}`} t={t} />
          ))
        )}
      </main>
      <footer className="flex items-center gap-4 border-t border-zinc-800 px-3 py-1 text-xs text-zinc-400">
        <span>
          Tap an item to start, tap again when ready. Bump finishes the ticket.
        </span>
        <span className="ml-auto flex items-center gap-3">
          <span>
            <i className="mr-1 inline-block size-2.5 rounded-sm bg-zinc-100" />
            New
          </span>
          <span>
            <i className="mr-1 inline-block size-2.5 rounded-sm bg-yellow-400" />
            Over 10 min
          </span>
          <span>
            <i className="mr-1 inline-block size-2.5 rounded-sm bg-red-600" />
            Over 20 min
          </span>
        </span>
      </footer>
    </div>
  )
}
