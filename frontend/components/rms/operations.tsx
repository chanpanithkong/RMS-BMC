"use client"

/**
 * Phase 4 back-office screens: payment reconciliation (FR-BILL-018), message delivery log (FR-NOTIF-013),
 * notification preferences (FR-NOTIF-011), recurring expenses (FR-EXP-008) and scheduled report emails (FR-RPT-027).
 * Every rule (matching, permissions, duplicates, mandatory notifications) is enforced by the server.
 */
import * as React from "react"
import { Link2, Lock, Plus, RotateCcw, Trash2, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { CrudTable, RecordDialog, type FieldValue } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { Notice, Panel, SimpleSelect, Stat, StatusBadge } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { can, useSession } from "@/lib/api/session"
import { act, num, save, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
const money = (v: string | number, cur: string) => (cur === "KHR" ? `៛${Math.round(num(v)).toLocaleString()}` : usd(num(v)))
const today = () => new Date().toLocaleDateString("en-CA")

// ---------------------------------------------------------------- reconciliation
interface RecPayment {
  payment_id: string
  order_no: string | null
  reference: string | null
  amount: string
  currency: string
  recorded_at: string
  status: string
  line_id: string | null
}
interface RecLine {
  id: string
  reference: string
  amount: string
  currency: string
  payment_id: string | null
  match_status: string
  matched_manually: boolean
  note: string | null
}
interface RecView {
  business_date: string
  method_code: string
  method_name: string
  status: string
  note: string | null
  closed_at: string | null
  payments: RecPayment[]
  lines: RecLine[]
  totals: { recorded: Record<string, string>; statement: Record<string, string> }
  counts: { matched: number; amount_mismatch: number; not_recorded: number; not_on_statement: number }
  balanced: boolean
}
const LABEL: Record<string, string> = {
  Matched: "Matched",
  AmountMismatch: "Amount differs",
  NotRecorded: "No payment recorded",
  NotOnStatement: "Not on statement",
  NotStarted: "Not started",
}
const TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  Matched: "success",
  AmountMismatch: "warning",
  NotRecorded: "danger",
  NotOnStatement: "danger",
  Closed: "success",
  Open: "warning",
  NotStarted: "neutral",
}

export function ReconciliationTab() {
  const methods = useApi(() => api<{ code: string; name: string }[]>("GET", "/payment-reconciliation/methods"), [], [])
  const days = useApi(() => api<{ business_date: string; method_code: string; payments: number; recorded_base: string; status: string }[]>("GET", "/payment-reconciliation/days"), [], [])
  const [day, setDay] = React.useState(today)
  const [method, setMethod] = React.useState("BANK_TRANSFER")
  const view = useApi(
    () => api<RecView>("GET", "/payment-reconciliation", { query: { business_date: day, method_code: method } }),
    [day, method],
    null
  )
  const [adding, setAdding] = React.useState(false)
  const [matching, setMatching] = React.useState<RecLine | null>(null)
  const fileRef = React.useRef<HTMLInputElement>(null)
  const v = view.data
  const open = v?.status !== "Closed"
  const reload = () => {
    view.reload()
    days.reload()
  }
  const importFile = async (f: File) => {
    const csv = await f.text()
    await act(
      () => api("POST", "/payment-reconciliation/import", { body: { business_date: day, method_code: method, csv } }),
      `Statement imported from ${f.name}`,
      reload
    )
  }
  const methodName = (c: string) => methods.data.find((m) => m.code === c)?.name ?? c
  return (
    <div className="space-y-4">
      <Panel title="Reconcile a day" description="Enter or import the bank or provider statement. Lines are matched to recorded payments by reference; payments themselves are never changed here.">
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid gap-1 text-sm">
            Business day
            <Input type="date" value={day} max={today()} onChange={(e) => setDay(e.target.value)} className="w-44" />
          </label>
          <label className="grid gap-1 text-sm">
            Method
            <SimpleSelect value={method} onChange={setMethod} options={methods.data.map((m) => ({ value: m.code, label: m.name }))} className="w-48" />
          </label>
          {open && (
            <>
              <Button variant="outline" onClick={() => setAdding(true)}>
                <Plus />
                Add statement line
              </Button>
              <Button variant="outline" onClick={() => fileRef.current?.click()}>
                <Upload />
                Import CSV
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  e.target.value = ""
                  if (f) void importFile(f)
                }}
              />
            </>
          )}
          {v && open && (v.lines.length > 0 || v.payments.length > 0) && (
            <Button
              className="ml-auto"
              onClick={() =>
                confirmAction({
                  title: `Lock ${methodName(method)} for ${day}?`,
                  effect: v.balanced
                    ? "Everything matches. The day becomes read-only."
                    : "There are differences. Explain them; the day becomes read-only with your note.",
                  confirmLabel: "Lock day",
                  requireReason: !v.balanced,
                  onConfirm: (note) =>
                    void act(() => api("POST", "/payment-reconciliation/close", { body: { business_date: day, method_code: method, note: note || null } }), "Day locked", reload),
                })
              }
            >
              <Lock />
              Lock day
            </Button>
          )}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">CSV columns: reference, amount, and optionally currency (USD or KHR) and received_at. A reference already entered is skipped.</p>
      </Panel>
      {v && (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <Stat label="Status" value={<StatusBadge status={LABEL[v.status] ?? v.status} tone={TONE[v.status]} />} hint={v.closed_at ? `Locked ${when(v.closed_at)}` : undefined} />
            <Stat label="Matched" value={v.counts.matched} />
            <Stat label="Amount differs" value={v.counts.amount_mismatch} tone={v.counts.amount_mismatch ? "warning" : undefined} />
            <Stat label="Unmatched" value={v.counts.not_recorded + v.counts.not_on_statement} tone={v.counts.not_recorded + v.counts.not_on_statement ? "danger" : undefined}
              hint={`${v.counts.not_on_statement} payment(s) not on statement · ${v.counts.not_recorded} line(s) with no payment`} />
          </div>
          {v.note && <Notice tone="info">Note: {v.note}</Notice>}
          <Panel title="Recorded payments" description={Object.entries(v.totals.recorded).map(([c, t]) => `${money(t, c)} recorded`).join(" · ") || "No payments recorded"}>
            <DataTable
              rows={v.payments.map((p) => ({ ...p, id: p.payment_id }))}
              exportName={`payments-${method}-${day}`}
              emptyTitle="No payments with this method on this day"
              columns={[
                { key: "order_no", header: "Order", value: (p) => p.order_no ?? "" },
                { key: "reference", header: "Reference", value: (p) => p.reference ?? "—" },
                { key: "amount", header: "Amount", align: "right", render: (p) => money(p.amount, p.currency) },
                { key: "recorded_at", header: "Recorded", value: (p) => when(p.recorded_at) },
                { key: "status", header: "Statement", value: (p) => LABEL[p.status] ?? p.status, render: (p) => <StatusBadge status={LABEL[p.status] ?? p.status} tone={TONE[p.status]} /> },
              ]}
            />
          </Panel>
          <Panel title="Statement lines" description={Object.entries(v.totals.statement).map(([c, t]) => `${money(t, c)} on statement`).join(" · ") || "Nothing entered yet"}>
            <DataTable
              rows={v.lines}
              exportName={`statement-${method}-${day}`}
              emptyTitle="No statement lines yet"
              columns={[
                { key: "reference", header: "Reference" },
                { key: "amount", header: "Amount", align: "right", render: (l) => money(l.amount, l.currency) },
                {
                  key: "match_status",
                  header: "Result",
                  value: (l) => LABEL[l.match_status] ?? l.match_status,
                  render: (l) => (
                    <span className="flex items-center gap-1.5">
                      <StatusBadge status={LABEL[l.match_status] ?? l.match_status} tone={TONE[l.match_status]} />
                      {l.matched_manually && <span className="text-xs text-muted-foreground">by hand</span>}
                    </span>
                  ),
                },
                { key: "note", header: "Note", value: (l) => l.note ?? "" },
              ]}
              rowActions={(l) =>
                open
                  ? [
                      { label: "Match to a payment", icon: Link2, onClick: () => setMatching(l) },
                      {
                        label: "Remove line",
                        icon: Trash2,
                        destructive: true,
                        onClick: () =>
                          confirmAction({
                            title: `Remove ${l.reference}?`,
                            effect: "Removes this statement entry only (it was typed or imported here). The removal is audited.",
                            destructive: true,
                            requireReason: true,
                            confirmLabel: "Remove",
                            onConfirm: (reason) => void act(() => api("POST", `/payment-reconciliation/lines/${l.id}/remove`, { body: { reason } }), "Line removed", reload),
                          }),
                      },
                    ]
                  : []
              }
            />
          </Panel>
        </>
      )}
      <Panel title="Recent days" description="Electronic payments in the last 30 days and whether each day is reconciled.">
        <DataTable
          rows={days.data.map((d) => ({ ...d, id: `${d.business_date}-${d.method_code}` }))}
          exportName="reconciliation-days"
          emptyTitle="No electronic payments yet"
          onRowClick={(d) => {
            setDay(d.business_date)
            setMethod(d.method_code)
          }}
          columns={[
            { key: "business_date", header: "Day" },
            { key: "method_code", header: "Method", value: (d) => methodName(d.method_code) },
            { key: "payments", header: "Payments", align: "right" },
            { key: "recorded_base", header: "Recorded (USD)", align: "right", render: (d) => usd(num(d.recorded_base)) },
            { key: "status", header: "Status", value: (d) => LABEL[d.status] ?? d.status, render: (d) => <StatusBadge status={LABEL[d.status] ?? d.status} tone={TONE[d.status]} /> },
          ]}
        />
      </Panel>
      <RecordDialog
        open={adding}
        onOpenChange={setAdding}
        title="Add statement line"
        description={`${methodName(method)}, ${day}`}
        fields={[
          { name: "reference", label: "Reference on the statement", required: true },
          { name: "amount", label: "Amount", type: "number", min: 0.01, required: true, half: true },
          { name: "currency", label: "Currency", type: "select", options: ["USD", "KHR"], required: true, half: true },
        ]}
        initial={{ currency: "USD" }}
        onSubmit={(f) =>
          save(() =>
            api("POST", "/payment-reconciliation/lines", {
              body: { business_date: day, method_code: method, lines: [{ reference: String(f.reference), amount: String(f.amount), currency: String(f.currency) }] },
            })
          ).then(reload)
        }
      />
      <RecordDialog
        open={!!matching}
        onOpenChange={(o) => !o && setMatching(null)}
        title={`Match ${matching?.reference ?? ""}`}
        description="Choose the recorded payment this statement line belongs to, e.g. when the bank shortened the reference."
        fields={[
          {
            name: "payment",
            label: "Payment",
            type: "select",
            required: true,
            options: ["(none: unlink)", ...(v?.payments.map((p) => `${p.order_no ?? "?"} · ${p.reference ?? "no ref"} · ${money(p.amount, p.currency)}`) ?? [])],
          },
          { name: "note", label: "Note", required: true },
        ]}
        onSubmit={(f: Record<string, FieldValue>) => {
          const labels = v?.payments.map((p) => `${p.order_no ?? "?"} · ${p.reference ?? "no ref"} · ${money(p.amount, p.currency)}`) ?? []
          const i = labels.indexOf(String(f.payment))
          return save(() =>
            api("POST", `/payment-reconciliation/lines/${matching!.id}/match`, { body: { payment_id: i >= 0 ? v!.payments[i].payment_id : null, note: String(f.note) } })
          ).then(reload)
        }}
      />
    </div>
  )
}

