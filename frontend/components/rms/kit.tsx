"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleDashed,
  Clock3,
  Delete,
  Info,
  Minus,
  Plus,
  type LucideIcon,
} from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Label } from "@/components/ui/label"
import { khr, toKhr, usd } from "@/lib/rms/billing"
import { cn } from "@/lib/utils"

export type Tone = "success" | "warning" | "info" | "danger" | "neutral"

const toneOf: Record<string, Tone> = {}
const assign = (tone: Tone, ...labels: string[]) =>
  labels.forEach((l) => (toneOf[l] = tone))
assign(
  "success",
  "Completed",
  "Paid",
  "Active",
  "Available",
  "Approved",
  "Ready",
  "Confirmed",
  "Delivered",
  "Received",
  "Posted",
  "Closed",
  "Served",
  "Collected",
  "Online",
  "Matched",
  "Enabled",
  "Success",
  "In Stock",
  "Settled",
  "Seated",
  "Accepted",
  "Published"
)
assign(
  "warning",
  "Pending",
  "Submitted",
  "Partially Paid",
  "Partially Received",
  "Requested",
  "Pending Approval",
  "Low",
  "Awaiting Payment",
  "Notified",
  "Waiting",
  "Pending Assignment",
  "Expiring",
  "Draft Change",
  "Held",
  "In Transit",
  "Difference",
  "Unmapped",
  "Unverified",
  "Locked",
  "Counting"
)
assign(
  "info",
  "Open",
  "Sent",
  "In Preparation",
  "In Progress",
  "Ordering",
  "Assigned",
  "Out for Delivery",
  "Sent to Supplier",
  "Reserved",
  "Dine-in",
  "Scheduled",
  "Partially Refunded"
)
assign(
  "danger",
  "Cancelled",
  "Rejected",
  "Failed",
  "No-show",
  "Out of Service",
  "Unpaid",
  "Negative",
  "Reversed",
  "Voided",
  "Force Closed",
  "Inactive",
  "Offline",
  "Refunded",
  "Left",
  "Revoked",
  "Critical",
  "Expired"
)

const toneClass: Record<Tone, string> = {
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  info: "bg-info-soft text-info",
  danger: "bg-danger-soft text-danger",
  neutral: "bg-muted text-muted-foreground",
}
const toneIcon: Record<Tone, LucideIcon> = {
  success: CheckCircle2,
  warning: Clock3,
  info: Info,
  danger: Ban,
  neutral: CircleDashed,
}

export function StatusBadge({
  status,
  tone,
  className,
}: {
  status: string
  tone?: Tone
  className?: string
}) {
  const t = tone ?? toneOf[status] ?? "neutral"
  const Icon = toneIcon[t]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap",
        toneClass[t],
        className
      )}
    >
      <Icon className="size-3" aria-hidden />
      {status}
    </span>
  )
}

export function MoneyText({
  value,
  dual,
  className,
}: {
  value: number
  dual?: boolean
  className?: string
}) {
  return (
    <span className={cn("tabular", className)}>
      {usd(value)}
      {dual && (
        <span className="ml-1.5 text-xs text-muted-foreground">
          {khr(toKhr(value))}
        </span>
      )}
    </span>
  )
}

export function LinkButton({
  href,
  variant,
  size,
  className,
  children,
  "aria-label": ariaLabel,
}: {
  href: string
  className?: string
  children: React.ReactNode
  "aria-label"?: string
} & Parameters<typeof buttonVariants>[0]) {
  return (
    <Link
      href={href}
      aria-label={ariaLabel}
      className={cn(buttonVariants({ variant, size }), className)}
    >
      {children}
    </Link>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="mt-0.5 max-w-3xl text-sm text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      )}
    </div>
  )
}

export const Page = ({ children }: { children: React.ReactNode }) => (
  <main className="flex flex-1 flex-col gap-4 p-4 lg:p-6">{children}</main>
)

