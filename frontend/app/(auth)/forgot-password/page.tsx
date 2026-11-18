"use client"

import * as React from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { FormRow, Notice } from "@/components/rms/kit"
import { api } from "@/lib/api/client"

export default function ForgotPasswordPage() {
  const [sent, setSent] = React.useState(false)
  const [who, setWho] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Reset password</CardTitle>
        <CardDescription>
          We&apos;ll email a reset link if the account exists and has an email address.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {sent ? (
          <Notice tone="success">If the account exists, a reset link has been sent. Check your email; the link works once.</Notice>
        ) : (
          <form
            className="grid gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              setBusy(true)
              // The answer is the same whether or not the account exists (no account enumeration).
              void api("POST", "/auth/password/forgot", { body: { email_or_username: who.trim() } })
                .catch(() => undefined)
                .finally(() => {
                  setBusy(false)
                  setSent(true)
                })
            }}
          >
            <FormRow label="Email or username" required htmlFor="em">
              <Input id="em" required autoComplete="username" value={who} onChange={(e) => setWho(e.target.value)} />
            </FormRow>
            <Button type="submit" className="h-10" disabled={busy}>
              {busy ? "Sending…" : "Send reset link"}
            </Button>
          </form>
        )}
        <Link
          href="/login"
          className="text-center text-sm underline-offset-4 hover:underline"
        >
          Back to sign in
        </Link>
      </CardContent>
    </Card>
  )
}