// ---------------------------------------------------------------- delivery log
interface LogRow {
  id: string
  channel: "SMS" | "Email"
  to: string
  purpose: string
  summary: string | null
  status: string
  attempts: number
  max_attempts: number
  last_error: string | null
  created_at: string
  sent_at: string | null
  next_attempt_at: string | null
}
export function MessageLogTab() {
  const { me } = useSession()
  const [from, setFrom] = React.useState(() => new Date(Date.now() - 7 * 86_400_000).toLocaleDateString("en-CA"))
  const [to, setTo] = React.useState(today)
  const rows = useApi(() => api<LogRow[]>("GET", "/message-log", { query: { date_from: from, date_to: to } }), [from, to], [])
  const retry = can(me, "messages.retry")
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-sm">
          From
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-44" />
        </label>
        <label className="grid gap-1 text-sm">
          To
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-44" />
        </label>
        <p className="text-xs text-muted-foreground">Failed messages are retried with growing waits; “Logged” means email isn’t set up yet, so it was recorded but not sent.</p>
      </div>
      <DataTable
        rows={rows.data}
        exportName="message-log"
        emptyTitle={rows.loading ? "Loading…" : "No messages in this period"}
        searchValue={(r) => `${r.to} ${r.purpose} ${r.summary ?? ""}`}
        filters={[
          { key: "channel", label: "Channel", options: ["SMS", "Email"] },
          { key: "status", label: "Status", options: ["Queued", "Retrying", "Sent", "Logged", "Failed"] },
        ]}
        columns={[
          { key: "created_at", header: "Queued", value: (r) => when(r.created_at) },
          { key: "channel", header: "Channel" },
          { key: "to", header: "To" },
          { key: "purpose", header: "Message", render: (r) => <span>{r.purpose}{r.summary && <span className="block max-w-xs truncate text-xs text-muted-foreground">{r.summary}</span>}</span> },
          {
            key: "status",
            header: "Status",
            render: (r) => (
              <StatusBadge status={r.status} tone={r.status === "Failed" ? "danger" : r.status === "Sent" ? "success" : r.status === "Retrying" ? "warning" : "neutral"} />
            ),
          },
          { key: "attempts", header: "Attempts", align: "right", value: (r) => `${r.attempts}/${r.max_attempts}` },
          { key: "last_error", header: "Last error", value: (r) => r.last_error ?? "" },
        ]}
        rowActions={(r) =>
          retry && r.status === "Failed"
            ? [{ label: "Retry", icon: RotateCcw, onClick: () => void act(() => api("POST", `/message-log/${r.channel}/${r.id}/retry`), "Queued again", rows.reload) }]
            : []
        }
      />
    </div>
  )
}

