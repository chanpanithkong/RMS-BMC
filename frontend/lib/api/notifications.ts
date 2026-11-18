/** In-app notifications (SRS §6.20): loaded from the API and refreshed live over the user's WebSocket topic. */
import * as React from "react"
import { api, connectRealtime } from "./client"
import { useSession } from "./session"
import { rms } from "@/lib/rms/store"
import type { Notice } from "@/lib/rms/types"

interface ApiNotification {
  id: string
  kind: string
  title: string
  body: string
  link: string | null
  created_at: string
  read_at: string | null
}

const toNotice = (n: ApiNotification): Notice => ({
  id: n.id,
  title: n.title,
  body: n.body,
  kind: n.kind as Notice["kind"],
  at: new Date(n.created_at).toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }),
  read: !!n.read_at,
  href: n.link ?? "/notifications",
})

export async function loadNotifications() {
  const r = await api<{ data: ApiNotification[]; unread: number }>("GET", "/notifications", { query: { page_size: 100 } })
  rms.loadNotices(r.data.map(toNotice))
  return r.unread
}

export async function markRead(id: string) {
  rms.markRead(id)
  await api("POST", `/notifications/${id}/read`).catch(() => undefined)
}

export async function markAllRead() {
  rms.markAllRead()
  await api("POST", "/notifications/read-all").catch(() => undefined)
}

/** Keep notifications current while signed in (used once, by the app header). */
export function useNotificationSync() {
  const { me } = useSession()
  const userId = me?.id
  React.useEffect(() => {
    if (!userId) return
    void loadNotifications().catch(() => undefined)
    const stop = connectRealtime([`user:${userId}`], (ev) => {
      if (ev.type === "notification") void loadNotifications().catch(() => undefined)
    })
    const timer = setInterval(() => void loadNotifications().catch(() => undefined), 120_000)
    return () => {
      stop()
      clearInterval(timer)
    }
  }, [userId])
}
