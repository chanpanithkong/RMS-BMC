/**
 * Typed client for the RMS FastAPI backend.
 * Types come from lib/api/schema.d.ts, generated from the backend OpenAPI spec:
 *   npx openapi-typescript@7.4.4 http://localhost:8000/api/v1/openapi.json -o lib/api/schema.d.ts
 *
 * Money values arrive as decimal strings ("12.99"). Display them as-is or with Intl;
 * never do arithmetic on them in the browser (the backend is authoritative, SRS C-02).
 */
import type { components, paths } from "./schema"

export type Schemas = components["schemas"]
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "")

export interface ApiErrorBody {
  code: string
  message: string
  details?: { field?: string; issue?: string }[]
  correlation_id: string
  [extra: string]: unknown
}

export class ApiError extends Error {
  constructor(public status: number, public body: ApiErrorBody) {
    super(body.message)
  }
  get code() {
    return this.body.code
  }
}

let accessToken: string | null = null
let branchId: string | null = null
export const setAccessToken = (t: string | null) => (accessToken = t)
export const setBranch = (id: string | null) => (branchId = id)

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE"
interface Options {
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  /** Pass true to generate a key, or a string to reuse one when retrying (BR-030). */
  idempotent?: boolean | string
  ifMatch?: number
  signal?: AbortSignal
}

export const newIdempotencyKey = () => crypto.randomUUID()

async function refresh(): Promise<boolean> {
  const r = await fetch(`${API_URL}/api/v1/auth/refresh`, { method: "POST", credentials: "include" })
  if (!r.ok) return false
  accessToken = (await r.json()).access_token
  return true
}

export async function api<T = unknown>(method: Method, path: keyof paths | string, opts: Options = {}, retried = false): Promise<T> {
  const url = new URL(`${API_URL}/api/v1${path}`)
  for (const [k, v] of Object.entries(opts.query ?? {})) if (v !== undefined && v !== null) url.searchParams.set(k, String(v))
  const headers: Record<string, string> = { Accept: "application/json" }
  if (opts.body !== undefined) headers["Content-Type"] = "application/json"
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  if (branchId) headers["X-Branch-Id"] = branchId
  if (opts.idempotent) headers["Idempotency-Key"] = typeof opts.idempotent === "string" ? opts.idempotent : newIdempotencyKey()
  if (opts.ifMatch !== undefined) headers["If-Match"] = String(opts.ifMatch)

  const res = await fetch(url, {
    method,
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    credentials: "include", // the refresh token travels only in an HttpOnly cookie
    signal: opts.signal,
  })
  if (res.status === 401 && !retried && !String(path).startsWith("/auth/")) {
    if (await refresh()) return api<T>(method, path, opts, true)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: { code: "HTTP_ERROR", message: res.statusText, correlation_id: "" } }))
    throw new ApiError(res.status, body.error)
  }
  if (res.status === 204) return undefined as T
  const type = res.headers.get("content-type") ?? ""
  return (type.includes("json") ? res.json() : res.text()) as Promise<T>
}

export async function login(username: string, password: string) {
  const data = await api<Schemas["TokenOut"]>("POST", "/auth/login", { body: { username, password } })
  accessToken = data.access_token
  return data
}

export async function logout() {
  await api("POST", "/auth/logout").catch(() => undefined)
  accessToken = null
}

/** Subscribe to real-time topics, e.g. `station:<branchId>:HOT`. Reconnects and resubscribes automatically. */
export function connectRealtime(topics: string[], onEvent: (event: { topic: string; type: string; data: Record<string, unknown> }) => void) {
  let ws: WebSocket | null = null
  let closed = false
  let delay = 1000
  const open = () => {
    if (!accessToken) return
    ws = new WebSocket(`${API_URL.replace(/^http/, "ws")}/api/v1/ws?token=${encodeURIComponent(accessToken)}`)
    ws.onopen = () => {
      delay = 1000
      topics.forEach((topic) => ws?.send(JSON.stringify({ action: "subscribe", topic })))
    }
    ws.onmessage = (m) => {
      const event = JSON.parse(m.data)
      if (event.type !== "subscribed") onEvent(event)
    }
    ws.onclose = () => {
      if (!closed) setTimeout(open, (delay = Math.min(delay * 2, 30000)))
    }
  }
  open()
  return () => {
    closed = true
    ws?.close()
  }
}
