"use client"

import * as React from "react"
import { Eye, ShieldCheck } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DataTable } from "@/components/rms/data-table"
import { KV, Notice, Page, PageHeader } from "@/components/rms/kit"
import { auditLog } from "@/lib/rms/back-office"

type Entry = (typeof auditLog)[number]

export default function AuditPage() {
  const [open, setOpen] = React.useState<Entry | null>(null)
  return (
    <Page>
      <PageHeader
        title="Audit trail"
        description="An append-only record of user and system actions. Entries can't be edited or deleted."
      />
      <Notice tone="success">
        <span className="flex items-center gap-1.5">
          <ShieldCheck className="size-4" />
          Hash chain last verified 08/11/2026 02:00. No breaks found.
        </span>
      </Notice>
      <DataTable
        rows={auditLog}
        pageSize={12}
        exportName="audit-log"
        onRowClick={setOpen}
        filters={[
          { key: "actor", label: "User" },
          { key: "entity", label: "Entity" },
          { key: "branch", label: "Branch" },
        ]}
        searchPlaceholder="Action, entity ID, user…"
        columns={[
          { key: "time", header: "Time" },
          { key: "actor", header: "User" },
          {
            key: "action",
            header: "Action",
            render: (a) => <code className="text-xs">{a.action}</code>,
          },
          { key: "entity", header: "Entity" },
          { key: "entityId", header: "Entity ID" },
          { key: "branch", header: "Branch" },
          { key: "before", header: "Before", hidden: true },
          { key: "after", header: "After" },
          { key: "device", header: "Device", hidden: true },
          { key: "ip", header: "IP", hidden: true },
        ]}
        rowActions={() => [
          { label: "View entry", icon: Eye, onClick: setOpen },
        ]}
      />
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="sm:max-w-lg">
          {open && (
            <>
              <DialogHeader>
                <DialogTitle>
                  <code>{open.action}</code>
                </DialogTitle>
                <DialogDescription>{open.time}</DialogDescription>
              </DialogHeader>
              <KV
                items={[
                  ["Actor", open.actor],
                  ["Entity", `${open.entity} ${open.entityId}`],
                  ["Branch", open.branch],
                  ["Before", open.before],
                  ["After", open.after],
                  ["IP address", open.ip],
                  ["Device", open.device],
                  ["Reason", open.reason || "—"],
                  ["Correlation ID", open.correlation],
                ]}
              />
            </>
          )}
        </DialogContent>
      </Dialog>
    </Page>
  )
}
