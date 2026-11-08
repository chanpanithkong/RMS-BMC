"use client"

import Link from "next/link"
import { ChevronRight } from "lucide-react"
import { DataTable } from "@/components/rms/data-table"
import {
  Page,
  PageHeader,
  PageTabs,
  Panel,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { reports } from "@/lib/rms/reports"
import { useRms } from "@/lib/rms/store"

const groups = [
  "Sales",
  "Control",
  "Finance",
  "Operations",
  "Inventory",
  "Purchasing",
]

export default function ReportsPage() {
  const { role } = useRms()
  const [tab, setTab] = useTab("catalogue")
  const allowed = reports.filter(
    (r) => r.roles.includes(role) || role === "OWNER"
  )
  return (
    <Page>
      <PageHeader
        title="Reports"
        description={`${allowed.length} reports available to your role, all built from posted transactions.`}
      />
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
          <p className="text-sm text-muted-foreground">
            Your role has no reports in this catalogue.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {groups.map((g) => {
              const items = allowed.filter((r) => r.group === g)
              return items.length === 0 ? null : (
                <Panel key={g} title={g}>
                  <ul className="-my-1 divide-y">
                    {items.map((r) => (
                      <li key={r.id}>
                        <Link
                          href={`/reports/${r.id}`}
                          className="flex items-center justify-between gap-2 py-2 text-sm hover:text-primary"
                        >
                          <span>
                            <span className="font-medium">{r.name}</span>
                            <span className="block text-xs text-muted-foreground">
                              {r.id} · {r.purpose}
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
          rows={[
            {
              id: "J-221",
              report: "RPT-16 Ingredient variance",
              started: "08/11 12:40",
              status: "In Progress",
              format: "Excel",
            },
            {
              id: "J-220",
              report: "RPT-02 Monthly sales",
              started: "08/11 09:02",
              status: "Completed",
              format: "PDF",
            },
            {
              id: "J-219",
              report: "RPT-26 Control exceptions",
              started: "07/11 18:31",
              status: "Failed",
              format: "Excel",
            },
          ]}
          exportName="report-jobs"
          columns={[
            { key: "id", header: "Job" },
            { key: "report", header: "Report" },
            { key: "format", header: "Format" },
            { key: "started", header: "Started" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
        />
      )}
      {tab === "scheduled" && (
        <DataTable
          rows={[
            {
              id: "1",
              report: "RPT-01 Daily sales",
              to: "owner@example.com",
              every: "Daily 23:30",
              format: "PDF",
            },
            {
              id: "2",
              report: "RPT-17 Inventory valuation",
              to: "acct@example.com",
              every: "Monthly, 1st",
              format: "Excel",
            },
          ]}
          exportName="scheduled-reports"
          columns={[
            { key: "report", header: "Report" },
            { key: "to", header: "Recipients" },
            { key: "every", header: "Schedule" },
            { key: "format", header: "Format" },
          ]}
        />
      )}
    </Page>
  )
}
