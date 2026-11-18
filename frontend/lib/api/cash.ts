/**
 * Cashier sessions against the RMS API (SRS §6.14). The backend computes expected cash and variances; the
 * cashier's count is blind, so expected amounts are only shown after the count is submitted (FR-STAFF-009).
 */
import { api } from "./client"
import { rms } from "@/lib/rms/store"
import type { CashierSession, CashMovement } from "@/lib/rms/types"

interface ApiSession {
  id: string
  user_id: string
  business_date: string
  status: string
  opened_at: string
  closed_at: string | null
  approved_by: string | null
  variance_reason: string | null
  floats: Record<string, string>
  results: { currency: string; expected: string; counted: string; variance: string }[] | null
  user_name?: string | null
  approved_by_name?: string | null
  movements?: { id: string; kind: string; currency: string; amount: string; reason: string; created_at: string; approved_by_name: string | null }[]
}

export interface SessionReport {
  kind: "X" | "Z"
  status: string
  opened_at: string
  closed_at: string | null
  floats: Record<string, string>
  payments: { method_currency: string; count: number; tendered: string; base: string }[]
  refunds: { refund_no: string; currency: string; amount: string }[]
  movements: { kind: string; currency: string; amount: string; reason: string }[]
  expected?: Record<string, string> | null
  results?: { currency: string; expected: string; counted: string; variance: string }[]
}

const STATUS: Record<string, CashierSession["status"]> = {
  ClosingPendingApproval: "Pending Approval",
  ForceClosed: "Force Closed",
}
const KIND: Record<string, CashMovement["kind"]> = { PaidOut: "Paid-out", PaidIn: "Paid-in", Drop: "Cash drop" }
export const KIND_CODE: Record<CashMovement["kind"], string> = { "Paid-out": "PaidOut", "Paid-in": "PaidIn", "Cash drop": "Drop" }

const n = (v?: string | null) => (v === null || v === undefined ? 0 : Number(v))
/** "YYYY-MM-DD HH:MM" in local time (the screens split date and time on the space). */
const when = (iso?: string | null) => {
  if (!iso) return undefined
  const d = new Date(iso)
  return `${d.toLocaleDateString("en-CA")} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}`
}

export function toSession(s: ApiSession, myId?: string): CashierSession {
  const res = Object.fromEntries((s.results ?? []).map((r) => [r.currency, r]))
  return {
    id: s.id,
    cashier: s.user_name ?? "",
    branch: "",
    terminal: "—",
    opened: when(s.opened_at) ?? "",
    closed: when(s.closed_at),
    floatUSD: n(s.floats.USD),
    floatKHR: n(s.floats.KHR),
    salesUSD: 0,
    salesKHR: 0,
    refundsUSD: 0,
    status: STATUS[s.status] ?? (s.status as CashierSession["status"]),
    countedUSD: res.USD ? n(res.USD.counted) : undefined,
    countedKHR: res.KHR ? n(res.KHR.counted) : undefined,
    varianceUSD: res.USD ? n(res.USD.variance) : undefined,
    varianceKHR: res.KHR ? n(res.KHR.variance) : undefined,
    movements: (s.movements ?? []).map((m) => ({
      id: m.id,
      kind: KIND[m.kind] ?? (m.kind as CashMovement["kind"]),
      currency: m.currency as "USD" | "KHR",
      amount: n(m.amount),
      reason: m.reason,
      time: when(m.created_at) ?? "",
      approvedBy: m.approved_by_name ?? undefined,
    })),
    approver: s.approved_by_name ?? undefined,
    varianceReason: s.variance_reason ?? undefined,
    mine: s.user_id === myId,
  }
}

/** Load the user's own open session, plus every branch session for users with cash.view. */
export async function loadSessions(myId: string, canViewAll: boolean) {
  const [current, all] = await Promise.all([
    api<ApiSession | null>("GET", "/cashier-sessions/current"),
    canViewAll ? api<ApiSession[]>("GET", "/cashier-sessions") : Promise.resolve([] as ApiSession[]),
  ])
  const list = canViewAll ? all : []
  if (current && !list.some((s) => s.id === current.id)) list.unshift(current)
  const sessions = list.map((s) => toSession(s, myId))
  rms.loadSessions(sessions)
  return sessions
}

export const openSession = (floats: { USD: number; KHR: number }) =>
  api<ApiSession>("POST", "/cashier-sessions", { body: { floats: { USD: String(floats.USD), KHR: String(floats.KHR) } } })

export const addMovement = (sessionId: string, m: { kind: CashMovement["kind"]; currency: "USD" | "KHR"; amount: number; reason: string }) =>
  api("POST", `/cashier-sessions/${sessionId}/cash-movements`, {
    body: { kind: KIND_CODE[m.kind], currency: m.currency, amount: String(m.amount), reason: m.reason },
  })

/** Submit the blind count. Returns the session with expected, counted and variance per currency. */
export async function closeSession(
  sessionId: string,
  counts: { USD: number; KHR: number },
  denominations: { USD: Record<string, number>; KHR: Record<string, number> },
  myId: string
) {
  const s = await api<ApiSession>("POST", `/cashier-sessions/${sessionId}/close`, {
    body: { counts: { USD: String(counts.USD), KHR: String(counts.KHR) }, denominations },
  })
  return toSession(s, myId)
}

export const approveVariance = (sessionId: string, reason: string) =>
  api<ApiSession>("POST", `/cashier-sessions/${sessionId}/approve-variance`, { body: { reason } })

export const forceClose = (sessionId: string, reason: string) =>
  api<ApiSession>("POST", `/cashier-sessions/${sessionId}/force-close`, { body: { reason } })

export const sessionReport = (sessionId: string) => api<SessionReport>("GET", `/cashier-sessions/${sessionId}/report`)
