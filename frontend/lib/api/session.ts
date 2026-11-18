/**
 * Signed-in session for the staff app.
 *
 * The access token lives only in memory (lib/api/client.ts). On a page load the session is restored from the
 * HttpOnly refresh cookie, then `/auth/me` gives the user's roles, permissions, approval limits, branches and
 * business date. Permissions shown here only hide what the user can't do; the backend enforces every request.
 */
import { useSyncExternalStore } from "react"
import { api, ApiError, login, logout, refreshSession, setAccessToken, setBranch, type Schemas } from "./client"
import { rms } from "@/lib/rms/store"
import type { Role } from "@/lib/rms/types"

export type Me = Schemas["MeOut"]
export type SessionStatus = "loading" | "anonymous" | "authenticated"

interface SessionState {
  status: SessionStatus
  me: Me | null
}

let state: SessionState = { status: "loading", me: null }
const initial = state
const listeners = new Set<() => void>()
const set = (s: SessionState) => {
  state = s
  listeners.forEach((l) => l())
}

export function useSession() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => state,
    () => initial
  )
}

/** The order in which a user's roles decide the main (displayed) role. */
const ROLE_ORDER: Role[] = ["OWNER", "GM", "BRMGR", "SYSADMIN", "ACCT", "AUDITOR", "SUPV", "KMGR", "CASHIER", "WAITER", "COOK", "BAR", "INVOFF", "PUROFF"]

function knownRoles(me: Me): Role[] {
  const codes = new Set(me.roles.map((r) => r.code))
  return ROLE_ORDER.filter((r) => codes.has(r))
}

async function loadMe(): Promise<Me> {
  const me = await api<Me>("GET", "/auth/me")
  setBranch(me.current_branch.id)
  const roles = knownRoles(me)
  // The existing screens read the user, roles and branch from the RMS store.
  rms.setUser(me.full_name, roles[0] ?? "WAITER", roles)
  rms.setBranch(me.current_branch.name_en)
  if (me.preferred_language === "km" || me.preferred_language === "en") rms.setLang(me.preferred_language)
  set({ status: "authenticated", me })
  return me
}

let restoring: Promise<void> | null = null

/** Called once by the auth guard: use the refresh cookie to get a new access token, or show the sign-in page. */
export function restoreSession(): Promise<void> {
  if (state.status !== "loading") return Promise.resolve()
  restoring ??= (async () => {
    try {
      if (await refreshSession()) {
        await loadMe()
        return
      }
    } catch {
      // fall through to signed out
    }
    set({ status: "anonymous", me: null })
  })()
  return restoring
}

export async function signIn(username: string, password: string): Promise<Me> {
  await login(username, password)
  return loadMe()
}

export async function signOut() {
  await logout()
  setAccessToken(null)
  setBranch(null)
  restoring = null
  set({ status: "anonymous", me: null })
}

/** Switch to another branch the user is assigned to (sent as X-Branch-Id on every request). */
export async function switchBranch(branchId: string) {
  setBranch(branchId)
  return loadMe()
}

export const can = (me: Me | null, permission: string) => !!me?.permissions.includes(permission)

/** Friendly sign-in errors from the backend's error codes. */
export function signInMessage(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case "INVALID_CREDENTIALS":
        return "Username or password is incorrect."
      case "ACCOUNT_LOCKED":
        return "This account is locked after too many failed attempts. Try again later or ask an administrator."
      case "ACCOUNT_INACTIVE":
        return "This account is not active. Ask an administrator."
      case "RATE_LIMITED":
        return "Too many attempts. Wait a moment and try again."
      default:
        return e.message
    }
  }
  return "Can't reach the server. Check your connection and try again."
}

/** Only allow same-site paths after sign-in (no open redirects or javascript: URLs). */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/"
}
