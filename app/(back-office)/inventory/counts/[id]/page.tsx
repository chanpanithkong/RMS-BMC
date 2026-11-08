"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { Check } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { confirmAction, requestApproval } from "@/components/rms/dialog-host"
import {
  Notice,
  Page,
  PageHeader,
  Panel,
  SimpleSelect,
  opts,
} from "@/components/rms/kit"
import { round2, usd } from "@/lib/rms/billing"
import { ingredients } from "@/lib/rms/back-office"

export default function CountSheetPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const items = ingredients.filter((i) => i.location === "Chiller")
  const [counts, setCounts] = React.useState<Record<string, string>>({})
  const [units, setUnits] = React.useState<Record<string, string>>({})
  const [submitted, setSubmitted] = React.useState(false)
  const done = items.filter(
    (i) => counts[i.id] !== undefined && counts[i.id] !== ""
  ).length
  const qtyOf = (i: (typeof items)[number]) => {
    const n = Number(counts[i.id] || 0)
    return (units[i.id] ?? i.unit) === "g" ? n / 1000 : n
  }
  const variance = items.map((i) => ({
    i,
    diff: round2(qtyOf(i) - i.onHand),
    value: round2((qtyOf(i) - i.onHand) * i.cost),
  }))
  const total = round2(variance.reduce((s, v) => s + v.value, 0))
  return (
    <Page>
      <PageHeader
        title={`Stock count ${id}`}
        description="Chiller, full count. System quantities stay hidden until you submit."
        actions={
          submitted ? (
            <Button
              onClick={() =>
                requestApproval({
                  action: `Post count ${id}`,
                  amount: usd(total),
                  onApproved: () => {
                    toast.success("Variance posted")
                    router.push("/inventory?tab=counts")
                  },
                })
              }
            >
              Send for approval
            </Button>
          ) : (
            <Button
              disabled={done < items.length}
              onClick={() =>
                confirmAction({
                  title: "Submit this count?",
                  effect:
                    "Counts lock and variances are shown. This can't be changed afterwards.",
                  confirmLabel: "Submit count",
                  onConfirm: () => setSubmitted(true),
                })
              }
            >
              Submit count
            </Button>
          )
        }
      />
      {!submitted && (
        <div className="flex items-center gap-3">
          <Progress
            value={(done / items.length) * 100}
            className="max-w-sm"
            aria-label="Count progress"
          />
          <span className="tabular text-sm">
            {done} of {items.length} counted
          </span>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Check className="size-3" />
            Draft saved automatically
          </span>
        </div>
      )}
      {submitted && (
        <Notice tone={total < 0 ? "warning" : "success"}>
          Total variance {usd(total)}. Approval is required before it is posted
          to stock.
        </Notice>
      )}
      <Panel title="Count sheet">
        <div className="overflow-x-auto">
          <table className="w-full min-w-xl text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="p-2 font-medium">Ingredient</th>
                <th className="p-2 font-medium">Counted</th>
                <th className="w-28 p-2 font-medium">Unit</th>
                {submitted && (
                  <>
                    <th className="p-2 text-right font-medium">System</th>
                    <th className="p-2 text-right font-medium">Variance</th>
                    <th className="p-2 text-right font-medium">Value</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {variance.map(({ i, diff, value }) => (
                <tr key={i.id} className="border-t">
                  <td className="p-2 font-medium">
                    {i.name}{" "}
                    <span className="font-normal text-muted-foreground">
                      {i.km}
                    </span>
                  </td>
                  <td className="p-2">
                    <Input
                      aria-label={`Counted ${i.name}`}
                      inputMode="decimal"
                      disabled={submitted}
                      className="h-11 w-32"
                      value={counts[i.id] ?? ""}
                      onChange={(e) =>
                        setCounts({ ...counts, [i.id]: e.target.value })
                      }
                    />
                  </td>
                  <td className="p-2">
                    <SimpleSelect
                      aria-label="Unit"
                      value={units[i.id] ?? i.unit}
                      onChange={(u) => setUnits({ ...units, [i.id]: u })}
                      options={opts(
                        ...(i.unit === "kg" ? ["kg", "g"] : [i.unit])
                      )}
                    />
                  </td>
                  {submitted && (
                    <>
                      <td className="tabular p-2 text-right">
                        {i.onHand} {i.unit}
                      </td>
                      <td
                        className={`tabular p-2 text-right ${diff < 0 ? "text-danger" : ""}`}
                      >
                        {diff > 0 && "+"}
                        {diff}
                      </td>
                      <td className="tabular p-2 text-right">{usd(value)}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </Page>
  )
}
