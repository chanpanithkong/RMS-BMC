import { Suspense } from "react"
import { AuthGate } from "@/components/rms/auth-gate"
import { RoleGate } from "@/components/rms/role-gate"

export default function FullscreenLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AuthGate>
      <Suspense>
        <RoleGate>{children}</RoleGate>
      </Suspense>
    </AuthGate>
  )
}
