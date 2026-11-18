"use client"

import * as React from "react"
import {
  FileText,
  LogIn,
  LogOut,
  ShieldAlert,
  ShieldCheck,
  Wallet,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  FormRow,
  KV,
  Notice,
  Page,
  PageHeader,
  PageTabs,
  Panel,
  Stat,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import * as cash from "@/lib/api/cash"
import { report as showError } from "@/lib/api/pos"
import { can, useSession } from "@/lib/api/session"
import { khr, usd } from "@/lib/rms/billing"
import { useRms } from "@/lib/rms/store"
import type { CashierSession } from "@/lib/rms/types"

const usdDen = [100, 50, 20, 10, 5, 1]
const khrDen = [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 100]

function CountColumn({
  title,
  dens,
  values,
  onChange,
  format,
}: {
  title: string
  dens: number[]
  values: Record<number, string>
  onChange: (d: number, v: string) => void
  format: (n: number) => string
}) {
  const total = dens.reduce((s, d) => s + d * Number(values[d] || 0), 0)
  return (
    <div className="flex-1">
      <h3 className="mb-2 flex justify-between text-sm font-medium">
        {title}
        <span className="tabular font-semibold">{format(total)}</span>
      </h3>
      <ul className="grid gap-1.5">
        {dens.map((d) => (
          <li key={d} className="grid grid-cols-[1fr_96px] items-center gap-2">
            <label htmlFor={`d-${title}-${d}`} className="tabular text-sm">
              {format(d)}
            </label>
            <Input
              id={`d-${title}-${d}`}
              inputMode="numeric"
              className="tabular h-11 text-right"
              placeholder="0"
              value={values[d] ?? ""}
              onChange={(e) => onChange(d, e.target.value.replace(/\D/g, ""))}
            />
          </li>
        ))}
      </ul>
    </div>
  )
}

const money = (cur: string, v: string | number) => (cur === "KHR" ? khr(Number(v)) : usd(Number(v)))

/** X report while the session is open, Z report once closed, both calculated by the server (FR-STAFF-012). */
function Report({ s, onClose }: { s: CashierSession | null; onClose: () => void }) {
  const [data, setData] = React.useState<cash.SessionReport | null>(null)
  React.useEffect(() => {
    if (!s) return
    let live = true
    cash.sessionReport(s.id).then((r) => live && setData(r), showError)
    return () => {
      live = false
      setData(null)
    }
  }, [s])
  if (!s) return null
  const rows: [string, string][] = data
    ? [
        ["Opening float", Object.entries(data.floats).map(([c, v]) => money(c, v)).join(" · ")],
        ...data.payments.map(
          (p) => [`${p.method_currency.replace(":", " · ")} (${p.count})`, money(p.method_currency.split(":")[1], p.tendered)] as [string, string]
        ),
        ...data.refunds.map((r) => [`Refund ${r.refund_no}`, money(r.currency, r.amount)] as [string, string]),
        ...data.movements.map((m) => [`${m.kind}: ${m.reason}`, money(m.currency, m.amount)] as [string, string]),
        ...(data.kind === "X"
          ? ([["Expected cash", data.expected ? Object.entries(data.expected).map(([c, v]) => money(c, v)).join(" · ") : "Hidden until the count"]] as [string, string][])
          : (data.results ?? []).flatMap(
              (r) =>
                [
                  [`Expected ${r.currency}`, money(r.currency, r.expected)],
                  [`Counted ${r.currency}`, money(r.currency, r.counted)],
                  [`Variance ${r.currency}`, money(r.currency, r.variance)],
                ] as [string, string][]
            )),
      ]
    : []
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{data?.kind ?? (s.status === "Open" ? "X" : "Z")} report</DialogTitle>
          <DialogDescription>
            {s.cashier} · opened {s.opened}
            {s.closed && ` · closed ${s.closed}`}
          </DialogDescription>
        </DialogHeader>
        {data ? <KV className="tabular" items={rows} /> : <p className="text-sm text-muted-foreground">Loading…</p>}
        <Button
          onClick={() => {
            toast.success("Report sent to printer")
            onClose()
          }}
        >
          Print
        </Button>
      </DialogContent>
    </Dialog>
  )
}

