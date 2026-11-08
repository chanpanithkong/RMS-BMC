"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import { FileSpreadsheet, FileText, Printer } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { ChartCard } from "@/components/rms/chart-card"
import { DataTable, type Column } from "@/components/rms/data-table"
import {
  DateRangeFilter,
  EmptyState,
  FormRow,
  LinkButton,
  Page,
  PageHeader,
  Panel,
  SimpleSelect,
  Stat,
  opts,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import { reports, type Fmt } from "@/lib/rms/reports"
import { useRms } from "@/lib/rms/store"

const fmtVal = (v: string | number, f: Fmt) =>
  f === "usd"
    ? usd(Number(v))
    : f === "pct"
      ? `${v}%`
      : f === "num"
        ? Number(v).toLocaleString("en-US")
        : String(v)
const scale: Record<string, number> = {
  Today: 1,
  Yesterday: 1.08,
  "This week": 6.4,
  "This month": 26.5,
  Custom: 12,
}
type Row = Record<string, string | number> & { id: string }

export default function ReportViewerPage() {
  const { id } = useParams<{ id: string }>()
  const { role, branch, userName } = useRms()
  const def = reports.find((r) => r.id === id)
  const [range, setRange] = React.useState("Today")
  const [chosenBranch, setChosenBranch] = React.useState(branch)
  if (!def)
    return (
      <Page>
        <EmptyState
          title="Report not found"
          action={<LinkButton href="/reports">Back to reports</LinkButton>}
        />
      </Page>
    )
  if (!def.roles.includes(role) && role !== "OWNER")
    return (
      <Page>
        <EmptyState
          title="You don't have access to this report"
          action={<LinkButton href="/reports">Back to reports</LinkButton>}
        />
      </Page>
    )
  const data = def.build(scale[range])
  const rows: Row[] = data.rows.map((r, i) => ({ ...r, id: String(i) }))
  const columns: Column<Row>[] = data.columns.map((c) => ({
    key: c.key,
    header: c.header,
    align: c.fmt === "text" ? "left" : "right",
    value: (r) => r[c.key],
    render: (r) => fmtVal(r[c.key], c.fmt),
  }))
  const extra = def.filters.filter(
    (f) =>
      ![
        "Period",
        "Business day",
        "Month",
        "Branch",
        "Branches",
        "As-of date",
        "Period between counts",
      ].includes(f)
  )
  return (
    <Page>
      <PageHeader
        title={def.name}
        description={`${def.id} · ${def.purpose}`}
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => {
                toast.success("Export queued and recorded in the audit log")
              }}
            >
              <FileSpreadsheet />
              Excel
            </Button>
            <Button variant="outline" onClick={() => window.print()}>
              <FileText />
              PDF
            </Button>
            <Button variant="outline" onClick={() => window.print()}>
              <Printer />
              Print
            </Button>
          </>
        }
      />
      <Panel title="Filters">
        <div className="flex flex-wrap items-end gap-3">
          <FormRow label="Period">
            <DateRangeFilter value={range} onChange={setRange} />
          </FormRow>
          <FormRow label="Branch">
            <SimpleSelect
              aria-label="Branch"
              className="w-36"
              value={chosenBranch}
              onChange={setChosenBranch}
              options={opts("Riverside", "BKK1", "Siem Reap")}
            />
          </FormRow>
          {extra.map((f) => (
            <FormRow key={f} label={f}>
              <SimpleSelect
                aria-label={f}
                className="w-36"
                value="All"
                onChange={() => toast.info(`${f} filter applied`)}
                options={opts("All")}
              />
            </FormRow>
          ))}
        </div>
      </Panel>
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {data.kpis.map(([l, v]) => (
          <Stat key={l} label={l} value={v} />
        ))}
      </section>
      {data.chart && (
        <ChartCard
          title={data.chart.label}
          type={data.chart.type}
          data={data.rows}
          xKey={data.chart.x}
          series={[{ key: data.chart.y, label: data.chart.label }]}
          format={
            data.chart.money
              ? (v) => `$${Math.round(v).toLocaleString()}`
              : undefined
          }
        />
      )}
      <DataTable
        key={id + range}
        rows={rows}
        columns={columns}
        exportName={def.id}
        pageSize={15}
      />
      <footer className="rounded-lg bg-muted p-3 text-xs text-muted-foreground">
        Filters: {range}, {chosenBranch} · Generated 08/11/2026 13:02 by{" "}
        {userName} · Currency USD · Figures derived from recorded transactions;
        illustrative examples are not business results.
      </footer>
    </Page>
  )
}
