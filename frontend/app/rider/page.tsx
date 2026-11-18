"use client"

import * as React from "react"
import { LogOut, MapPin, Phone } from "lucide-react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { confirmAction } from "@/components/rms/dialog-host"
import { StatusBadge } from "@/components/rms/kit"
import { api, connectRealtime } from "@/lib/api/client"
import { signOut, useSession } from "@/lib/api/session"
import { act, num, useApi } from "@/lib/api/use-api"
import { khr, toKhr, usd } from "@/lib/rms/billing"

interface Job {
  id: string
  order_no: string
  address: string
  landmark: string | null
  phone: string | null
  status: string
  customer_name: string | null
  amount_due: string
  kitchen_status: string
}

const LABEL: Record<string, string> = { OutForDelivery: "Out for Delivery", InPreparation: "In Preparation", PartiallyReady: "Partly ready", NotSent: "Not sent" }

export default function RiderPage() {
  const router = useRouter()
  const { me } = useSession()
  const jobs = useApi(() => api<Job[]>("GET", "/deliveries/mine"), [], [])
  // New assignments and kitchen progress arrive on the branch topic.
  const branchId = me?.current_branch.id
  const reload = jobs.reload
  React.useEffect(() => {
    if (!branchId) return
    return connectRealtime([`branch:${branchId}`], (ev) => {
      if (ev.type.startsWith("delivery.") || ev.type.startsWith("order.")) reload()
    })
  }, [branchId, reload])
  const active = jobs.data.filter((d) => ["Assigned", "OutForDelivery"].includes(d.status))
  const run = (fn: () => Promise<unknown>, done: string) => void act(fn, done, jobs.reload)

  return (
    <main className="mx-auto min-h-svh max-w-md bg-muted/30 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">My deliveries</h1>
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            void signOut().then(() => router.replace("/login?next=/rider"))
          }
        >
          <LogOut />
          Sign out
        </Button>
      </div>
      <p className="mb-4 text-sm text-muted-foreground">
        {me?.full_name} · {active.length} active
      </p>
      {active.length === 0 && (
        <p className="rounded-xl border bg-card p-8 text-center text-muted-foreground">{jobs.loading ? "Loading…" : "No deliveries assigned to you right now."}</p>
      )}
      <ul className="grid gap-3">
        {active.map((d) => {
          const due = num(d.amount_due)
          return (
            <li key={d.id} className="rounded-xl border bg-card p-4">
              <div className="flex items-center justify-between">
                <span className="text-lg font-semibold">{d.order_no}</span>
                <StatusBadge status={LABEL[d.status] ?? d.status} />
              </div>
              {d.customer_name && <p className="mt-1 text-sm font-medium">{d.customer_name}</p>}
              <p className="mt-2 flex items-start gap-2 text-sm">
                <MapPin className="mt-0.5 size-4 shrink-0" />
                <span>
                  {d.address}
                  {d.landmark && <span className="block text-muted-foreground">{d.landmark}</span>}
                </span>
              </p>
              {d.phone && (
                <a href={`tel:${d.phone.replaceAll(" ", "")}`} className="mt-1 flex items-center gap-2 text-sm text-primary">
                  <Phone className="size-4" />
                  {d.phone}
                </a>
              )}
              <p className="mt-2 text-sm">
                {due <= 0 ? (
                  "Prepaid"
                ) : (
                  <>
                    Collect <b className="tabular">{usd(due)}</b> <span className="tabular text-muted-foreground">{khr(toKhr(due))}</span>
                  </>
                )}
              </p>
              {d.status === "Assigned" ? (
                <>
                  {d.kitchen_status !== "Ready" && <p className="mt-2 text-xs text-warning">Kitchen: {LABEL[d.kitchen_status] ?? d.kitchen_status}. You can leave once everything is ready.</p>}
                  <Button className="mt-3 h-12 w-full" onClick={() => run(() => api("POST", `/deliveries/${d.id}/out`), "On your way")}>
                    Start delivery
                  </Button>
                </>
              ) : (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Button className="h-12" onClick={() => run(() => api("POST", `/deliveries/${d.id}/delivered`, { body: {} }), "Delivery confirmed")}>
                    Delivered
                  </Button>
                  <Button
                    className="h-12"
                    variant="destructive"
                    onClick={() =>
                      confirmAction({
                        title: "Delivery failed?",
                        effect: "The branch is told and decides whether to send it again.",
                        reasons: ["Customer not reachable", "Wrong address", "Customer refused", "Accident or breakdown"],
                        destructive: true,
                        confirmLabel: "Report failure",
                        onConfirm: (reason) => run(() => api("POST", `/deliveries/${d.id}/failed`, { body: { reason } }), "Failure reported"),
                      })
                    }
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
