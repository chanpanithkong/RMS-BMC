"use client"

import { usePathname } from "next/navigation"
import { ShieldAlert } from "lucide-react"
import { LinkButton } from "@/components/rms/kit"
import { navForPath, roleLabels } from "@/lib/rms/nav"
import { useRms } from "@/lib/rms/store"

/** UI-level gate only: the SRS requires the backend to enforce permissions on every request. */
export function RoleGate({ children }: { children: React.ReactNode }) {
  const path = usePathname()
  const { role, roles } = useRms()
  const nav = navForPath(path)
  if (nav && !nav.roles.some((r) => roles.includes(r))) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-10 text-center">
        <ShieldAlert className="size-8 text-muted-foreground" aria-hidden />
        <h1 className="text-lg font-semibold">
          You don&apos;t have access to {nav.en}
        </h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          The {roleLabels[role]} role can&apos;t open this section. Ask an
          administrator if you need it.
        </p>
        <LinkButton href="/notifications" variant="outline" className="mt-2">
          Go to notifications
        </LinkButton>
      </div>
    )
  }
  return <>{children}</>
}
