"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import { FileSpreadsheet, Hourglass, Printer } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { DataTable, type Column } from "@/components/rms/data-table"
import { EmptyState, KV, LinkButton, Notice, Page, PageHeader, Panel } from "@/components/rms/kit"
import { api, ApiError, download } from "@/lib/api/client"
import { can, useSession } from "@/lib/api/session"
import { apiMessage, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"
import { reports as described } from "@/lib/rms/reports"

type Value = string | number | boolean | null | Record<string, unknown> | unknown[]
interface Report {
  id: string
  name: string
  from: string
  to: string
  branch: string
  generated_at: string
  generated_by: string
  summary: Record<string, Value>
  rows: Record<string, Value>[]
  note?: string | null
}

const MONEY = /(sales|amount|total|cost|value|discount|refund|charge|tax|fee|price|expense|revenue|margin|paid|balance|base|commission|spend|net|gross|variance_value|result)/i
const PCT = /(pct|percent|_rate$|share)/i
const label = (k: string) => k.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase())
/** Format a value by its key name: money in USD, percentages, counts and text. */
function fmt(key: string, v: Value): string {
  if (v === null || v === undefined || v === "") return "—"
  if (typeof v === "boolean") return v ? "Yes" : "No"
  if (typeof v === "object") return JSON.stringify(v)
  const n = typeof v === "number" ? v : Number(v)
  if (!Number.isNaN(n) && /^-?\d+(\.\d+)?$/.test(String(v))) {
    if (PCT.test(key)) return `${Number(n.toFixed(2))}%`
    if (MONEY.test(key) && !/count|qty|quantity|orders|tickets|items|minutes|hours/i.test(key)) return usd(n)
    return Number.isInteger(n) ? n.toLocaleString() : Number(n.toFixed(3)).toLocaleString()
  }
  return String(v)
}

function Table({ rows, name }: { rows: Record<string, Value>[]; name: string }) {
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))].filter((k) => !k.endsWith("_id") && k !== "id")
  const data = rows.map((r, i) => ({ ...r, id: String(i) })) as (Record<string, Value> & { id: string })[]
  const columns: Column<(typeof data)[number]>[] = keys.map((k) => ({
    key: k,
    header: label(k),
    align: typeof rows.find((r) => r[k] !== null && r[k] !== undefined)?.[k] === "string" && Number.isNaN(Number(rows[0]?.[k])) ? "left" : "right",
    value: (r) => (typeof r[k] === "object" ? JSON.stringify(r[k]) : (r[k] as string | number)),
    render: (r) => fmt(k, r[k]),
  }))
  return <DataTable rows={data} columns={columns} exportName={name} emptyTitle="No data for this period" pageSize={15} />
}

export default function ReportViewerPage() {
  const { id } = useParams<{ id: string }>()
  const { me } = useSession()
  const today = me?.business_date ?? new Date().toLocaleDateString("en-CA")
  const [from, setFrom] = React.useState("")
  const [to, setTo] = React.useState("")
  const f = from || today
  const t = to || today
  const report = useApi(
    () =>
      api<Report>("GET", `/reports/${id}`, { query: { date_from: f, date_to: t } }).catch((e) => {
        if (e instanceof ApiError && (e.status === 403 || e.status === 404)) return { error: e.message } as const
        throw e
      }),
    [id, f, t],
    null as Report | { error: string } | null
  )
  const info = described.find((r) => r.id === id)
  const data = report.data
  if (data && "error" in data)
    return (
      <Page>
        <EmptyState title={data.error} action={<LinkButton href="/reports">Back to reports</LinkButton>} />
      </Page>
    )
  const scalars = data ? Object.entries(data.summary ?? {}).filter(([, v]) => v === null || typeof v !== "object") : []
  const nested = data ? Object.entries(data.summary ?? {}).filter(([, v]) => v && typeof v === "object" && !Array.isArray(v)) : []
  const lists = data ? Object.entries(data.summary ?? {}).filter(([, v]) => Array.isArray(v) && v.length > 0 && typeof v[0] === "object") : []

  return (
    <Page>
      <PageHeader
        title={data?.name ?? info?.name ?? id}
        description={info?.purpose ?? "Built from posted transactions."}
        actions={
          <>
            {can(me, "report.export") && (
              <>
                <Button
                  variant="outline"
                  onClick={() => void download(`/reports/${id}/export`, `${id}-${f}-${t}.csv`, { date_from: f, date_to: t, format: "csv" }).catch((e) => toast.error(apiMessage(e)))}
                >
                  <FileSpreadsheet />
                  CSV
                </Button>
                <Button
                  variant="outline"
                  onClick={() =>
                    api("POST", `/reports/${id}/jobs`, { body: { date_from: f, date_to: t } }).then(
                      () => toast.success("Queued. Find it under Reports → Background jobs."),
                      (e) => toast.error(apiMessage(e))
                    )
                  }
                >
                  <Hourglass />
                  Run in background
                </Button>
              </>
            )}
            <Button variant="outline" onClick={() => window.print()}>
              <Printer />
              Print
            </Button>
          </>
        }
      />
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <label className="grid gap-1">
          From
          <Input type="date" className="h-9 w-40" value={f} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="grid gap-1">
          To
          <Input type="date" className="h-9 w-40" value={t} onChange={(e) => setTo(e.target.value)} />
        </label>
        {data && (
          <span className="pb-2 text-xs text-muted-foreground">
            {data.branch} · generated {when(data.generated_at)} by {data.generated_by}
          </span>
        )}
      </div>
      {report.loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {data && (
        <>
          {scalars.length > 0 && (
            <Panel title="Summary">
              <KV className="tabular" items={scalars.filter(([k]) => k !== "note").map(([k, v]) => [label(k), fmt(k, v as Value)] as [string, string])} />
            </Panel>
          )}
          {nested.map(([k, v]) => (
            <Panel key={k} title={label(k)}>
              <KV className="tabular" items={Object.entries(v as Record<string, Value>).map(([kk, vv]) => [label(kk), fmt(kk, vv)] as [string, string])} />
            </Panel>
          ))}
          {data.rows.length > 0 || lists.length === 0 ? <Table rows={data.rows} name={id} /> : null}
          {lists.map(([k, v]) => (
            <Panel key={k} title={label(k)}>
              <Table rows={v as Record<string, Value>[]} name={`${id}-${k}`} />
            </Panel>
          ))}
          {(data.note || typeof data.summary?.note === "string") && <Notice tone="info">{String(data.note ?? data.summary.note)}</Notice>}
        </>
      )}
    </Page>
  )
}
