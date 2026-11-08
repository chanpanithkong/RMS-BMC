"use client"

import { MapPin, Phone } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/rms/kit"
import { calcBill, khr, paymentStatus, toKhr, usd } from "@/lib/rms/billing"
import { rms, useRms } from "@/lib/rms/store"

export default function RiderPage() {
  const { orders } = useRms()
  const jobs = orders.filter(
    (o) =>
      o.delivery && ["Assigned", "Out for Delivery"].includes(o.delivery.status)
  )
  return (
    <main className="mx-auto min-h-svh max-w-md bg-muted/30 p-4">
      <h1 className="text-xl font-semibold">My deliveries</h1>
      <p className="mb-4 text-sm text-muted-foreground">{jobs.length} active</p>
      {jobs.length === 0 && (
        <p className="rounded-xl border bg-card p-8 text-center text-muted-foreground">
          No deliveries assigned to you right now.
        </p>
      )}
      <ul className="grid gap-3">
        {jobs.map((o) => {
          const d = o.delivery!
          const t = calcBill(o)
          return (
            <li key={o.id} className="rounded-xl border bg-card p-4">
              <div className="flex items-center justify-between">
                <span className="text-lg font-semibold">{o.no}</span>
                <StatusBadge status={d.status} />
              </div>
              <p className="mt-2 flex items-start gap-2 text-sm">
                <MapPin className="mt-0.5 size-4 shrink-0" />
                {d.address}
              </p>
              <a
                href={`tel:${d.phone.replaceAll(" ", "")}`}
                className="mt-1 flex items-center gap-2 text-sm text-primary"
              >
                <Phone className="size-4" />
                {d.phone}
              </a>
              <p className="mt-2 text-sm">
                {paymentStatus(o) === "Paid" ? (
                  "Prepaid"
                ) : (
                  <>
                    Collect <b className="tabular">{usd(t.balance)}</b>{" "}
                    <span className="tabular text-muted-foreground">
                      {khr(toKhr(t.balance))}
                    </span>
                  </>
                )}
              </p>
              {d.status === "Assigned" ? (
                <Button
                  className="mt-3 h-12 w-full"
                  onClick={() => rms.setDelivery(o.id, "Out for Delivery")}
                >
                  Start delivery
                </Button>
              ) : (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Button
                    className="h-12"
                    onClick={() => {
                      rms.setDelivery(o.id, "Delivered")
                      rms.serveAll(o.id)
                      toast.success("Delivery confirmed")
                    }}
                  >
                    Delivered
                  </Button>
                  <Button
                    className="h-12"
                    variant="destructive"
                    onClick={() => rms.setDelivery(o.id, "Failed")}
                  >
                    Failed
                  </Button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </main>
  )
}
