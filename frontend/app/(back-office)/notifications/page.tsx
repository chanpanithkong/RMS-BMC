"use client"

import * as React from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Notice, Page, PageHeader, PageTabs, StatusBadge, useTab } from "@/components/rms/kit"
import { MessageLogTab, PreferencesTab } from "@/components/rms/operations"
import { can, useSession } from "@/lib/api/session"
import { markAllRead, markRead } from "@/lib/api/notifications"
import { useRms } from "@/lib/rms/store"
import { cn } from "@/lib/utils"


export default function NotificationsPage() {
  const { notices } = useRms()
  const [tab, setTab] = useTab("inbox")
  const { me } = useSession()
  const [kind, setKind] = React.useState("All")
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
          <Button variant="outline" onClick={() => void markAllRead()}>
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
            {shown.length === 0 && <li className="p-6 text-center text-sm text-muted-foreground">No notifications.</li>}
          {shown.map((n) => (
              <li key={n.id}>
                <Link
                  href={n.href}
                  onClick={() => void markRead(n.id)}
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
      {tab === "log" && (can(me, "messages.view") ? <MessageLogTab /> : <Notice tone="info">The delivery log is for managers and administrators.</Notice>)}
      {tab === "prefs" && <PreferencesTab />}
    </Page>
  )
}
