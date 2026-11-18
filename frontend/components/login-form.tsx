"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { safeNext, signIn, signInMessage } from "@/lib/api/session"

export function LoginForm() {
  const router = useRouter()
  const next = safeNext(useSearchParams().get("next"))
  const [username, setUsername] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return setError("Enter your username and password.")
    setError("")
    setBusy(true)
    try {
      // The backend counts failed attempts and locks the account (5 in 15 minutes).
      const me = await signIn(username.trim(), password)
      router.replace(me.must_change_password ? "/change-password" : next)
    } catch (err) {
      setError(signInMessage(err))
      setPassword("")
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>
          Use your staff account. Shared terminals can use a PIN instead.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit}>
          <FieldGroup>
            <Field data-invalid={!!error || undefined}>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field data-invalid={!!error || undefined}>
              <div className="flex items-center">
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <Link
                  href="/forgot-password"
                  className="ml-auto text-sm underline-offset-4 hover:underline"
                >
                  Forgot password?
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              {error && <FieldError role="alert">{error}</FieldError>}
            </Field>
            <Field>
              <Button type="submit" disabled={busy} className="h-10">
                {busy ? "Signing in…" : "Sign in"}
              </Button>
              <Link
                href="/lock"
                className="text-center text-sm underline-offset-4 hover:underline"
              >
                Use PIN on shared terminal
              </Link>
              <FieldDescription className="text-center">
                Staff accounts are created by your administrator.
              </FieldDescription>
            </Field>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  )
}
