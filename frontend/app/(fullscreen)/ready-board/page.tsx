"use client"

import { useLiveSync } from "@/lib/api/pos"
import { kitchenStatus } from "@/lib/rms/billing"
import { useRms } from "@/lib/rms/store"
import type { Order } from "@/lib/rms/types"

function Column({
  title,
  orders,
  ready,
}: {
  title: string
  orders: Order[]
  ready?: boolean
}) {
  return (
    <section className={ready ? "bg-emerald-700 p-6" : "bg-zinc-900 p-6"}>
      <h2 className="mb-6 text-4xl font-bold">{title}</h2>
      <ul className="grid grid-cols-2 gap-4 xl:grid-cols-3">
        {orders.map((o) => (
          <li key={o.id} className="rounded-2xl bg-black/25 p-5 text-center">
            <p className="tabular text-6xl font-bold">
              {o.no.replace("#", "")}
            </p>
            <p className="mt-1 text-2xl opacity-80">
              {(o.pickup ?? "").slice(0, 1)}.
            </p>
          </li>
        ))}
      </ul>
      {orders.length === 0 && (
        <p className="text-2xl opacity-60">No orders right now</p>
      )}
    </section>
  )
}

export default function ReadyBoardPage() {
  const { orders } = useRms()
  // Open orders from the server, updated live as the kitchen marks items ready.
  useLiveSync()
  const takeaway = orders.filter(
    (o) =>
      o.type === "TAKEAWAY" &&
      o.status === "Open" &&
      kitchenStatus(o) !== "Not Sent" &&
      kitchenStatus(o) !== "Served"
  )
  return (
    <main className="grid min-h-svh grid-cols-2 text-white">
      <h1 className="sr-only">Takeaway order status</h1>
      <Column
        title="Preparing"
        orders={takeaway.filter((o) => kitchenStatus(o) === "In Progress")}
      />
      <Column
        title="Ready for pickup"
        orders={takeaway.filter((o) => kitchenStatus(o) === "Ready")}
        ready
      />
    </main>
  )
}