export default function ShiftsPage() {
  const { sessions } = useRms()
  const { me } = useSession()
  const myId = me?.id ?? ""
  const viewAll = can(me, "cash.view")
  const canApprove = can(me, "cash.approve")
  const reload = React.useCallback(() => {
    if (myId) void cash.loadSessions(myId, viewAll).catch(showError)
  }, [myId, viewAll])
  React.useEffect(reload, [reload])
  const [busy, setBusy] = React.useState(false)
  /** Run an API call, show the server's message on failure, and reload sessions after. */
  const run = async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true)
    try {
      await fn()
      if (done) toast.success(done)
      return true
    } catch (e) {
      showError(e)
      return false
    } finally {
      setBusy(false)
      reload()
    }
  }
  const [tab, setTab] = useTab("session")
  const session = sessions.find((s) => s.status === "Open" && s.mine)
  const [cntU, setCntU] = React.useState<Record<number, string>>({})
  const [cntK, setCntK] = React.useState<Record<number, string>>({})
  const [closing, setClosing] = React.useState(false)
  const [result, setResult] = React.useState<CashierSession | null>(null)
  const [floatU, setFloatU] = React.useState("50")
  const [floatK, setFloatK] = React.useState("100000")
  const [move, setMove] = React.useState(false)
  const [report, setReport] = React.useState<CashierSession | null>(null)
  const countedU = usdDen.reduce((s, d) => s + d * Number(cntU[d] || 0), 0)
  const countedK = khrDen.reduce((s, d) => s + d * Number(cntK[d] || 0), 0)

  const denominations = (dens: number[], values: Record<number, string>) =>
    Object.fromEntries(dens.filter((d) => Number(values[d] || 0) > 0).map((d) => [String(d), Number(values[d])]))
  const submitCount = () => {
    if (!session) return
    void run(async () => {
      const closed = await cash.closeSession(
        session.id,
        { USD: countedU, KHR: countedK },
        { USD: denominations(usdDen, cntU), KHR: denominations(khrDen, cntK) },
        myId
      )
      setResult(closed)
      setClosing(false)
      setCntU({})
      setCntK({})
    })
  }
  return (
    <Page>
      <PageHeader
        title="Shifts & cashiers"
        description="Cashier sessions control cash from opening float to closing count."
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "session", label: "Current session" },
          { value: "movements", label: "Cash movements" },
          {
            value: "history",
            label: "Session history",
            count: sessions.length,
          },
        ]}
      />
      {tab === "session" &&
        (result ? (
          <Panel
            title={`Session ${result.id} counted`}
            description="Expected cash is revealed only after the count is submitted."
            className="max-w-2xl"
          >
            <table className="tabular w-full text-sm">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="p-1.5 text-left font-medium">Currency</th>
                  <th className="p-1.5 text-right font-medium">Expected</th>
                  <th className="p-1.5 text-right font-medium">Counted</th>
                  <th className="p-1.5 text-right font-medium">Variance</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t">
                  <td className="p-1.5">USD</td>
                  <td className="p-1.5 text-right">
                    {usd(result.countedUSD! - result.varianceUSD!)}
                  </td>
                  <td className="p-1.5 text-right">
                    {usd(result.countedUSD!)}
                  </td>
                  <td className="p-1.5 text-right font-semibold">
                    {usd(result.varianceUSD!)}
                  </td>
                </tr>
                <tr className="border-t">
                  <td className="p-1.5">KHR</td>
                  <td className="p-1.5 text-right">
                    {khr(result.countedKHR! - result.varianceKHR!)}
                  </td>
                  <td className="p-1.5 text-right">
                    {khr(result.countedKHR!)}
                  </td>
                  <td className="p-1.5 text-right font-semibold">
                    {khr(result.varianceKHR!)}
                  </td>
                </tr>
              </tbody>
            </table>
            <div className="mt-3">
              {result.status === "Pending Approval" ? (
                <Notice tone="danger">
                  Variance is beyond tolerance. A manager must approve it with a
                  reason (Session history, signed in as themselves) before the
                  session closes.
                </Notice>
              ) : (
                <Notice tone="success">
                  Variance is within tolerance. Session closed.
                </Notice>
              )}
            </div>
            <div className="mt-3 flex gap-2">
              <Button
                variant="outline"
                onClick={() => setReport(result)}
              >
                <FileText />Z report
              </Button>
              <Button variant="ghost" onClick={() => setResult(null)}>
                Done
              </Button>
            </div>
          </Panel>
        ) : closing && session ? (
          <Panel
            title={`Close session ${session.id}`}
            description="Count each denomination. The expected amount stays hidden until you submit."
            className="max-w-3xl"
          >
            <div className="flex flex-col gap-6 sm:flex-row">
              <CountColumn
                title="USD"
                dens={usdDen}
                values={cntU}
                format={usd}
                onChange={(d, v) => setCntU({ ...cntU, [d]: v })}
              />
              <CountColumn
                title="KHR"
                dens={khrDen}
                values={cntK}
                format={khr}
                onChange={(d, v) => setCntK({ ...cntK, [d]: v })}
              />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setClosing(false)}>
                Back
              </Button>
              <Button
                className="h-11"
                disabled={busy}
                onClick={() =>
                  confirmAction({
                    title: "Submit closing count?",
                    effect: `USD ${usd(countedU)} and KHR ${khr(countedK)}. The count can't be changed after you submit.`,
                    confirmLabel: "Submit count",
                    onConfirm: submitCount,
                  })
                }
              >
                Submit count
              </Button>
            </div>
          </Panel>
        ) : session ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Stat
                label="Session"
                value={session.cashier}
                icon={Wallet}
                hint="Your session"
              />
              <Stat
                label="Opened"
                value={session.opened.split(" ")[1]}
                hint={session.opened.split(" ")[0]}
              />
              <Stat
                label="Opening float"
                value={usd(session.floatUSD)}
                hint={khr(session.floatKHR)}
              />
              <Stat label="Cash movements" value={session.movements.length} />
            </section>
            <div className="flex flex-wrap gap-2">
              <Button className="h-11" onClick={() => setClosing(true)}>
                <LogOut />
                Close session
              </Button>
              <Button
                className="h-11"
                variant="outline"
                onClick={() => setMove(true)}
              >
                Paid-in / paid-out / drop
              </Button>
              <Button
                className="h-11"
                variant="outline"
                onClick={() => setReport(session)}
              >
                <FileText />X report
              </Button>
            </div>
          </>
        ) : (
          <Panel
            title="Open a cashier session"
            description="Cash payments, refunds and paid-outs need an open session."
            className="max-w-md"
          >
            <div className="grid gap-3">
              <FormRow label="Opening float USD" required htmlFor="fu">
                <Input
                  id="fu"
                  inputMode="decimal"
                  className="h-11"
                  value={floatU}
                  onChange={(e) => setFloatU(e.target.value)}
                />
              </FormRow>
              <FormRow label="Opening float KHR" required htmlFor="fk">
                <Input
                  id="fk"
                  inputMode="numeric"
                  className="h-11"
                  value={floatK}
                  onChange={(e) => setFloatK(e.target.value)}
                />
              </FormRow>
              <Button
                className="h-11"
                disabled={busy}
                onClick={() =>
                  void run(
                    () => cash.openSession({ USD: Number(floatU) || 0, KHR: Number(floatK) || 0 }),
                    "Session opened"
                  )
                }
              >
                <LogIn />
                Open session
              </Button>
            </div>
          </Panel>
        ))}
      {tab === "movements" && (
        <DataTable
          rows={sessions.flatMap((s) =>
            s.movements.map((m) => ({
              ...m,
              session: s.id,
              cashier: s.cashier,
            }))
          )}
          exportName="cash-movements"
          emptyTitle="No cash movements"
          toolbar={
            session && (
              <Button onClick={() => setMove(true)}>New movement</Button>
            )
          }
          columns={[
            { key: "time", header: "Time" },
            { key: "session", header: "Session" },
            { key: "cashier", header: "Cashier" },
            { key: "kind", header: "Type" },
            {
              key: "amount",
              header: "Amount",
              align: "right",
              render: (m) =>
                m.currency === "USD" ? usd(m.amount) : khr(m.amount),
            },
            { key: "reason", header: "Reason" },
            { key: "approvedBy", header: "Approved by", render: (m) => m.approvedBy ?? "—" },
          ]}
        />
      )}
      {tab === "history" && (
        <DataTable
          rows={sessions}
          exportName="cashier-sessions"
          filters={[
            {
              key: "status",
              label: "Status",
              options: ["Open", "Pending Approval", "Closed", "Force Closed"],
            },
          ]}
          columns={[
            { key: "cashier", header: "Cashier" },
            { key: "opened", header: "Opened" },
            { key: "closed", header: "Closed", render: (s) => s.closed ?? "—" },
            {
              key: "varianceUSD",
              header: "Variance USD",
              align: "right",
              value: (s) => s.varianceUSD ?? 0,
              render: (s) =>
                s.varianceUSD === undefined ? "—" : usd(s.varianceUSD),
            },
            {
              key: "varianceKHR",
              header: "Variance KHR",
              align: "right",
              value: (s) => s.varianceKHR ?? 0,
              render: (s) =>
                s.varianceKHR === undefined ? "—" : khr(s.varianceKHR),
            },
            {
              key: "status",
              header: "Status",
              render: (s) => <StatusBadge status={s.status} />,
            },
          ]}
          rowActions={(s) => [
            {
              label: s.status === "Open" ? "X report" : "Z report",
              icon: FileText,
              onClick: () => setReport(s),
            },
            {
              label: "Approve variance",
              icon: ShieldCheck,
              hidden: () => s.status !== "Pending Approval" || !canApprove || !!s.mine,
              onClick: () =>
                confirmAction({
                  title: `Approve ${s.cashier}'s variance?`,
                  effect: `USD ${usd(s.varianceUSD ?? 0)} · KHR ${khr(s.varianceKHR ?? 0)}. The reason is stored with the session.`,
                  requireReason: true,
                  confirmLabel: "Approve variance",
                  onConfirm: (reason) => void run(() => cash.approveVariance(s.id, reason), "Variance approved"),
                }),
            },
            {
              label: "Force close",
              icon: ShieldAlert,
              destructive: true,
              hidden: () => s.status !== "Open" || !canApprove,
              onClick: () =>
                confirmAction({
                  title: `Force-close ${s.cashier}'s session?`,
                  effect:
                    "The session closes without a count and is flagged for a later count.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Force close",
                  onConfirm: (reason) => void run(() => cash.forceClose(s.id, reason), "Session force-closed"),
                }),
            },
          ]}
        />
      )}
      <RecordDialog
        open={move}
        onOpenChange={setMove}
        title="Cash movement"
        description="Recorded in your open cashier session."
        fields={[
          {
            name: "kind",
            label: "Type",
            type: "select",
            options: ["Paid-out", "Paid-in", "Cash drop"],
            required: true,
          },
          {
            name: "amount",
            label: "Amount",
            type: "number",
            min: 0.01,
            required: true,
            half: true,
          },
          {
            name: "currency",
            label: "Currency",
            type: "select",
            options: ["USD", "KHR"],
            required: true,
            half: true,
          },
          { name: "reason", label: "Reason", required: true },
        ]}
        initial={{ currency: "USD" }}
        onSubmit={(v) =>
          void run(
            () =>
              cash.addMovement(session!.id, {
                kind: v.kind as "Paid-out",
                currency: v.currency as "USD",
                amount: Number(v.amount),
                reason: String(v.reason),
              }),
            "Cash movement recorded"
          )
        }
      />
      <Report s={report} onClose={() => setReport(null)} />
    </Page>
  )
}
