"use client"

import { useParams } from "next/navigation"
import { Check } from "lucide-react"
import { LinkButton } from "@/components/rms/kit"
import { calcBill, kitchenStatus, usd } from "@/lib/rms/billing"
import { useRms } from "@/lib/rms/store"
import { cn } from "@/lib/utils"

export default function TrackOrderPage() {
  const { id } = useParams<{ id: string }>()
  const { orders } = useRms()
  const o = orders.find((x) => x.id === id)
  if (!o)
    return (
      <main className="flex min-h-svh flex-col items-center justify-center gap-3 p-6 text-center">
        <h1 className="text-lg font-semibold">
          This tracking link has expired
        </h1>
        <LinkButton href="/online">Back to menu</LinkButton>
      </main>
    )
  const steps = [
    "Received",
    "Accepted",
    "Preparing",
    "Ready",
    ...(o.type === "DELIVERY" ? ["Out for Delivery"] : []),
    "Completed",
  ]
  const k = kitchenStatus(o)
  const current =
    o.status === "Completed"
      ? steps.length - 1
      : o.delivery?.status === "Out for Delivery"
        ? steps.indexOf("Out for Delivery")
        : k === "Ready"
          ? 3
          : k === "In Progress"
            ? 2
            : o.onlineState === "Accepted"
              ? 1
              : 0
  return (
    <main className="mx-auto min-h-svh max-w-md p-6">
      <h1 className="text-xl font-semibold">Order {o.no}</h1>
      <p className="text-sm text-muted-foreground">
        Thanks, {o.pickup}. Total {usd(calcBill(o).total)}.
      </p>
      {o.onlineState === "Rejected" ? (
        <p className="mt-6 rounded-lg bg-danger-soft p-3 text-sm text-danger">
          Sorry, the restaurant couldn&apos;t accept this order. Any payment
          will be refunded.
        </p>
      ) : (
        <ol className="mt-6 grid gap-0">
          {steps.map((s, i) => (
            <li key={s} className="flex items-start gap-3 pb-6 last:pb-0">
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold",
                  i <= current
                    ? "border-primary bg-primary text-primary-foreground"
                    : "text-muted-foreground"
                )}
              >
                {i < current ? <Check className="size-4" /> : i + 1}
              </span>
              <span
                className={cn(
                  "pt-0.5",
                  i === current
                    ? "font-semibold"
                    : i > current && "text-muted-foreground"
                )}
              >
                {s}
                {i === current && (
                  <span className="block text-xs font-normal text-muted-foreground">
                    Current status
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
      <LinkButton href="/online" variant="outline" className="mt-8 w-full">
        Order something else
      </LinkButton>
    </main>
  )
}
