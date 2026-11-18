"use client"

import { loadCurrent } from "@/lib/api/cash"
import { markAllRead, markRead, useNotificationSync } from "@/lib/api/notifications"
import * as React from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import {
  Bell,
  CalendarDays,
  CircleUser,
  KeyRound,
  Languages,
  LogOut,
  Moon,
  Search,
  Sun,
  UserCog,
  Wallet,
} from "lucide-react"
import { useTheme } from "next-themes"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { SimpleSelect } from "@/components/rms/kit"
import { navForPath, roleLabels } from "@/lib/rms/nav"
import { signOut, switchBranch, useSession } from "@/lib/api/session"
import { initials, rms, useRms } from "@/lib/rms/store"
import { cn } from "@/lib/utils"

export function NotificationBell() {
  const { notices } = useRms()
  const unread = notices.filter((n) => !n.read)
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="relative"
            aria-label={`Notifications, ${unread.length} unread`}
          />
        }
      >
        <Bell />
        {unread.length > 0 && (
          <span className="tabular absolute -top-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
            {unread.length}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b p-3">
          <p className="font-medium">Notifications</p>
          <Button variant="ghost" size="xs" onClick={() => void markAllRead()}>
            Mark all read
          </Button>
        </div>
        <ul className="max-h-80 overflow-y-auto">
          {notices.length === 0 && <li className="p-3 text-sm text-muted-foreground">No notifications.</li>}
          {notices.slice(0, 6).map((n) => (
            <li key={n.id} className="border-b last:border-0">
              <Link
                href={n.href}
                onClick={() => void markRead(n.id)}
                className={cn(
                  "block p-3 text-sm hover:bg-muted",
                  !n.read && "bg-accent/40"
                )}
              >
                <span className="flex justify-between gap-2 font-medium">
                  {n.title}
                  <span className="tabular text-xs font-normal text-muted-foreground">
                    {n.at}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">{n.body}</span>
              </Link>
            </li>
          ))}
        </ul>
        <Link
          href="/notifications"
          className="block p-2 text-center text-sm text-primary hover:underline"
        >
          Open notification centre
        </Link>
      </PopoverContent>
    </Popover>
  )
}

export function UserMenu() {
  const { role, userName, lang } = useRms()
  const { me } = useSession()
  const router = useRouter()
  const { resolvedTheme, setTheme } = useTheme()
  const branches = me?.branches ?? []
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            className="h-9 gap-2 px-1.5"
            aria-label="User menu"
          />
        }
      >
        <Avatar className="size-7">
          <AvatarFallback>{initials(userName)}</AvatarFallback>
        </Avatar>
        <span className="hidden text-left leading-tight xl:block">
          <span className="block text-xs font-medium">{userName}</span>
          <span className="block text-[11px] text-muted-foreground">
            {roleLabels[role]}
          </span>
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuGroup>
          <DropdownMenuLabel>{userName}</DropdownMenuLabel>
          <DropdownMenuItem render={<Link href="/profile" />}>
            <CircleUser />
            Profile
          </DropdownMenuItem>
          <DropdownMenuItem render={<Link href="/lock" />}>
            <KeyRound />
            Change PIN / lock
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() =>
              setTheme(resolvedTheme === "dark" ? "light" : "dark")
            }
          >
            {resolvedTheme === "dark" ? <Sun /> : <Moon />}Switch theme
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => rms.setLang(lang === "en" ? "km" : "en")}
          >
            <Languages />
            {lang === "en" ? "ខ្មែរ" : "English"}
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        {branches.length > 1 && (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              <UserCog />
              Switch branch
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent className="max-h-80 w-52 overflow-y-auto">
              <DropdownMenuGroup>
                <DropdownMenuRadioGroup
                  value={me?.current_branch.id}
                  onValueChange={(v) => void switchBranch(String(v))}
                >
                  {branches.map((b) => (
                    <DropdownMenuRadioItem key={b.id} value={b.id}>
                      {b.name_en}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuGroup>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onClick={async () => {
            await signOut()
            router.replace("/login")
          }}
        >
          <LogOut />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function AppHeader() {
  const { lang, sessions, userName } = useRms()
  const { me } = useSession()
  const path = usePathname()
  const router = useRouter()
  const [q, setQ] = React.useState("")
  const nav = navForPath(path)
  const session = sessions.find((s) => s.status === "Open" && s.mine)
  useNotificationSync()
  const myId = me?.id
  // Keep the cashier-session indicator current as the user moves between pages.
  React.useEffect(() => {
    if (myId) loadCurrent(myId).catch(() => undefined)
  }, [myId, path])
  const title = nav ? (lang === "km" ? nav.km : nav.en) : "Profile"
  const crumbs = path.split("/").filter(Boolean).slice(1)

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-3 backdrop-blur">
      <SidebarTrigger className="-ml-1" />
      <Separator
        orientation="vertical"
        className="mr-1 data-vertical:h-4 data-vertical:self-auto"
      />
      <nav
        aria-label="Breadcrumb"
        className="hidden min-w-0 items-center gap-1 truncate text-sm md:flex"
      >
        {nav && crumbs.length > 0 ? (
          <Link
            href={nav.href}
            className="text-muted-foreground hover:text-foreground"
          >
            {title}
          </Link>
        ) : (
          <span className="font-medium">{title}</span>
        )}
        {crumbs.map((c) => (
          <span key={c} className="truncate font-medium">
            <span className="mx-1 text-muted-foreground">/</span>
            {decodeURIComponent(c)}
          </span>
        ))}
      </nav>
      <form
        className="relative ml-auto hidden w-52 lg:block xl:w-72"
        role="search"
        onSubmit={(e) => {
          e.preventDefault()
          if (q.trim()) router.push(`/orders?q=${encodeURIComponent(q.trim())}`)
        }}
      >
        <Search
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          aria-label="Search orders, tables and customers"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Order no, table, phone…"
          className="pl-8"
        />
      </form>
      <div className="ml-auto flex items-center gap-1 lg:ml-1">
        {me && me.branches.length > 1 ? (
          <SimpleSelect
            aria-label="Branch"
            className="hidden w-32 sm:flex"
            value={me.current_branch.id}
            onChange={(v) => void switchBranch(v)}
            options={me.branches.map((b) => ({ value: b.id, label: b.name_en }))}
          />
        ) : (
          <span className="hidden px-2 text-xs text-muted-foreground sm:block">
            {me?.current_branch.name_en}
          </span>
        )}
        <span
          className="tabular hidden items-center gap-1 px-2 text-xs text-muted-foreground xl:flex"
          title="Business date"
        >
          <CalendarDays className="size-3.5" />
          {me?.business_date}
        </span>
        <Link
          href="/shifts"
          className="hidden items-center gap-1 rounded-md px-2 py-1 text-xs hover:bg-muted md:flex"
          title={
            session ? `Cashier session open (${session.cashier})` : "No open cashier session"
          }
        >
          <Wallet
            className={cn("size-3.5", session ? "text-success" : "text-danger")}
          />
          {session
            ? `Session open · ${session.cashier === userName ? "you" : session.cashier.split(" ")[0]}`
            : "No session"}
        </Link>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => rms.setLang(lang === "en" ? "km" : "en")}
          aria-label="Switch language"
        >
          {lang === "en" ? "ខ្មែរ" : "EN"}
        </Button>
        <NotificationBell />
        <UserMenu />
      </div>
    </header>
  )
}
