"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { FormRow } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { reloadMe } from "@/lib/api/session"
import { apiMessage } from "@/lib/api/use-api"

export default function ChangePasswordPage() {
  const router = useRouter()
  const [current, setCurrent] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [formError, setFormError] = React.useState("")
  const [next, setNext] = React.useState("")
  const [again, setAgain] = React.useState("")
  const [errors, setErrors] = React.useState<{ next?: string; again?: string }>(
    {}
  )
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const out: typeof errors = {}
    if (next.length < 10) out.next = "Use at least 10 characters."
    if (next !== again) out.again = "Passwords don't match."
    setErrors(out)
    if (Object.keys(out).length) return
    setBusy(true)
    setFormError("")
    try {
      await api("POST", "/auth/password/change", { body: { current_password: current, new_password: next } })
      await reloadMe() // reloads /auth/me so the "must change password" flag clears
      toast.success("Password changed")
      router.replace("/")
    } catch (err) {
      setFormError(apiMessage(err))
      setBusy(false)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Change password</CardTitle>
        <CardDescription>
          Required after a temporary password is issued.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-3" onSubmit={(e) => void submit(e)}>
          <FormRow label="Current password" required htmlFor="c">
            <Input
              id="c"
              type="password"
              required
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </FormRow>
          <FormRow
            label="New password"
            required
            htmlFor="n"
            error={errors.next}
            hint="At least 10 characters, and not your username."
          >
            <Input
              id="n"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              aria-invalid={!!errors.next || undefined}
            />
          </FormRow>
          <FormRow
            label="Confirm new password"
            required
            htmlFor="a"
            error={errors.again}
          >
            <Input
              id="a"
              type="password"
              autoComplete="new-password"
              value={again}
              onChange={(e) => setAgain(e.target.value)}
              aria-invalid={!!errors.again || undefined}
            />
          </FormRow>
          {formError && (
            <p role="alert" className="text-sm text-danger">
              {formError}
            </p>
          )}
          <Button type="submit" className="h-10" disabled={busy}>
            {busy ? "Updating…" : "Update password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
