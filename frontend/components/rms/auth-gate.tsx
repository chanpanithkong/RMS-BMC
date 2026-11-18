"use client"

import * as React from "react"
import { usePathname, useRouter } from "next/navigation"
import { Skeleton } from "@/components/ui/skeleton"
import { restoreSession, useSession } from "@/lib/api/session"

/**
 * Staff screens need a signed-in user. On first load the session is restored from the refresh cookie;
 * without one the user goes to the sign-in page and comes back here afterwards.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { status, me } = useSession()
  const router = useRouter()
  const path = usePathname()

  React.useEffect(() => {
    void restoreSession()
  }, [])

  React.useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(path)}`)
    else if (status === "authenticated" && me?.must_change_password && path !== "/change-password") router.replace("/change-password")
  }, [status, me, path, router])

  if (status !== "authenticated") {
    return (
      <div className="grid gap-4 p-6" aria-busy="true" aria-label="Loading your session">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }
  return <>{children}</>
}