// ---------------------------------------------------------------- preferences
export function PreferencesTab() {
  const prefs = useApi(() => api<{ kind: string; label: string; mandatory: boolean; enabled: boolean }[]>("GET", "/me/notification-preferences"), [], [])
  return (
    <Panel title="Which notifications you receive" description="Safety and money notifications are always delivered. The others you can turn off for yourself." className="max-w-xl">
      <ul className="divide-y">
        {prefs.data.map((p) => (
          <li key={p.kind} className="flex items-center justify-between gap-3 py-2.5 text-sm">
            <span>
              {p.label}
              {p.mandatory && <span className="ml-2 text-xs text-muted-foreground">always on</span>}
            </span>
            <Switch
              aria-label={p.label}
              checked={p.enabled}
              disabled={p.mandatory}
              onCheckedChange={(c) =>
                void act(() => api("PUT", "/me/notification-preferences", { body: { preferences: { [p.kind]: Boolean(c) } } }), c ? `${p.label} on` : `${p.label} off`, prefs.reload)
              }
            />
          </li>
        ))}
      </ul>
    </Panel>
  )
}

// ---------------------------------------------------------------- recurring expenses
interface Template {
  id: string
  name: string
  category_id: string
  description: string
  payee: string
  amount: string
  currency: string
  frequency: "Weekly" | "Monthly"
  day_of_week: number | null
  day_of_month: number | null
  next_run_date: string
  is_active: boolean
}
export function RecurringExpensesTab({ categories, onGenerated }: { categories: { id: string; name: string }[]; onGenerated: () => void }) {
  const { me } = useSession()
  const manage = can(me, "expenses.create")
  const list = useApi(() => api<Template[]>("GET", "/expense-templates"), [], [])
  const catName = (id: string) => categories.find((c) => c.id === id)?.name ?? "?"
  const toBody = (v: Record<string, FieldValue>) => ({
    name: String(v.name),
    category_id: categories.find((c) => c.name === v.category)?.id,
    description: String(v.description),
    payee: String(v.payee),
    amount: String(v.amount),
    currency: String(v.currency || "USD"),
    frequency: String(v.frequency),
    day_of_week: v.frequency === "Weekly" ? DAYS.indexOf(String(v.weekday)) : null,
    day_of_month: v.frequency === "Monthly" ? Number(v.monthday) || 1 : null,
    start_date: v.start ? String(v.start) : null,
    is_active: v.active !== false,
  })
  return (
    <div className="space-y-3">
      {manage && (
        <div className="flex justify-end">
          <Button
            variant="outline"
            onClick={() =>
              void act(async () => {
                const r = await api<{ created: number }>("POST", "/expense-templates/generate")
                return r
              }, "Due drafts created", () => {
                list.reload()
                onGenerated()
              })
            }
          >
            Create due drafts now
          </Button>
        </div>
      )}
      <CrudTable
        noun="Recurring expense"
        rows={list.data.map((t) => ({
          ...t,
          schedule: t.frequency === "Weekly" ? `Every ${DAYS[t.day_of_week ?? 0]}` : `Monthly on day ${t.day_of_month}`,
          status: t.is_active ? "Active" : "Paused",
        }))}
        canAdd={manage}
        canEdit={manage}
        description="Each due date creates one Draft expense (never twice). Someone still checks, submits and gets it approved as usual."
        onSave={(v, e) => save(() => (e ? api("PUT", `/expense-templates/${e.id}`, { body: toBody(v) }) : api("POST", "/expense-templates", { body: toBody(v) }))).then(list.reload)}
        columns={[
          { key: "name", header: "Name", render: (t) => <span className="font-medium">{t.name}</span> },
          { key: "category_id", header: "Category", value: (t) => catName(t.category_id) },
          { key: "payee", header: "Payee" },
          { key: "amount", header: "Amount", align: "right", render: (t) => money(t.amount, t.currency) },
          { key: "schedule", header: "Schedule" },
          { key: "next_run_date", header: "Next draft" },
          { key: "status", header: "Status", render: (t) => <StatusBadge status={t.status} /> },
        ]}
        fields={[
          { name: "name", label: "Name", required: true, half: true },
          { name: "category", label: "Category", type: "select", options: categories.map((c) => c.name), required: true, half: true },
          { name: "description", label: "Description on the expense", required: true },
          { name: "payee", label: "Payee", required: true, half: true },
          { name: "amount", label: "Amount", type: "number", min: 0.01, required: true, half: true },
          { name: "currency", label: "Currency", type: "select", options: ["USD", "KHR"], half: true },
          { name: "frequency", label: "Repeats", type: "select", options: ["Weekly", "Monthly"], required: true, half: true },
          { name: "weekday", label: "Day of the week (weekly)", type: "select", options: DAYS, half: true, validate: (x, a) => (a.frequency === "Weekly" && !x ? "Choose a day" : undefined) },
          { name: "monthday", label: "Day of the month (monthly)", type: "number", min: 1, max: 31, half: true, hint: "Short months use their last day",
            validate: (x, a) => (a.frequency === "Monthly" && !x ? "Choose a day" : undefined) },
          { name: "start", label: "Starting from", type: "date", half: true },
          { name: "active", label: "Active", type: "switch", half: true },
        ]}
        toForm={(t) => ({
          name: t.name,
          category: catName(t.category_id),
          description: t.description,
          payee: t.payee,
          amount: String(num(t.amount)),
          currency: t.currency,
          frequency: t.frequency,
          weekday: t.day_of_week === null ? "" : DAYS[t.day_of_week],
          monthday: t.day_of_month === null ? "" : String(t.day_of_month),
          start: t.next_run_date,
          active: t.is_active,
        })}
      />
    </div>
  )
}

