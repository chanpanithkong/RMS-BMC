"use client"

import * as React from "react"
import { Download, ShieldAlert, ShieldCheck } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { DataTable } from "@/components/rms/data-table"
import { KV, Notice, Page, PageHeader } from "@/components/rms/kit"
import { api, download } from "@/lib/api/client"
import { can, useSession } from "@/lib/api/session"
import { apiMessage, useApi, when } from "@/lib/api/use-api"

interface Entry {
  id: number
  occurred_at: string
  actor_user_id: string | null
  actor_type: string
  ip: string | null
  action: string
  entity_type: string
  entity_id: string | null
  before_data: Record<string, unknown> | null
  after_data: Record<string, unknown> | null
  reason: string | null
  correlation_id: string | null
  entry_hash: string
}

const json = (v: unknown) => (v ? JSON.stringify(v, null, 2) : "—")

export default function AuditPage() {
  const { me } = useSession()
  const [open, setOpen] = React.useState<Entry | null>(null)
  const [from, setFrom] = React.useState("")
  const [to, setTo] = React.useState("")
  const [action, setAction] = React.useState("")
  const [entity, setEntity] = React.useState("")
  const query = {
    date_from: from ? new Date(`${from}T00:00`).toISOString() : undefined,
    date_to: to ? new Date(`${to}T23:59:59`).toISOString() : undefined,
    action: action.trim() || undefined,
    entity_type: entity.trim() || undefined,
  }
  const key = JSON.stringify(query)
  const log = useApi(async () => (await api<{ data: Entry[]; total: number }>("GET", "/audit-logs", { query: { ...query, page_size: 200 } })), [key], { data: [], total: 0 })
  const chain = useApi(() => api<{ valid: boolean; checked: number; broken_at_id: number | null }>("GET", "/audit-logs/integrity"), [], null)
  const users = useApi(
    async () => (can(me, "users.view") ? (await api<{ data: { id: string; full_name: string }[] }>("GET", "/users", { query: { page_size: 200 } })).data : []),
    [me?.id],
    []
  )
  const who = (e: Entry) => (e.actor_user_id ? (users.data.find((u) => u.id === e.actor_user_id)?.full_name ?? "User") : e.actor_type)
  const rows = log.data.data.map((e) => ({ ...e, time: when(e.occurred_at), actor: who(e), target: `${e.entity_type}${e.entity_id ? ` ${e.entity_id.slice(0, 8)}` : ""}` }))

  return (
    <Page>
      <PageHeader
        title="Audit trail"
        description="An append-only record of user and system actions. Entries can't be edited or deleted."
        actions={
          can(me, "audit.export") && (
            <Button
              variant="outline"
              onClick={() =>
                void download("/audit-logs/export", "audit-log.csv", query as Record<string, string | undefined>).catch((e) => toast.error(apiMessage(e)))
              }
            >
              <Download />
              Export CSV
            </Button>
          )
        }
      />
      {chain.data &&
        (chain.data.valid ? (
          <Notice tone="success">
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="size-4" />
              Hash chain verified just now: {chain.data.checked.toLocaleString()} entries, no breaks.
            </span>
          </Notice>
        ) : (
          <Notice tone="danger">
            <span className="flex items-center gap-1.5">
              <ShieldAlert className="size-4" />
              The hash chain is broken at entry {chain.data.broken_at_id}. Records after it may have been changed outside the system.
            </span>
          </Notice>
        ))}
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <label className="grid gap-1">
          From
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-9 w-40" />
        </label>
        <label className="grid gap-1">
          To
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-9 w-40" />
        </label>
        <label className="grid gap-1">
          Action
          <Input placeholder="e.g. order.cancel" value={action} onChange={(e) => setAction(e.target.value)} className="h-9 w-44" />
        </label>
        <label className="grid gap-1">
          Entity
          <Input placeholder="e.g. Order" value={entity} onChange={(e) => setEntity(e.target.value)} className="h-9 w-36" />
        </label>
        <span className="pb-2 text-muted-foreground">
          {log.data.total > rows.length ? `Showing the newest ${rows.length} of ${log.data.total.toLocaleString()}` : `${rows.length} entries`}
        </span>
      </div>
      <DataTable
        rows={rows.map((r) => ({ ...r, id: String(r.id) }))}
        pageSize={14}
        exportName="audit-log"
        emptyTitle={log.loading ? "Loading…" : "No entries"}
        onRowClick={(r) => setOpen(log.data.data.find((e) => String(e.id) === r.id) ?? null)}
        filters={[{ key: "actor", label: "User" }, { key: "entity_type", label: "Entity" }]}
        columns={[
          { key: "time", header: "Time" },
          { key: "actor", header: "User" },
          { key: "action", header: "Action", render: (r) => <code className="text-xs">{r.action}</code> },
          { key: "target", header: "Record" },
          { key: "reason", header: "Reason", render: (r) => r.reason ?? "—" },
          { key: "ip", header: "IP", render: (r) => r.ip ?? "—" },
        ]}
      />
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          {open && (
            <>
              <DialogHeader>
                <DialogTitle>{open.action}</DialogTitle>
                <DialogDescription>
                  {when(open.occurred_at)} · {who(open)}
                </DialogDescription>
              </DialogHeader>
              <KV
                items={[
                  ["Record", `${open.entity_type} ${open.entity_id ?? ""}`],
                  ["Reason", open.reason ?? "—"],
                  ["IP", open.ip ?? "—"],
                  ["Correlation", open.correlation_id ?? "—"],
                  ["Entry hash", <code key="h" className="break-all text-xs">{open.entry_hash}</code>],
                ]}
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Before</p>
                  <pre className="max-h-64 overflow-auto rounded-md bg-muted p-2 text-xs">{json(open.before_data)}</pre>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">After</p>
                  <pre className="max-h-64 overflow-auto rounded-md bg-muted p-2 text-xs">{json(open.after_data)}</pre>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </Page>
  )
}
