"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { FormRow, Keypad } from "@/components/rms/kit"
import { pinSignIn, signInMessage } from "@/lib/api/session"

/**
 * The device token identifies this shared terminal. It is issued once under Branches → Devices and kept on the
 * device (it is not a user credential; the backend also needs the person's username and PIN, and can revoke it).
 */
const KEY = "rms.device_token"
const readToken = () => {
  try {
    return localStorage.getItem(KEY) ?? ""
  } catch {
    return ""
  }
}

export default function LockScreenPage() {
  const router = useRouter()
  // localStorage isn't available during server rendering, so read it as an external store (null on the server).
  const stored = React.useSyncExternalStore(
    () => () => undefined,
    readToken,
    () => null
  )
  const [changed, setDevice] = React.useState<string | null>(null)
  const device = changed ?? stored
  const [draft, setDraft] = React.useState("")
  const [username, setUsername] = React.useState("")
  const [pin, setPin] = React.useState("")
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  const unlock = async () => {
    if (!username.trim()) return setError("Enter your username.")
    if (pin.length < 4) return setError("Enter your 4–6 digit PIN.")
    setBusy(true)
    try {
      await pinSignIn(device!, username.trim(), pin)
      router.replace("/pos")
    } catch (e) {
      setError(signInMessage(e))
      setPin("")
      setBusy(false)
    }
  }

  if (device === null) return null
  if (!device)
    return (
      <Card>
        <CardHeader className="text-center">
          <CardTitle>Register this terminal</CardTitle>
          <CardDescription>PIN sign-in works only on registered devices. A manager registers the device under Branches → Devices and enters the token here once.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <FormRow label="Device token" htmlFor="dt">
            <Input id="dt" autoComplete="off" value={draft} onChange={(e) => setDraft(e.target.value)} />
          </FormRow>
          <Button
            className="h-11"
            disabled={draft.trim().length < 10}
            onClick={() => {
              try {
                localStorage.setItem(KEY, draft.trim())
              } catch {
                return setError("This browser doesn't allow saving the device token.")
              }
              setDevice(draft.trim())
            }}
          >
            Save
          </Button>
          {error && (
            <p role="alert" className="text-center text-sm text-danger">
              {error}
            </p>
          )}
          <Link href="/login" className="text-center text-sm underline-offset-4 hover:underline">
            Sign in with password
          </Link>
        </CardContent>
      </Card>
    )

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle>Enter PIN</CardTitle>
        <CardDescription>Switch user on this terminal</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <FormRow label="Username" htmlFor="u">
          <Input id="u" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        </FormRow>
        <div className="flex h-10 items-center justify-center gap-2" aria-live="polite" aria-label={`${pin.length} digits entered`}>
          {Array.from({ length: 6 }, (_, i) => (
            <span key={i} className={`size-3 rounded-full border ${i < pin.length ? "bg-primary" : ""}`} />
          ))}
        </div>
        {error && (
          <p role="alert" className="text-center text-sm text-danger">
            {error}
          </p>
        )}
        <Keypad
          value={pin}
          onChange={(v) => {
            setPin(v.slice(0, 6))
            setError("")
          }}
          decimals={false}
        />
        <Button className="h-12" disabled={busy} onClick={() => void unlock()}>
          {busy ? "Checking…" : "Unlock"}
        </Button>
        <div className="flex justify-between text-sm">
          <Link href="/login" className="underline-offset-4 hover:underline">
            Sign in with password
          </Link>
          <button
            className="text-muted-foreground underline-offset-4 hover:underline"
            onClick={() => {
              try {
                localStorage.removeItem(KEY)
              } catch {
                /* nothing stored */
              }
              setDevice("")
            }}
          >
            Forget this device
          </button>
        </div>
      </CardContent>
    </Card>
  )
}
