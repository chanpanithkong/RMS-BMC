/** Small helpers for back-office screens that read from and write to the RMS API. */
import * as React from "react"
import { toast } from "sonner"
import { ApiError } from "./client"
import { useSession } from "./session"

export const apiMessage = (e: unknown) =>
  e instanceof ApiError ? e.message : "Can't reach the server. Check the connection and try again."

export function showError(e: unknown) {
  toast.error(apiMessage(e))
}

/**
 * Load data for a screen. `deps` re-run the loader; it also re-runs when the user switches branch.
 * Returns the data (or `initial` until loaded), whether it is loading, and `reload()` for after a change.
 */
export function useApi<T>(load: () => Promise<T>, deps: React.DependencyList, initial: T) {
  const { me } = useSession()
  const branch = me?.current_branch.id
  const [data, setData] = React.useState<T>(initial)
  const [loading, setLoading] = React.useState(true)
  const [tick, setTick] = React.useState(0)
  const loader = React.useRef(load)
  React.useEffect(() => {
    loader.current = load
  })
  React.useEffect(() => {
    if (!branch) return
    let live = true
    loader
      .current()
      .then((d) => live && setData(d), showError)
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [branch, tick, ...deps])
  const reload = React.useCallback(() => setTick((t) => t + 1), [])
  return { data, loading, reload, setData }
}

/** Run a write, toast the result, and reload. Resolves to false if it failed (the error is shown). */
export async function act(fn: () => Promise<unknown>, done?: string, after?: () => void) {
  try {
    await fn()
    if (done) toast.success(done)
    return true
  } catch (e) {
    showError(e)
    return false
  } finally {
    after?.()
  }
}

/** Throw form-friendly errors (the server's message) so RecordDialog shows them inline. */
export async function save<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn()
  } catch (e) {
    throw new Error(apiMessage(e))
  }
}

export const num = (v: unknown) => (v === null || v === undefined || v === "" ? 0 : Number(v))
export const str = (v: unknown) => (v === null || v === undefined ? "" : String(v))
/** "YYYY-MM-DD HH:MM" in local time. */
export const when = (iso?: string | null) => {
  if (!iso) return ""
  const d = new Date(iso)
  return `${d.toLocaleDateString("en-CA")} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}`
}