// ---------------------------------------------------------------- scheduled reports
interface Schedule {
  id: string
  report_id: string
  report_name: string
  name: string
  frequency: "Daily" | "Weekly" | "Monthly"
  day_of_week: number | null
  day_of_month: number | null
  hour: number
  next_run_at: string
  last_run_at: string | null
  is_active: boolean
  recipients: { id: string; name: string }[]
}
export function ScheduledReportsTab({ reports }: { reports: { id: string; name: string }[] }) {
  const { me } = useSession()
  const manage = can(me, "report.export")
  const list = useApi(() => api<Schedule[]>("GET", "/report-schedules"), [], [])
  const users = useApi(
    () => (can(me, "users.view") ? api<{ data: { id: string; full_name: string; username: string }[] }>("GET", "/users", { query: { page_size: 200 } }).then((r) => r.data) : Promise.resolve([])),
    [],
    []
  )
  const people = me ? [{ id: me.id, full_name: me.full_name, username: me.username }, ...users.data.filter((u) => u.id !== me.id)] : users.data
  const toBody = (v: Record<string, FieldValue>) => ({
    report_id: reports.find((r) => r.name === v.report)?.id,
    name: String(v.name),
    frequency: String(v.frequency),
    day_of_week: v.frequency === "Weekly" ? DAYS.indexOf(String(v.weekday)) : null,
    day_of_month: v.frequency === "Monthly" ? Number(v.monthday) || 1 : null,
    hour: Number(v.hour ?? 7),
    recipient_ids: String(v.recipients ?? "")
      .split(",")
      .map((s) => people.find((p) => p.username.toLowerCase() === s.trim().toLowerCase() || p.full_name.toLowerCase() === s.trim().toLowerCase())?.id)
      .filter((x): x is string => !!x),
    is_active: v.active !== false,
  })
  return (
    <CrudTable
      noun="Scheduled report"
      rows={list.data.map((s) => ({
        ...s,
        when: `${s.frequency === "Daily" ? "Every day" : s.frequency === "Weekly" ? `Every ${DAYS[s.day_of_week ?? 0]}` : `Monthly on day ${s.day_of_month}`} at ${String(s.hour).padStart(2, "0")}:00`,
        to: s.recipients.map((r) => r.name).join(", "),
        status: s.is_active ? "Active" : "Paused",
      }))}
      canAdd={manage}
      canEdit={manage}
      description="Each recipient gets an email with a sign-in link to their own copy, built with their own permissions. Daily = yesterday, weekly = the last 7 days, monthly = the previous month."
      onSave={(v, e) => save(() => (e ? api("PUT", `/report-schedules/${e.id}`, { body: toBody(v) }) : api("POST", "/report-schedules", { body: toBody(v) }))).then(list.reload)}
      columns={[
        { key: "name", header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
        { key: "report_name", header: "Report" },
        { key: "when", header: "When" },
        { key: "to", header: "Recipients" },
        { key: "next_run_at", header: "Next run", value: (s) => when(s.next_run_at) },
        { key: "status", header: "Status", render: (s) => <StatusBadge status={s.status} /> },
      ]}
      fields={[
        { name: "name", label: "Name", required: true, half: true },
        { name: "report", label: "Report", type: "select", options: reports.map((r) => r.name), required: true, half: true },
        { name: "frequency", label: "Repeats", type: "select", options: ["Daily", "Weekly", "Monthly"], required: true, half: true },
        { name: "hour", label: "Hour (branch time, 0–23)", type: "number", min: 0, max: 23, required: true, half: true },
        { name: "weekday", label: "Day of the week (weekly)", type: "select", options: DAYS, half: true, validate: (x, a) => (a.frequency === "Weekly" && !x ? "Choose a day" : undefined) },
        { name: "monthday", label: "Day of the month (monthly, 1–28)", type: "number", min: 1, max: 28, half: true,
          validate: (x, a) => (a.frequency === "Monthly" && !x ? "Choose a day" : undefined) },
        { name: "recipients", label: "Recipients (usernames, comma separated)", required: true, hint: people.slice(0, 6).map((p) => p.username).join(", ") },
        { name: "active", label: "Active", type: "switch" },
      ]}
      toForm={(s) => ({
        name: s.name,
        report: s.report_name,
        frequency: s.frequency,
        hour: String(s.hour),
        weekday: s.day_of_week === null ? "" : DAYS[s.day_of_week],
        monthday: s.day_of_month === null ? "" : String(s.day_of_month),
        recipients: s.recipients.map((r) => people.find((p) => p.id === r.id)?.username ?? r.name).join(", "),
        active: s.is_active,
      })}
    />
  )
}
