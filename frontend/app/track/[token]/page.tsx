"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import { Check } from "lucide-react"
import { KhqrPanel } from "@/components/rms/khqr-panel"
import { LinkButton } from "@/components/rms/kit"
import * as pub from "@/lib/api/public"
import { apiMessage } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"
import { cn } from "@/lib/utils"

type Tracking = Awaited<ReturnType<typeof pub.track>>

/** Public order tracking (FR-ONL-009). The link works until it expires; the page refreshes itself. */
export default function TrackOrderPage() {
  const { token } = useParams<{ token: string }>()
  const [data, setData] = React.useState<Tracking | null>(null)
  const [error, setError] = React.useState("")
  const paid = React.useCallback(() => setData((d) => (d ? { ...d, payment_status: "Paid" } : d)), [])
  React.useEffect(() => {
    let live = true
    const load = () =>
      pub.track(token).then(
        (d) => {
          if (!live) return
          setData(d)
          setError("")
        },
        (e) => live && setError(apiMessage(e))
      )
    void load()
    const t = setInterval(() => void load(), 15_000)
    return () => {
      live = false
      clearInterval(t)
    }
  }, [token])

  if (error && !data)
    return (
      <main className="flex min-h-svh flex-col items-center justify-center gap-3 p-6 text-center">
        <h1 className="text-lg font-semibold">This tracking link has expired or isn&apos;t valid</h1>
        <p className="text-sm text-muted-foreground">{error}</p>
        <LinkButton href="/online">Back to menu</LinkButton>
      </main>
    )
  if (!data) return <main className="p-6 text-center text-sm text-muted-foreground">Loading…</main>

  const delivery = data.fulfilment === "Delivery"
  const steps = ["Received", "Accepted", "Preparing", "Ready", ...(delivery ? ["Out for Delivery"] : []), "Completed"]
  const current = Math.max(0, steps.indexOf(data.status))
  const stopped = data.status === "Rejected" || data.status === "Cancelled"
  return (
    <main className="mx-auto min-h-svh max-w-md p-6">
      <h1 className="text-xl font-semibold">Order {data.order_no}</h1>
      <p className="text-sm text-muted-foreground">
        {data.branch.name_en} · total {usd(Number(data.totals.total))}
        {data.branch.phone && ` · ${data.branch.phone}`}
      </p>
      {!stopped && data.payment_status === "Pending" && <KhqrPanel token={token} onPaid={paid} />}
      {stopped ? (
        <p className="mt-6 rounded-lg bg-danger-soft p-3 text-sm text-danger">
          {data.status === "Rejected" ? "Sorry, the restaurant couldn't accept this order." : "This order was cancelled."}
          {data.reject_reason && ` ${data.reject_reason}.`} Any payment will be refunded.
        </p>
      ) : (
        <ol className="mt-6 grid gap-0">
          {steps.map((s, i) => (
            <li key={s} className="flex items-start gap-3 pb-6 last:pb-0">
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold",
                  i <= current ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground"
                )}
              >
                {i < current ? <Check className="size-4" /> : i + 1}
              </span>
              <span className={cn("pt-0.5", i === current ? "font-semibold" : i > current && "text-muted-foreground")}>
                {s === "Ready" && !delivery ? "Ready for pickup" : s}
                {i === current && <span className="block text-xs font-normal text-muted-foreground">Current status · updates by itself</span>}
              </span>
            </li>
          ))}
        </ol>
      )}
      <ul className="mt-6 divide-y rounded-lg border text-sm">
        {data.items.map((i, n) => (
          <li key={n} className="flex justify-between gap-2 p-2">
            <span>
              {Number(i.quantity)} × {i.name}
              {i.variant !== "Regular" && ` (${i.variant})`}
            </span>
            <span className="text-xs text-muted-foreground">{i.status === "Cancelled" ? "Cancelled" : ""}</span>
          </li>
        ))}
      </ul>
      <LinkButton href="/online" variant="outline" className="mt-8 w-full">
        Order something else
      </LinkButton>
    </main>
  )
}
