import { Suspense } from "react"
import { RoleGate } from "@/components/rms/role-gate"

export default function FullscreenLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <Suspense>
      <RoleGate>{children}</RoleGate>
    </Suspense>
  )
}
