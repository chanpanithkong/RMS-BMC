"use client"

import * as React from "react"
import Link from "next/link"
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

export default function CustomerSignupPage() {
  const router = useRouter()
  const [phone, setPhone] = React.useState("")
  const [error, setError] = React.useState("")
  return (
    <Card>
      <CardHeader>
        <CardTitle>Create a customer account</CardTitle>
        <CardDescription>
          Track your online orders and reorder faster. Staff accounts are
          created by an administrator.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (!/^(\+855|0)[\d ]{7,12}$/.test(phone))
              return setError(
                "Enter a Cambodian phone number starting with 0 or +855."
              )
            toast.success("Account created")
            router.push("/online")
          }}
        >
          <FormRow label="Name" required htmlFor="n">
            <Input id="n" required autoComplete="name" />
          </FormRow>
          <FormRow label="Phone" required htmlFor="p" error={error}>
            <Input
              id="p"
              type="tel"
              autoComplete="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              aria-invalid={!!error || undefined}
            />
          </FormRow>
          <FormRow label="Email" htmlFor="e">
            <Input id="e" type="email" autoComplete="email" />
          </FormRow>
          <FormRow label="Password" required htmlFor="w">
            <Input
              id="w"
              type="password"
              required
              minLength={10}
              autoComplete="new-password"
            />
          </FormRow>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" required className="mt-1" />I agree to my
            details being stored to manage my orders.
          </label>
          <Button type="submit" className="h-10">
            Create account
          </Button>
          <Link
            href="/online"
            className="text-center text-sm underline-offset-4 hover:underline"
          >
            Continue as guest
          </Link>
        </form>
      </CardContent>
    </Card>
  )
}
