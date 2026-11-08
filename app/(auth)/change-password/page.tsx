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

export default function ChangePasswordPage() {
  const router = useRouter()
  const [next, setNext] = React.useState("")
  const [again, setAgain] = React.useState("")
  const [errors, setErrors] = React.useState<{ next?: string; again?: string }>(
    {}
  )
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const out: typeof errors = {}
    if (next.length < 10) out.next = "Use at least 10 characters."
    if (next !== again) out.again = "Passwords don't match."
    setErrors(out)
    if (Object.keys(out).length) return
    toast.success("Password changed")
    router.push("/")
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
        <form className="grid gap-3" onSubmit={submit}>
          <FormRow label="Current password" required htmlFor="c">
            <Input
              id="c"
              type="password"
              required
              autoComplete="current-password"
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
          <Button type="submit" className="h-10">
            Update password
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
