"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { Check } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { confirmAction } from "@/components/rms/dialog-host"
import { LinkButton, Notice, Page, PageHeader, Panel, SimpleSelect, StatusBadge } from "@/components/rms/kit"
import * as inv from "@/lib/api/inventory"
import { can, useSession } from "@/lib/api/session"
import { apiMessage, num, useApi } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

async function loadSheet(id: string) {
  const [sheet, units, locations] = await Promise.all([inv.getCount(id), inv.units(), inv.locations()])
  return { sheet, units, locations }
}

export default function CountSheetPage() {
  const { id } = useParams<{ id: string }>()
  const { data, loading, reload } = useApi(() => loadSheet(id), [id], null)
  if (loading || !data) return <Page><PageHeader title="Stock count" description="Loading…" /></Page>
  return <Sheet key={data.sheet.status} data={data} reload={reload} />
}

function Sheet({ data, reload }: { data: Awaited<ReturnType<typeof loadSheet>>; reload: () => void }) {
  const router = useRouter()
  const { me } = useSession()
  const { sheet, units, locations } = data
  const draft = sheet.status === "Draft"
  const unitByCode = Object.fromEntries(units.map((u) => [u.code, u]))
  const sameDim = (code: string) => units.filter((u) => u.dimension === unitByCode[code]?.dimension).map((u) => u.code)
  const [counts, setCounts] = React.useState<Record<string, string>>(
    Object.fromEntries(sheet.lines.map((l) => [l.ingredient_id, l.counted_qty === null ? "" : String(num(l.counted_qty))]))
  )
  const [unitOf, setUnitOf] = React.useState<Record<string, string>>({})
  const [saving, setSaving] = React.useState<"" | "saving" | "saved">("")
  const [busy, setBusy] = React.useState(false)
  const done = sheet.lines.filter((l) => counts[l.ingredient_id] !== "").length
  const total = sheet.lines.reduce((s, l) => s + num(l.variance_value), 0)

  /** Each entry is saved to the server when the field loses focus, so a count can be continued later. */
  const saveLine = async (ingredientId: string, stockUnit: string) => {
    const v = counts[ingredientId]
    if (v === "" || !(Number(v) >= 0)) return
    setSaving("saving")
    try {
      await inv.enterCounts(sheet.id, [{ ingredient_id: ingredientId, quantity: v, uom_id: unitByCode[unitOf[ingredientId] ?? stockUnit].id }])
      setSaving("saved")
    } catch (e) {
      setSaving("")
      toast.error(apiMessage(e))
    }
  }
  const run = async (fn: () => Promise<unknown>, done: string, after?: () => void) => {
    setBusy(true)
    try {
      await fn()
      toast.success(done)
      if (after) after()
      else reload()
    } catch (e) {
      toast.error(apiMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const location = locations.find((l) => l.id === sheet.location_id)?.name ?? ""
  const state = sheet.status === "Submitted" ? "Pending Approval" : sheet.status === "Draft" ? "Counting" : sheet.status

  return (
    <Page>
      <PageHeader
        title={`Stock count ${sheet.count_no}`}
        description={`${location}. ${draft ? "System quantities stay hidden until you submit." : "Counted against the system quantity at submission."}`}
        actions={
          <>
            <StatusBadge status={state} />
            <LinkButton href="/inventory?tab=counts" variant="outline">
              Back
            </LinkButton>
            {draft && (
              <Button
                disabled={done < sheet.lines.length || busy}
                onClick={() =>
                  confirmAction({
                    title: "Submit this count?",
                    effect: "Counts lock and variances are shown. A manager then approves posting them to stock.",
                    confirmLabel: "Submit count",
                    onConfirm: () => void run(() => inv.submitCount(sheet.id), "Count submitted"),
                  })
                }
              >
                Submit count
              </Button>
            )}
            {sheet.status === "Submitted" && can(me, "inventory.approve") && (
              <>
                <Button variant="outline" disabled={busy} onClick={() => void run(() => inv.decideCount(sheet.id, false), "Count rejected")}>
                  Reject
                </Button>
                <Button
                  disabled={busy}
                  onClick={() =>
                    confirmAction({
                      title: "Post the variance to stock?",
                      effect: `${usd(total)} of count adjustments will be posted. Someone other than the counter must approve.`,
                      confirmLabel: "Approve and post",
                      onConfirm: () => void run(() => inv.decideCount(sheet.id, true), "Variance posted", () => router.push("/inventory?tab=counts")),
                    })
                  }
                >
                  Approve and post
                </Button>
              </>
            )}
          </>
        }
      />
      {draft ? (
        <div className="flex items-center gap-3">
          <Progress value={sheet.lines.length ? (done / sheet.lines.length) * 100 : 0} className="max-w-sm" aria-label="Count progress" />
          <span className="tabular text-sm">
            {done} of {sheet.lines.length} counted
          </span>
          {saving && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Check className="size-3" />
              {saving === "saving" ? "Saving…" : "Draft saved"}
            </span>
          )}
        </div>
      ) : (
        <Notice tone={total < 0 ? "warning" : "success"}>
          Total variance {usd(total)}.{" "}
          {sheet.status === "Submitted" ? "Approval is required before it is posted to stock." : `This count is ${sheet.status.toLowerCase()}.`}
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
                {!draft && (
                  <>
                    <th className="p-2 text-right font-medium">System</th>
                    <th className="p-2 text-right font-medium">Variance</th>
                    <th className="p-2 text-right font-medium">Value</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {sheet.lines.map((l) => {
                const diff = num(l.variance)
                return (
                  <tr key={l.ingredient_id} className="border-t">
                    <td className="p-2 font-medium">{l.ingredient}</td>
                    <td className="p-2">
                      <Input
                        aria-label={`Counted ${l.ingredient}`}
                        inputMode="decimal"
                        disabled={!draft}
                        className="h-11 w-32"
                        value={counts[l.ingredient_id] ?? ""}
                        onChange={(e) => setCounts({ ...counts, [l.ingredient_id]: e.target.value })}
                        onBlur={() => void saveLine(l.ingredient_id, l.unit)}
                      />
                    </td>
                    <td className="p-2">
                      {draft ? (
                        <SimpleSelect
                          aria-label="Unit"
                          value={unitOf[l.ingredient_id] ?? l.unit}
                          onChange={(u) => setUnitOf({ ...unitOf, [l.ingredient_id]: u })}
                          options={sameDim(l.unit).map((u) => ({ value: u, label: u }))}
                        />
                      ) : (
                        l.unit
                      )}
                    </td>
                    {!draft && (
                      <>
                        <td className="tabular p-2 text-right">{inv.qty(l.system_qty, l.unit)}</td>
                        <td className={`tabular p-2 text-right ${diff < 0 ? "text-danger" : ""}`}>
                          {diff > 0 && "+"}
                          {inv.qty(diff)}
                        </td>
                        <td className="tabular p-2 text-right">{usd(num(l.variance_value))}</td>
                      </>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </Page>
  )
}
