import { Suspense } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import { AppHeader } from "@/components/rms/app-header"
import { RoleGate } from "@/components/rms/role-gate"
import { Skeleton } from "@/components/ui/skeleton"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

export default function BackOfficeLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <AppHeader />
        <Suspense
          fallback={
            <div className="grid gap-4 p-6">
              <Skeleton className="h-8 w-56" />
              <Skeleton className="h-64 w-full" />
            </div>
          }
        >
          <RoleGate>{children}</RoleGate>
        </Suspense>
      </SidebarInset>
    </SidebarProvider>
  )
}
