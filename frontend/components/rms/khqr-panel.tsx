"use client"

/**
 * KHQR payment for an online order (FR-ONL-007). The QR string comes from the server (Bakong); this only draws it,
 * counts down to its expiry, checks the payment every few seconds, and offers a new code once it expires.
 */
import * as React from "react"
import QRCode from "qrcode"
import { Button } from "@/components/ui/button"
import * as pub from "@/lib/api/public"
import { apiMessage } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

const left = (iso: string | null, now: number) => (iso ? Math.max(0, Math.floor((new Date(iso).getTime() - now) / 1000)) : 0)

export function KhqrPanel({ token, onPaid }: { token: string; onPaid: () => void }) {
  const [state, setState] = React.useState<pub.KhqrState | null>(null)
  const [img, setImg] = React.useState("")
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [now, setNow] = React.useState(() => Date.now())

  React.useEffect(() => {
    let live = true
    const check = () =>
      pub.paymentState(token).then(
        (s) => {
          if (!live) return
          setState(s)
          setError("")
          if (s.payment_status === "Paid") onPaid()
        },
        (e) => live && setError(apiMessage(e))
      )
    void check()
    const poll = setInterval(() => void check(), 5_000)
    const tick = setInterval(() => setNow(Date.now()), 1_000)
    return () => {
      live = false
      clearInterval(poll)
      clearInterval(tick)
    }
  }, [token, onPaid])

  React.useEffect(() => {
    let live = true
    if (state?.qr)
      void QRCode.toDataURL(state.qr, { margin: 1, width: 280, errorCorrectionLevel: "M" }).then((url) => live && setImg(url))
    return () => {
      live = false
    }
  }, [state?.qr])

  if (!state) return error ? <p className="mt-4 text-sm text-danger">{error}</p> : null
  if (state.payment_status === "Paid") return <p className="mt-4 rounded-lg bg-success-soft p-3 text-sm text-success">Payment received. Thank you.</p>
  if (state.payment_status !== "Pending") return null

  const secs = left(state.expires_at, now)
  const expired = !state.qr || secs === 0
  const renew = async () => {
    setBusy(true)
    try {
      setState(await pub.newKhqr(token))
      setNow(Date.now())
    } catch (e) {
      setError(apiMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="mt-4 rounded-xl border p-4 text-center" aria-live="polite">
      <h2 className="text-sm font-semibold">Pay with KHQR</h2>
      <p className="text-xs text-muted-foreground">
        Scan with any Cambodian banking app · {state.currency === "KHR" ? `៛${Math.round(Number(state.amount)).toLocaleString()}` : usd(Number(state.amount))}
      </p>
      {expired ? (
        <div className="py-6">
          <p className="text-sm">This code has expired.</p>
          <Button className="mt-3" onClick={() => void renew()} disabled={busy}>
            {busy ? "Getting a new code…" : "Get a new code"}
          </Button>
        </div>
      ) : (
        <>
          {img ? (
            // eslint-disable-next-line @next/next/no-img-element -- a generated data: URL, nothing to optimise
            <img src={img} alt="KHQR payment code" width={240} height={240} className="mx-auto my-3 rounded-lg bg-white p-2" />
          ) : (
            <div className="mx-auto my-3 size-60 animate-pulse rounded-lg bg-muted" />
          )}
          <p className="tabular text-sm">
            Expires in {Math.floor(secs / 60)}:{String(secs % 60).padStart(2, "0")}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">This page updates by itself once the bank confirms the payment.</p>
        </>
      )}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </section>
  )
}
