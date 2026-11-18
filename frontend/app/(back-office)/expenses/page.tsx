"use client"

import * as React from "react"
import { Check, CircleDollarSign, Paperclip, Send, Undo2, Upload, X } from "lucide-react"
import { toast } from "sonner"
import { CrudTable, RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { Page, PageHeader, PageTabs, Stat, StatusBadge, useTab } from "@/components/rms/kit"
import { api, download } from "@/lib/api/client"
import { RecurringExpensesTab } from "@/components/rms/operations"
import { can, useSession } from "@/lib/api/session"
import { act, apiMessage, num, save, useApi } from "@/lib/api/use-api"
import { khr, usd } from "@/lib/rms/billing"

interface Expense {
  id: string
  expense_no: string
  category_id: string
  expense_date: string
  description: string
  amount: string
  currency: "USD" | "KHR"
  amount_base: string
  payee: string
  status: string
  submitted_by: string | null
  approved_by: string | null
  decision_reason: string | null
  payment_method: string | null
  paid_at: string | null
  payment_ref: string | null
  attachments: { id: string; filename: string; content_type: string; size_bytes: number }[]
}
interface Category {
  id: string
  name_en: string
  name_km: string | null
  attachment_required: boolean
  is_active: boolean
}

const METHODS: Record<string, string> = { "Cash drawer": "CASH_DRAWER", "Bank transfer": "BANK_TRANSFER", KHQR: "KHQR", Card: "CARD", Other: "OTHER" }
const METHOD_LABEL = Object.fromEntries(Object.entries(METHODS).map(([k, v]) => [v, k]))
const monthStart = () => {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toLocaleDateString("en-CA")
}

export default function ExpensesPage() {
  const { me } = useSession()
  const [tab, setTab] = useTab("all")
  const list = useApi(async () => (await api<{ data: Expense[] }>("GET", "/expenses", { query: { page_size: 200 } })).data, [], [])
  const cats = useApi(() => api<Category[]>("GET", "/expense-categories"), [], [])
  const [from, setFrom] = React.useState(monthStart())
  const today = new Date().toLocaleDateString("en-CA")
  const summary = useApi(
    () =>
      api<{ period: string; category: string; payment_method: string | null; total_base: string; count: number }[]>("GET", "/expenses/summary", {
        query: { date_from: from, date_to: today, period: "month" },
      }),
    [from, tab === "summary"],
    []
  )
  const [pay, setPay] = React.useState<Expense | null>(null)
  const fileFor = React.useRef<Expense | null>(null)
  const fileInput = React.useRef<HTMLInputElement>(null)
  const catName = (id: string) => cats.data.find((c) => c.id === id)?.name_en ?? ""
  const reload = () => list.reload()

  const rows = list.data.map((e) => ({
    ...e,
    category: catName(e.category_id),
    amt: num(e.amount),
    base: num(e.amount_base),
    method: e.payment_method ? (METHOD_LABEL[e.payment_method] ?? e.payment_method) : "—",
    files: e.attachments.length,
  }))
  const pending = rows.filter((e) => e.status === "Submitted")
  const month = rows.filter((e) => e.expense_date >= monthStart() && ["Approved", "Paid"].includes(e.status))

  const upload = async (file: File) => {
    const e = fileFor.current
    if (!e) return
    const form = new FormData()
    form.append("file", file)
    try {
      await api("POST", `/expenses/${e.id}/attachments`, { body: form })
      toast.success(`${file.name} attached to ${e.expense_no}`)
      reload()
    } catch (err) {
      toast.error(apiMessage(err))
    }
  }

  const table = (data: typeof rows) => (
    <CrudTable
      noun="Expense"
      addLabel="Record expense"
      rows={data}
      canEdit={false}
      canAdd={tab === "all" && can(me, "expenses.create")}
      description="Saved as a draft. Submit it for approval when the receipt is attached."
      onSave={(v) =>
        save(() =>
          api("POST", "/expenses", {
            body: {
              category_id: cats.data.find((c) => c.name_en === v.category)!.id,
              expense_date: String(v.date),
              description: String(v.description),
              amount: String(v.amount),
              currency: v.currency || "USD",
              payee: String(v.payee),
            },
          })
        ).then(reload)
      }
      filters={[
        { key: "category", label: "Category", options: cats.data.map((c) => c.name_en) },
        { key: "status", label: "Status", options: ["Draft", "Submitted", "Approved", "Rejected", "Paid", "Reversed"] },
      ]}
      columns={[
        { key: "expense_no", header: "Expense" },
        { key: "expense_date", header: "Date" },
        { key: "category", header: "Category" },
        { key: "description", header: "Description" },
        { key: "payee", header: "Payee" },
        { key: "amt", header: "Amount", align: "right", render: (e) => (e.currency === "KHR" ? khr(e.amt) : usd(e.amt)) },
        { key: "method", header: "Paid by" },
        { key: "files", header: "Files", align: "right" },
        { key: "status", header: "Status", render: (e) => <StatusBadge status={e.status} /> },
      ]}
      fields={[
        { name: "date", label: "Date", type: "date", required: true, half: true },
        { name: "category", label: "Category", type: "select", options: cats.data.filter((c) => c.is_active).map((c) => c.name_en), required: true, half: true },
        { name: "description", label: "Description", required: true },
        { name: "payee", label: "Payee", required: true },
        { name: "amount", label: "Amount", type: "number", min: 0.01, required: true, half: true },
        { name: "currency", label: "Currency", type: "select", options: ["USD", "KHR"], required: true, half: true },
      ]}
      extraActions={(e) => [
        {
          label: "Attach receipt",
          icon: Upload,
          hidden: () => !["Draft", "Submitted"].includes(e.status) || !can(me, "expenses.create"),
          onClick: () => {
            fileFor.current = e
            fileInput.current?.click()
          },
        },
        ...e.attachments.map((a) => ({
          label: `Open ${a.filename}`,
          icon: Paperclip,
          onClick: () => void download(`/expenses/${e.id}/attachments/${a.id}`, a.filename).catch((err) => toast.error(apiMessage(err))),
        })),
        {
          label: "Submit for approval",
          icon: Send,
          hidden: () => e.status !== "Draft",
          onClick: () => void act(() => api("POST", `/expenses/${e.id}/submit`), `${e.expense_no} submitted`, reload),
        },
        {
          label: "Approve",
          icon: Check,
          hidden: () => e.status !== "Submitted" || !can(me, "expenses.approve"),
          onClick: () => void act(() => api("POST", `/expenses/${e.id}/decision`, { body: { approve: true } }), `${e.expense_no} approved`, reload),
        },
        {
          label: "Reject",
          icon: X,
          destructive: true,
          hidden: () => e.status !== "Submitted" || !can(me, "expenses.approve"),
          onClick: () =>
            confirmAction({
              title: `Reject ${e.expense_no}?`,
              effect: "The submitter sees the reason.",
              requireReason: true,
              destructive: true,
              confirmLabel: "Reject",
              onConfirm: (reason) => void act(() => api("POST", `/expenses/${e.id}/decision`, { body: { approve: false, reason } }), `${e.expense_no} rejected`, reload),
            }),
        },
        { label: "Record payment", icon: CircleDollarSign, hidden: () => e.status !== "Approved" || !can(me, "expenses.pay"), onClick: () => setPay(e) },
        {
          label: "Reverse",
          icon: Undo2,
          destructive: true,
          hidden: () => e.status !== "Paid" || !can(me, "expenses.approve"),
          onClick: () =>
            confirmAction({
              title: `Reverse ${e.expense_no}?`,
              effect: "The original stays on record and a reversing entry is added.",
              requireReason: true,
              destructive: true,
              confirmLabel: "Reverse",
              onConfirm: (reason) => void act(() => api("POST", `/expenses/${e.id}/reverse`, { body: { reason } }), `${e.expense_no} reversed`, reload),
            }),
        },
      ]}
    />
  )

  return (
    <Page>
      <PageHeader title="Expenses" description="Operating costs with receipts. Above your limit, someone else approves. Cash-drawer payments come out of your open cashier session." />
      <section className="grid gap-3 sm:grid-cols-3">
        <Stat label="Approved this month" value={usd(month.reduce((s, e) => s + e.base, 0))} hint={`${month.length} expenses`} />
        <Stat label="Waiting for approval" value={pending.length} tone={pending.length ? "warning" : undefined} />
        <Stat label="Approved, not paid" value={rows.filter((e) => e.status === "Approved").length} />
      </section>
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "all", label: "All expenses", count: rows.length },
          { value: "approvals", label: "Approvals", count: pending.length },
          { value: "summary", label: "Summary" },
          { value: "categories", label: "Categories" },
          { value: "recurring", label: "Recurring" },
        ]}
      />
      {tab === "all" && table(rows)}
      {tab === "approvals" && table(pending)}
      {tab === "summary" && (
        <>
          <label className="flex items-center gap-2 text-sm">
            From
            <input type="date" className="rounded-md border px-2 py-1" value={from} onChange={(e) => setFrom(e.target.value)} />
            to today
          </label>
          <DataTable
            rows={summary.data.map((r, i) => ({ ...r, id: String(i), method: r.payment_method ? (METHOD_LABEL[r.payment_method] ?? r.payment_method) : "Not paid yet", total: num(r.total_base) }))}
            exportName="expense-summary"
            emptyTitle="No approved expenses in this period"
            columns={[
              { key: "period", header: "Month" },
              { key: "category", header: "Category" },
              { key: "method", header: "Paid by" },
              { key: "count", header: "Count", align: "right" },
              { key: "total", header: "Total (USD)", align: "right", render: (r) => usd(r.total) },
            ]}
          />
        </>
      )}
      {tab === "categories" && (
        <CrudTable
          noun="Category"
          rows={cats.data.map((c) => ({ ...c, receipt: c.attachment_required ? "Required" : "Optional" }))}
          canEdit={false}
          canAdd={can(me, "settings.manage")}
          onSave={(v) =>
            save(() => api("POST", "/expense-categories", { body: { name_en: v.name, name_km: String(v.km ?? "") || undefined, attachment_required: Boolean(v.receipt) } })).then(
              cats.reload
            )
          }
          columns={[
            { key: "name_en", header: "Category" },
            { key: "name_km", header: "Khmer", render: (c) => c.name_km ?? "" },
            { key: "receipt", header: "Receipt" },
            { key: "is_active", header: "Status", value: (c) => (c.is_active ? "Active" : "Inactive"), render: (c) => <StatusBadge status={c.is_active ? "Active" : "Inactive"} /> },
          ]}
          fields={[
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", half: true },
            { name: "receipt", label: "A receipt must be attached", type: "switch" },
          ]}
        />
      )}
      {tab === "recurring" && <RecurringExpensesTab categories={cats.data.filter((c) => c.is_active).map((c) => ({ id: c.id, name: c.name_en }))} onGenerated={reload} />}
      <input
        ref={fileInput}
        type="file"
        accept="application/pdf,image/jpeg,image/png"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void upload(f)
          e.target.value = ""
        }}
      />
      <RecordDialog
        open={!!pay}
        onOpenChange={(o) => !o && setPay(null)}
        title={`Pay ${pay?.expense_no ?? ""}`}
        description={pay ? `${pay.payee}: ${pay.currency === "KHR" ? khr(num(pay.amount)) : usd(num(pay.amount))}` : undefined}
        fields={[
          { name: "method", label: "Paid by", type: "select", options: Object.keys(METHODS), required: true, half: true },
          { name: "ref", label: "Reference", half: true },
        ]}
        initial={{ method: "Bank transfer" }}
        onSubmit={(v) =>
          save(() => api("POST", `/expenses/${pay!.id}/pay`, { body: { method: METHODS[String(v.method)], reference: String(v.ref ?? "") || undefined } })).then(reload)
        }
      />
    </Page>
  )
}
