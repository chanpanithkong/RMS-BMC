"use client"

import { Check, ChefHat, Clock3, Menu as MenuIcon } from "lucide-react"
import { toast } from "sonner"
import { LinkButton } from "@/components/rms/kit"
import { kitchenStatus } from "@/lib/rms/billing"
import { minLabel, rms, useClock, useRms } from "@/lib/rms/store"
import type { Order, Station } from "@/lib/rms/types"
import { cn } from "@/lib/utils"

const stations: Station[] = ["Hot", "Cold", "Beverage", "Dessert", "Bar"]

function cell(o: Order, s: Station) {
  const lines = o.lines.filter(
    (l) => l.station === s && l.status !== "Cancelled" && l.status !== "Pending"
  )
  if (!lines.length) return null
  const done = lines.filter(
    (l) => !["Sent", "In Preparation"].includes(l.status)
  ).length
  return {
    done,
    total: lines.length,
    cooking: lines.some((l) => l.status === "In Preparation"),
  }
}

export default function ExpoPage() {
  const { orders } = useRms()
  const at = useClock()
  const rows = orders.filter(
    (o) =>
      o.status === "Open" &&
      kitchenStatus(o) !== "Not Sent" &&
      kitchenStatus(o) !== "Served"
  )
  return (
    <div className="dark flex min-h-svh flex-col bg-zinc-950 text-zinc-50">
      <header className="flex items-center gap-3 border-b border-zinc-800 p-2">
        <LinkButton
          href="/kds"
          variant="outline"
          size="icon-lg"
          aria-label="Back to stations"
        >
          <MenuIcon />
        </LinkButton>
        <h1 className="text-xl font-bold">Expo</h1>
        <span className="text-sm text-zinc-400">
          {rows.length} active orders
        </span>
      </header>
      <main className="overflow-x-auto p-3">
        <table className="w-full min-w-3xl border-separate border-spacing-y-1.5 text-left">
          <thead className="text-sm text-zinc-400">
            <tr>
              <th className="px-3 py-1 font-medium">Order</th>
              <th className="font-medium">Where</th>
              {stations.map((s) => (
                <th key={s} className="text-center font-medium">
                  {s}
                </th>
              ))}
              <th className="text-right font-medium">Age</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => {
              const ready = kitchenStatus(o) === "Ready"
              return (
                <tr
                  key={o.id}
                  className={cn(
                    "text-lg",
                    ready ? "bg-emerald-700" : "bg-zinc-900"
                  )}
                >
                  <td className="rounded-l-lg px-3 py-3 font-bold">{o.no}</td>
                  <td>
                    {o.table ? `Table ${o.table}` : (o.pickup ?? "Delivery")}
                  </td>
                  {stations.map((s) => {
                    const c = cell(o, s)
                    return (
                      <td key={s} className="text-center text-base">
                        {c ? (
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 font-semibold",
                              c.done === c.total
                                ? "text-emerald-300"
                                : c.cooking
                                  ? "text-amber-300"
                                  : "text-zinc-300"
                            )}
                          >
                            {c.done === c.total ? (
                              <Check className="size-4" />
                            ) : c.cooking ? (
                              <ChefHat className="size-4" />
                            ) : (
                              <Clock3 className="size-4" />
                            )}
                            <span className="tabular">
                              {c.done}/{c.total}
                            </span>
                          </span>
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>
                    )
                  })}
                  <td className="tabular text-right">
                    {minLabel(at - o.createdAt)}
                  </td>
                  <td className="rounded-r-lg px-3 text-right">
                    <button
                      disabled={!o.lines.some((l) => l.status === "Ready")}
                      onClick={() => {
                        rms.serveAll(o.id)
                        toast.success(`${o.no} handed over`)
                      }}
                      className="touch-target rounded-lg bg-zinc-100 px-4 text-base font-bold text-zinc-950 disabled:opacity-30"
                    >
                      {o.type === "DINE_IN" ? "Served" : "Collected"}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="p-20 text-center text-2xl font-semibold text-zinc-500">
            No orders in progress.
          </p>
        )}
      </main>
    </div>
  )
}
