"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
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

const MAX_ATTEMPTS = 5

export function LoginForm() {
  const router = useRouter()
  const [username, setUsername] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [error, setError] = React.useState("")
  const [attempts, setAttempts] = React.useState(0)
  const [busy, setBusy] = React.useState(false)
  const locked = attempts >= MAX_ATTEMPTS

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (locked) return
    if (!username.trim() || !password) {
      setAttempts((a) => a + 1)
      return setError("Enter your username and password.")
    }
    setError("")
    setBusy(true)
    // Demo only: real sign-in must call the authentication API.
    setTimeout(() => router.push("/"), 300)
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
              {error && <FieldError>{error}</FieldError>}
            </Field>
            {locked && (
              <p role="alert" className="text-sm text-danger">
                Account locked after {MAX_ATTEMPTS} failed attempts. Ask an
                administrator to unlock it.
              </p>
            )}
            <Field>
              <Button type="submit" disabled={busy || locked} className="h-10">
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
