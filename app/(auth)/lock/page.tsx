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
import { Keypad } from "@/components/rms/kit"
import { rms } from "@/lib/rms/store"

export default function LockScreenPage() {
  const router = useRouter()
  const [pin, setPin] = React.useState("")
  const [error, setError] = React.useState("")
  const unlock = () => {
    if (pin.length < 4) return setError("Enter your 4–6 digit PIN.")
    // Demo only: a real PIN is verified by the API and maps to that user.
    rms.setUser("Lina Chhay", "CASHIER")
    router.push("/pos")
  }
  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle>Enter PIN</CardTitle>
        <CardDescription>Switch user on this terminal</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div
          className="flex h-10 items-center justify-center gap-2"
          aria-live="polite"
          aria-label={`${pin.length} digits entered`}
        >
          {Array.from({ length: 6 }, (_, i) => (
            <span
              key={i}
              className={`size-3 rounded-full border ${i < pin.length ? "bg-primary" : ""}`}
            />
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
        <Button className="h-12" onClick={unlock}>
          Unlock
        </Button>
        <Link
          href="/login"
          className="text-center text-sm underline-offset-4 hover:underline"
        >
          Sign in with password
        </Link>
      </CardContent>
    </Card>
  )
}
