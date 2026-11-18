"use client"

import * as React from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { FormRow, Notice } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { apiMessage } from "@/lib/api/use-api"

/** Target of the reset email: /reset-password?token=… (the token works once and expires). */
function ResetForm() {
  const token = useSearchParams().get("token") ?? ""
  const [next, setNext] = React.useState("")
  const [again, setAgain] = React.useState("")
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [done, setDone] = React.useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (next.length < 10) return setError("Use at least 10 characters.")
    if (next !== again) return setError("Passwords don't match.")
    setBusy(true)
    setError("")
    try {
      await api("POST", "/auth/password/reset", { body: { token, new_password: next } })
      setDone(true)
    } catch (err) {
      setError(apiMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Choose a new password</CardTitle>
        <CardDescription>At least 10 characters, and not your username.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {!token ? (
          <Notice tone="danger">This link is incomplete. Ask for a new reset link.</Notice>
        ) : done ? (
          <Notice tone="success">Password updated. Sign in with your new password.</Notice>
        ) : (
          <form className="grid gap-3" onSubmit={(e) => void submit(e)}>
            <FormRow label="New password" required htmlFor="n">
              <Input id="n" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
            </FormRow>
            <FormRow label="Confirm new password" required htmlFor="a">
              <Input id="a" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
            </FormRow>
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <Button type="submit" className="h-10" disabled={busy}>
              {busy ? "Saving…" : "Set password"}
            </Button>
          </form>
        )}
        <Link href={done ? "/login" : "/forgot-password"} className="text-center text-sm underline-offset-4 hover:underline">
          {done ? "Sign in" : "Ask for a new link"}
        </Link>
      </CardContent>
    </Card>
  )
}

export default function ResetPasswordPage() {
  return (
    <React.Suspense>
      <ResetForm />
    </React.Suspense>
  )
}
