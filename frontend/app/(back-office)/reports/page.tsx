"use client"

import Link from "next/link"
import { ChevronRight, Download } from "lucide-react"
import { toast } from "sonner"
import { DataTable } from "@/components/rms/data-table"
import { Page, PageHeader, PageTabs, Panel, StatusBadge, useTab } from "@/components/rms/kit"
import { api, download } from "@/lib/api/client"
import { ScheduledReportsTab } from "@/components/rms/operations"
import { can, useSession } from "@/lib/api/session"
import { apiMessage, useApi, when } from "@/lib/api/use-api"
import { reports as described } from "@/lib/rms/reports"

const groups = ["Sales", "Control", "Finance", "Operations", "Inventory", "Purchasing"]

interface Job {
  id: string
  report_id: string
  params: Record<string, string>
  status: string
  rows: number | null
  error: string | null
  created_at: string
  finished_at: string | null
  download: string | null
}

export default function ReportsPage() {
  const { me } = useSession()
  const [tab, setTab] = useTab("catalogue")
  const catalogue = useApi(() => api<{ id: string; name: string; available: boolean }[]>("GET", "/reports"), [], [])
  const jobs = useApi(() => (can(me, "report.export") ? api<Job[]>("GET", "/report-jobs") : Promise.resolve([])), [tab === "jobs", me?.id], [])
  // Group and one-line purpose come from the SRS catalogue text; names and access come from the server.
  const info = Object.fromEntries(described.map((r) => [r.id, r]))
  const allowed = catalogue.data.filter((r) => r.available)
  const name = (id: string) => catalogue.data.find((r) => r.id === id)?.name ?? id

  return (
    <Page>
      <PageHeader title="Reports" description={`${allowed.length} reports available to your role, all built from posted transactions.`} />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "catalogue", label: "Catalogue" },
          { value: "jobs", label: "Background jobs" },
          { value: "scheduled", label: "Scheduled" },
        ]}
      />
      {tab === "catalogue" &&
        (allowed.length === 0 ? (
          <p className="text-sm text-muted-foreground">{catalogue.loading ? "Loading…" : "Your role has no reports."}</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {[...groups, "Other"].map((g) => {
              const items = allowed.filter((r) => (info[r.id]?.group ?? "Other") === g)
              return items.length === 0 ? null : (
                <Panel key={g} title={g}>
                  <ul className="-my-1 divide-y">
                    {items.map((r) => (
                      <li key={r.id}>
                        <Link href={`/reports/${r.id}`} className="flex items-center justify-between gap-2 py-2 text-sm hover:text-primary">
                          <span>
                            <span className="font-medium">{r.name}</span>
                            <span className="block text-xs text-muted-foreground">
                              {r.id}
                              {info[r.id] ? ` · ${info[r.id].purpose}` : ""}
                            </span>
                          </span>
                          <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                </Panel>
              )
            })}
          </div>
        ))}
      {tab === "jobs" && (
        <DataTable
          rows={jobs.data.map((j) => ({
            ...j,
            report: `${j.report_id} ${name(j.report_id)}`,
            period: `${j.params.date_from ?? ""} – ${j.params.date_to ?? ""}`,
            started: when(j.created_at),
          }))}
          exportName="report-jobs"
          emptyTitle={can(me, "report.export") ? "No background jobs. Large reports can be queued from the report page." : "Exporting reports needs the export permission."}
          columns={[
            { key: "report", header: "Report" },
            { key: "period", header: "Period" },
            { key: "started", header: "Started" },
            { key: "rows", header: "Rows", align: "right", render: (j) => j.rows ?? "—" },
            { key: "status", header: "Status", render: (j) => <StatusBadge status={j.status} tone={j.status === "Failed" ? "danger" : undefined} /> },
            { key: "error", header: "Problem", render: (j) => j.error ?? "" },
          ]}
          rowActions={(j) => [
            {
              label: "Download CSV",
              icon: Download,
              hidden: () => !j.download,
              onClick: () => void download(`/report-jobs/${j.id}/download`, `${j.report_id}.csv`).catch((e) => toast.error(apiMessage(e))),
            },
          ]}
        />
      )}
      {tab === "scheduled" && <ScheduledReportsTab reports={allowed} />}
    </Page>
  )
}
