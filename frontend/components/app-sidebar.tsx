"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { UtensilsCrossed } from "lucide-react"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"
import { navForPath, navGroups, roleLabels } from "@/lib/rms/nav"
import { useRms } from "@/lib/rms/store"

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname()
  const { role, lang, notices, branch } = useRms()
  const active = navForPath(pathname)?.key
  const unread = notices.filter((n) => !n.read).length

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              render={<Link href="/" />}
              tooltip="Restaurant Management System"
            >
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <UtensilsCrossed className="size-4" />
              </div>
              <div className="flex flex-col gap-0.5 leading-none">
                <span className="font-semibold">RMS Demo Restaurant</span>
                <span className="text-xs text-muted-foreground">
                  {branch} branch
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        {navGroups.map((g) => {
          const items = g.items.filter((i) => i.roles.includes(role))
          if (!items.length) return null
          return (
            <SidebarGroup key={g.en}>
              <SidebarGroupLabel>
                {lang === "km" ? g.km : g.en}
              </SidebarGroupLabel>
              <SidebarMenu>
                {items.map((item) => {
                  const label = lang === "km" ? item.km : item.en
                  return (
                    <SidebarMenuItem key={item.key}>
                      <SidebarMenuButton
                        isActive={active === item.key}
                        tooltip={label}
                        render={<Link href={item.href} />}
                      >
                        <item.icon />
                        <span>{label}</span>
                      </SidebarMenuButton>
                      {item.key === "notifications" && unread > 0 && (
                        <SidebarMenuBadge className="tabular">
                          {unread}
                        </SidebarMenuBadge>
                      )}
                    </SidebarMenuItem>
                  )
                })}
              </SidebarMenu>
            </SidebarGroup>
          )
        })}
      </SidebarContent>
      <SidebarFooter>
        <p className="truncate px-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
          Signed in as {roleLabels[role]}
        </p>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
