"use client"

import * as React from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { DataTable } from "@/components/rms/data-table"
import {
  Page,
  PageHeader,
  PageTabs,
  Panel,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { rms, useRms } from "@/lib/rms/store"
import { cn } from "@/lib/utils"

const prefs = [
  ["Order ready", true, true],
  ["Kitchen delay alerts", true, true],
  ["Pending approvals", true, true],
  ["Low stock and expiry", true, true],
  ["System alerts", true, true],
  ["Failed or pending payments", true, false],
  ["Open session reminders", true, false],
  ["Daily digest email", false, false],
] as const

export default function NotificationsPage() {
  const { notices } = useRms()
  const [tab, setTab] = useTab("inbox")
  const [kind, setKind] = React.useState("All")
  const [pref, setPref] = React.useState<Record<string, boolean>>(
    Object.fromEntries(prefs.map(([n, on]) => [n, on]))
  )
  const kinds = [
    "All",
    "Kitchen",
    "Stock",
    "Approval",
    "Payment",
    "Cash",
    "System",
  ]
  const shown = notices.filter((n) => kind === "All" || n.kind === kind)
  return (
    <Page>
      <PageHeader
        title="Notifications"
        description="Operational alerts for your role and branch."
        actions={
          <Button variant="outline" onClick={rms.markAllRead}>
            Mark all read
          </Button>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          {
            value: "inbox",
            label: "Inbox",
            count: notices.filter((n) => !n.read).length,
          },
          { value: "log", label: "Delivery log" },
          { value: "prefs", label: "Preferences" },
        ]}
      />
      {tab === "inbox" && (
        <>
          <div className="flex flex-wrap gap-1.5">
            {kinds.map((k) => (
              <Button
                key={k}
                size="sm"
                aria-pressed={k === kind}
                variant={k === kind ? "default" : "outline"}
                onClick={() => setKind(k)}
              >
                {k}
              </Button>
            ))}
          </div>
          <ul className="divide-y rounded-xl border bg-card">
            {shown.map((n) => (
              <li key={n.id}>
                <Link
                  href={n.href}
                  onClick={() => rms.markRead(n.id)}
                  className={cn(
                    "flex items-start justify-between gap-3 p-3 text-sm hover:bg-muted/50",
                    !n.read && "bg-accent/40"
                  )}
                >
                  <span>
                    <span className="font-medium">{n.title}</span>
                    {!n.read && (
                      <span className="ml-2 text-xs font-medium text-primary">
                        Unread
                      </span>
                    )}
                    <span className="block text-muted-foreground">
                      {n.body}
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    <StatusBadge status={n.kind} tone="neutral" />
                    <span className="tabular text-xs text-muted-foreground">
                      {n.at}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
      {tab === "log" && (
        <DataTable
          rows={[
            {
              id: "1",
              time: "08/11 12:10",
              channel: "SMS",
              to: "012 ••• 441",
              template: "Reservation reminder",
              attempts: 1,
              status: "Delivered",
            },
            {
              id: "2",
              time: "08/11 11:40",
              channel: "Email",
              to: "sales@example.com",
              template: "Purchase order",
              attempts: 1,
              status: "Delivered",
            },
            {
              id: "3",
              time: "08/11 10:05",
              channel: "SMS",
              to: "097 ••• 112",
              template: "Table ready",
              attempts: 3,
              status: "Failed",
            },
          ]}
          exportName="delivery-log"
          columns={[
            { key: "time", header: "Time" },
            { key: "channel", header: "Channel" },
            { key: "to", header: "Recipient" },
            { key: "template", header: "Template" },
            { key: "attempts", header: "Attempts", align: "right" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
        />
      )}
      {tab === "prefs" && (
        <Panel
          title="What you receive"
          description="Mandatory operational alerts can't be turned off."
          className="max-w-lg"
        >
          <ul className="divide-y">
            {prefs.map(([n, , locked]) => (
              <li
                key={n}
                className="flex items-center justify-between py-2 text-sm"
              >
                <span>
                  {n}
                  {locked && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      Required
                    </span>
                  )}
                </span>
                <Switch
                  aria-label={n}
                  disabled={locked}
                  checked={pref[n]}
                  onCheckedChange={(c) => {
                    setPref({ ...pref, [n]: Boolean(c) })
                    toast.success("Preference saved")
                  }}
                />
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </Page>
  )
}
