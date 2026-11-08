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

export default function ForgotPasswordPage() {
  const [sent, setSent] = React.useState(false)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Reset password</CardTitle>
        <CardDescription>
          We&apos;ll email a reset link if the account exists.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {sent ? (
          <Notice tone="success">Check your email for a reset link.</Notice>
        ) : (
          <form
            className="grid gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              setSent(true)
            }}
          >
            <FormRow label="Email" required htmlFor="em">
              <Input id="em" type="email" required autoComplete="email" />
            </FormRow>
            <Button type="submit" className="h-10">
              Send reset link
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
