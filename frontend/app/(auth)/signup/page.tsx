"use client"

import * as React from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { FormRow, KV } from "@/components/rms/kit"
import { ApiError } from "@/lib/api/client"
import * as pub from "@/lib/api/public"
import { apiMessage } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

type Account = Awaited<ReturnType<typeof pub.account>>
type Orders = Awaited<ReturnType<typeof pub.myOrders>>

/**
 * Customer account for online ordering: sign in with a 6-digit code sent by text message (no password).
 * The first sign-in creates the account and needs a name. Staff accounts are separate.
 */
function CustomerAccount() {
  const code = pub.branchCode(useSearchParams().get("branch"))
  const [step, setStep] = React.useState<"phone" | "code" | "account">("phone")
  const [phone, setPhone] = React.useState("")
  const [sms, setSms] = React.useState("")
  const [name, setName] = React.useState("")
  const [needName, setNeedName] = React.useState(false)
  const [consent, setConsent] = React.useState(false)
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [me, setMe] = React.useState<Account | null>(null)
  const [orders, setOrders] = React.useState<Orders>([])

  const loadAccount = React.useCallback(async () => {
    const [a, o] = await Promise.all([pub.account(), pub.myOrders()])
    setMe(a)
    setOrders(o)
    setStep("account")
  }, [])
  // Already signed in on this tab: show the account straight away.
  React.useEffect(() => {
    if (!pub.customerToken()) return
    Promise.all([pub.account(), pub.myOrders()]).then(
      ([a, o]) => {
        setMe(a)
        setOrders(o)
        setStep("account")
      },
      () => pub.setCustomerToken(null)
    )
  }, [])

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError("")
    try {
      await fn()
    } catch (e) {
      if (e instanceof ApiError && e.code === "NAME_REQUIRED") {
        setNeedName(true)
        setError("Welcome! Tell us your name to create your account.")
      } else setError(apiMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{step === "account" ? `Hello, ${me?.name ?? ""}` : "Your account"}</CardTitle>
        <CardDescription>
          {step === "account" ? "Your details and recent orders." : "Sign in with your phone number. We text you a 6-digit code. Staff accounts are created by an administrator."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {!code && step !== "account" && <p className="text-sm text-muted-foreground">Open this page from the restaurant&apos;s ordering link.</p>}
        {step === "phone" && code && (
          <form
            className="grid gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              if (!/^(\+855|0)[\d ]{7,12}$/.test(phone.trim())) return setError("Enter a Cambodian phone number starting with 0 or +855.")
              void run(async () => {
                await pub.requestCode(code, phone.trim())
                setStep("code")
              })
            }}
          >
            <FormRow label="Phone" required htmlFor="p">
              <Input id="p" type="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </FormRow>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />I agree to my details being stored to manage my orders.
            </label>
            <Button type="submit" className="h-10" disabled={busy || !consent}>
              {busy ? "Sending…" : "Text me a code"}
            </Button>
          </form>
        )}
        {step === "code" && (
          <form
            className="grid gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              void run(async () => {
                const r = await pub.verifyCode(code, phone.trim(), sms.trim(), needName ? name.trim() : undefined)
                pub.setCustomerToken(r.customer_token)
                await loadAccount()
              })
            }}
          >
            <FormRow label="6-digit code" required htmlFor="c" hint={`Sent to ${phone}`}>
              <Input id="c" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={sms} onChange={(e) => setSms(e.target.value.replace(/\D/g, ""))} />
            </FormRow>
            {needName && (
              <FormRow label="Your name" required htmlFor="n">
                <Input id="n" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
              </FormRow>
            )}
            <Button type="submit" className="h-10" disabled={busy || sms.length !== 6 || (needName && !name.trim())}>
              {busy ? "Checking…" : "Sign in"}
            </Button>
            <button type="button" className="text-sm text-muted-foreground underline-offset-4 hover:underline" onClick={() => setStep("phone")}>
              Use a different number
            </button>
          </form>
        )}
        {step === "account" && me && (
          <>
            <KV
              items={[
                ["Phone", me.phone],
                ["Email", me.email ?? "—"],
                ["Loyalty points", me.loyalty_points.toLocaleString()],
              ]}
            />
            <ul className="divide-y rounded-lg border text-sm">
              {orders.length === 0 && <li className="p-3 text-muted-foreground">No orders yet.</li>}
              {orders.slice(0, 10).map((o) => (
                <li key={o.order_no + o.business_date} className="flex justify-between gap-2 p-2">
                  <span>
                    {o.order_no} · {o.business_date}
                    <span className="block text-xs text-muted-foreground">{o.items.map((i) => `${Number(i.quantity)} × ${i.name}`).join(", ")}</span>
                  </span>
                  <span className="text-right">
                    {usd(Number(o.total))}
                    <span className="block text-xs text-muted-foreground">{o.status}</span>
                  </span>
                </li>
              ))}
            </ul>
            <Button
              variant="outline"
              onClick={() =>
                void pub.signOutCustomer().finally(() => {
                  setMe(null)
                  setStep("phone")
                })
              }
            >
              Sign out
            </Button>
          </>
        )}
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <Link href={code ? `/online?branch=${code}` : "/online"} className="text-center text-sm underline-offset-4 hover:underline">
          {step === "account" ? "Order now" : "Continue as guest"}
        </Link>
      </CardContent>
    </Card>
  )
}

export default function CustomerAccountPage() {
  return (
    <React.Suspense>
      <CustomerAccount />
    </React.Suspense>
  )
}