export function Stat({
  label,
  value,
  hint,
  icon: Icon,
  href,
  tone,
}: {
  label: string
  value: React.ReactNode
  hint?: React.ReactNode
  icon?: LucideIcon
  href?: string
  tone?: Tone
}) {
  const body = (
    <Card
      size="sm"
      className={cn("h-full", href && "transition-colors hover:bg-accent/40")}
    >
      <CardContent>
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {Icon && (
            <Icon
              className={cn(
                "size-4 text-muted-foreground",
                tone === "danger" && "text-danger",
                tone === "warning" && "text-warning",
                tone === "success" && "text-success"
              )}
              aria-hidden
            />
          )}
        </div>
        <p className="tabular mt-1 text-2xl font-semibold tracking-tight">
          {value}
        </p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
  return href ? (
    <Link
      href={href}
      className="block rounded-xl focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      {body}
    </Link>
  ) : (
    body
  )
}

export function Panel({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string
  description?: string
  actions?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>{title}</CardTitle>
          {description && (
            <CardDescription className="mt-0.5">{description}</CardDescription>
          )}
        </div>
        {actions}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export interface Option {
  value: string
  label: string
}
export const opts = (...values: string[]): Option[] =>
  values.map((v) => ({ value: v, label: v }))

export function SimpleSelect({
  value,
  onChange,
  options,
  placeholder,
  className,
  id,
  "aria-label": ariaLabel,
  invalid,
  size,
}: {
  value: string
  onChange: (v: string) => void
  options: Option[]
  placeholder?: string
  className?: string
  id?: string
  "aria-label"?: string
  invalid?: boolean
  size?: "sm" | "default"
}) {
  return (
    <Select
      value={value}
      onValueChange={(v) => onChange(String(v ?? ""))}
      items={options}
    >
      <SelectTrigger
        id={id}
        aria-label={ariaLabel}
        aria-invalid={invalid || undefined}
        size={size}
        className={cn("w-full", className)}
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function FormRow({
  label,
  required,
  error,
  children,
  htmlFor,
  hint,
}: {
  label: string
  required?: boolean
  error?: string
  children: React.ReactNode
  htmlFor?: string
  hint?: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={htmlFor}>
        {label}
        {required && (
          <span className="text-danger" aria-hidden>
            {" "}
            *
          </span>
        )}
      </Label>
      {children}
      {hint && !error && (
        <p className="text-xs text-muted-foreground">{hint}</p>
      )}
      {error && (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

export function QuantityStepper({
  value,
  onChange,
  min = 0,
  size = "default",
  label = "quantity",
}: {
  value: number
  onChange: (n: number) => void
  min?: number
  size?: "default" | "lg"
  label?: string
}) {
  const btn = size === "lg" ? "size-11" : "size-9"
  return (
    <div className="inline-flex items-center gap-1">
      <Button
        variant="outline"
        className={btn}
        aria-label={`Decrease ${label}`}
        onClick={() => onChange(Math.max(value - 1, min))}
      >
        <Minus />
      </Button>
      <span className="tabular w-8 text-center font-semibold">{value}</span>
      <Button
        variant="outline"
        className={btn}
        aria-label={`Increase ${label}`}
        onClick={() => onChange(value + 1)}
      >
        <Plus />
      </Button>
    </div>
  )
}

export function Keypad({
  value,
  onChange,
  decimals = true,
}: {
  value: string
  onChange: (v: string) => void
  decimals?: boolean
}) {
  const press = (k: string) => {
    if (k === "back") return onChange(value.slice(0, -1))
    if (k === "." && (value.includes(".") || !decimals)) return
    onChange(value === "0" && k !== "." ? k : value + k)
  }
  return (
    <div className="grid grid-cols-3 gap-2">
      {[
        "7",
        "8",
        "9",
        "4",
        "5",
        "6",
        "1",
        "2",
        "3",
        decimals ? "." : "00",
        "0",
        "back",
      ].map((k) => (
        <Button
          key={k}
          variant="outline"
          className="h-12 text-lg font-medium"
          aria-label={k === "back" ? "Backspace" : k}
          onClick={() => press(k === "00" ? "0" : k)}
        >
          {k === "back" ? <Delete className="size-5" /> : k}
        </Button>
      ))}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed p-8 text-center">
      <p className="font-medium">{title}</p>
      {description && (
        <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function Notice({
  tone = "warning",
  children,
  className,
}: {
  tone?: Tone
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-lg px-3 py-2 text-sm",
        toneClass[tone],
        className
      )}
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  )
}

export function KV({
  items,
  className,
}: {
  items: [string, React.ReactNode][]
  className?: string
}) {
  return (
    <dl
      className={cn(
        "grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm",
        className
      )}
    >
      {items.map(([k, v]) => (
        <React.Fragment key={k}>
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="text-right font-medium">{v}</dd>
        </React.Fragment>
      ))}
    </dl>
  )
}

/** Tabs whose selection lives in the URL (?tab=), so every tab can be linked to. */
export function useTab(fallback: string) {
  const params = useSearchParams()
  const router = useRouter()
  const path = usePathname()
  const tab = params.get("tab") ?? fallback
  const setTab = React.useCallback(
    (t: string) => {
      const next = new URLSearchParams(window.location.search)
      next.set("tab", t)
      router.replace(`${path}?${next.toString()}`, { scroll: false })
    },
    [path, router]
  )
  return [tab, setTab] as const
}

export function PageTabs({
  tabs,
  value,
  onChange,
  children,
}: {
  tabs: { value: string; label: string; count?: number }[]
  value: string
  onChange: (v: string) => void
  children?: React.ReactNode
}) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(String(v))}>
      <div className="-mx-1 overflow-x-auto px-1 pb-1">
        <TabsList>
          {tabs.map((t) => (
            <TabsTrigger key={t.value} value={t.value} className="px-2.5">
              {t.label}
              {t.count !== undefined && (
                <span className="tabular rounded bg-muted-foreground/15 px-1 text-xs">
                  {t.count}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </div>
      {children}
    </Tabs>
  )
}

export function DateRangeFilter({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  return (
    <SimpleSelect
      aria-label="Date range"
      className="w-36"
      value={value}
      onChange={onChange}
      options={opts("Today", "Yesterday", "This week", "This month", "Custom")}
    />
  )
}
