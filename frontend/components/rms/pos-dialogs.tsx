"use client"

import * as React from "react"
import { Check, Mail, Printer, QrCode, Receipt } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { requestApproval } from "@/components/rms/dialog-host"
import {
  FormRow,
  KV,
  Keypad,
  Notice,
  QuantityStepper,
  SimpleSelect,
  opts,
} from "@/components/rms/kit"
import {
  billing,
  calcBill,
  cashResult,
  khr,
  lineGross,
  round2,
  toKhr,
  usd,
} from "@/lib/rms/billing"
import { modifierGroups, useRms } from "@/lib/rms/store"
import { loadBills, pay, report, splitBills } from "@/lib/api/pos"
import { ApiError } from "@/lib/api/client"
import type {
  Discount,
  LineModifier,
  MenuItem,
  Order,
  OrderLine,
  Role,
} from "@/lib/rms/types"
import { cn } from "@/lib/utils"

const chip = (on: boolean) =>
  cn(
    "touch-target rounded-lg border px-3 py-2 text-sm font-medium transition-colors",
    on
      ? "border-primary bg-primary text-primary-foreground"
      : "bg-background hover:bg-muted"
  )

export function ModifierDialog({
  item,
  onClose,
  onConfirm,
}: {
  item: MenuItem | null
  onClose: () => void
  onConfirm: (o: {
    variant?: string
    price: number
    modifiers: LineModifier[]
    qty: number
    note?: string
    allergy?: boolean
  }) => void
}) {
  const [variant, setVariant] = React.useState<string>()
  const [picked, setPicked] = React.useState<Record<string, string[]>>({})
  const [qty, setQty] = React.useState(1)
  const [note, setNote] = React.useState("")
  const [last, setLast] = React.useState<string>()
  if (item && item.id !== last) {
    setLast(item.id)
    setVariant(item.variants?.[0].name)
    setPicked({})
    setQty(1)
    setNote("")
  }
  if (!item && last) setLast(undefined)
  if (!item) return null
  const groups = item.groups
    .map((id) => modifierGroups.find((g) => g.id === id)!)
    .filter(Boolean)
  const toggle = (gid: string, mid: string, max: number) =>
    setPicked((p) => {
      const cur = p[gid] ?? []
      if (cur.includes(mid))
        return { ...p, [gid]: cur.filter((x) => x !== mid) }
      if (max === 1) return { ...p, [gid]: [mid] }
      return cur.length >= max ? p : { ...p, [gid]: [...cur, mid] }
    })
  const ready = groups.every((g) => (picked[g.id]?.length ?? 0) >= g.min)
  const mods = groups.flatMap((g) =>
    g.modifiers
      .filter((m) => picked[g.id]?.includes(m.id))
      .map((m) => ({ id: m.id, name: m.name, delta: m.delta }))
  )
  const price =
    item.variants?.find((v) => v.name === variant)?.price ?? item.price
  const each = price + mods.reduce((s, m) => s + m.delta, 0)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {item.name}{" "}
            <span className="font-normal text-muted-foreground">{item.km}</span>
          </DialogTitle>
          <DialogDescription>
            Choose options, then add to the order.
          </DialogDescription>
        </DialogHeader>
        {item.variants && (
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium">
              Size{" "}
              <span className="text-xs font-normal text-muted-foreground">
                choose 1
              </span>
            </legend>
            <div className="flex flex-wrap gap-2">
              {item.variants.map((v) => (
                <button
                  key={v.name}
                  className={chip(variant === v.name)}
                  aria-pressed={variant === v.name}
                  onClick={() => setVariant(v.name)}
                >
                  {v.name} · {usd(v.price)}
                </button>
              ))}
            </div>
          </fieldset>
        )}
        {groups.map((g) => {
          const count = picked[g.id]?.length ?? 0
          return (
            <fieldset key={g.id}>
              <legend className="mb-1.5 flex w-full items-baseline gap-2 text-sm font-medium">
                {g.name}
                <span className="text-xs font-normal text-muted-foreground">
                  {g.min > 0
                    ? `required · choose ${g.min === g.max ? g.min : `${g.min}–${g.max}`}`
                    : `optional · up to ${g.max}`}
                </span>
                {g.min > 0 && count < g.min && (
                  <span className="ml-auto text-xs font-normal text-danger">
                    Required
                  </span>
                )}
              </legend>
              <div className="flex flex-wrap gap-2">
                {g.modifiers.map((m) => {
                  const on = picked[g.id]?.includes(m.id) ?? false
                  return (
                    <button
                      key={m.id}
                      className={chip(on)}
                      aria-pressed={on}
                      onClick={() => toggle(g.id, m.id, g.max)}
                    >
                      {m.name}
                      {m.delta > 0 && ` +${usd(m.delta)}`}
                    </button>
                  )
                })}
              </div>
            </fieldset>
          )
        })}
        <FormRow
          label="Kitchen note"
          htmlFor="m-note"
          hint="Start with “ALLERGY” to highlight it on the kitchen ticket."
        >
          <Input
            id="m-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. no onion"
          />
        </FormRow>
        <DialogFooter className="items-center sm:justify-between">
          <QuantityStepper value={qty} onChange={setQty} min={1} size="lg" />
          <Button
            className="h-11 px-5"
            disabled={!ready}
            onClick={() =>
              onConfirm({
                variant,
                price,
                modifiers: mods,
                qty,
                note: note || undefined,
                allergy: /allerg/i.test(note),
              })
            }
          >
            Add · {usd(round2(each * qty))}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const limitByRole: Partial<Record<Role, number>> = {
  CASHIER: 10,
  BAR: 10,
  SUPV: 20,
  BRMGR: 30,
  GM: 50,
  OWNER: 100,
}
const discountReasons = [
  "Regular customer",
  "Service recovery",
  "Staff meal",
  "Complimentary",
  "Promotion not applied",
  "Manager decision",
]

export function DiscountDialog({
  open,
  onClose,
  base,
  title,
  onApply,
  onRemove,
  current,
}: {
  open: boolean
  onClose: () => void
  base: number
  title: string
  onApply: (d: Discount) => void
  onRemove?: () => void
  current?: Discount
}) {
  const { role } = useRms()
  const [kind, setKind] = React.useState<"percent" | "amount">("percent")
  const [value, setValue] = React.useState("10")
  const [reason, setReason] = React.useState("")
  const [err, setErr] = React.useState("")
  const limit = limitByRole[role] ?? 0
  const n = Number(value)
  const pct = kind === "percent" ? n : base ? (n / base) * 100 : 0
  const submit = () => {
    if (!(n > 0)) return setErr("Enter a discount above zero")
    if (kind === "percent" && n > 100)
      return setErr("A percentage can't exceed 100")
    if (kind === "amount" && n > base)
      return setErr(`Can't exceed ${usd(base)}`)
    if (!reason) return setErr("Choose a reason")
    const d: Discount = { kind, value: n, reason }
    if (current && current.kind === kind && current.value === n)
      return setErr("This discount is already applied")
    if (pct > limit) {
      onClose()
      requestApproval({
        action: `Discount on ${title}`,
        amount: kind === "percent" ? `${n}%` : usd(n),
        limit: `${limit}%`,
        reason,
        onApproved: (by) => {
          onApply({ ...d, approvedBy: by })
          toast.success(`Approved by ${by}`)
        },
        onDeclined: () => toast.info("Discount not applied"),
      })
      return
    }
    onApply(d)
    onClose()
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Discount</DialogTitle>
          <DialogDescription>
            {title} · base {usd(base)} · your limit {limit}%
          </DialogDescription>
        </DialogHeader>
        <Tabs
          value={kind}
          onValueChange={(v) => setKind(v as "percent" | "amount")}
        >
          <TabsList className="w-full">
            <TabsTrigger value="percent">Percent</TabsTrigger>
            <TabsTrigger value="amount">Amount</TabsTrigger>
          </TabsList>
        </Tabs>
        <FormRow
          label={kind === "percent" ? "Percentage" : "Amount (USD)"}
          required
          htmlFor="d-v"
          error={err}
        >
          <Input
            id="d-v"
            inputMode="decimal"
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              setErr("")
            }}
          />
        </FormRow>
        <FormRow label="Reason" required>
          <SimpleSelect
            aria-label="Discount reason"
            value={reason}
            onChange={setReason}
            options={opts(...discountReasons)}
            placeholder="Select…"
          />
        </FormRow>
        <DialogFooter>
          {current && onRemove && (
            <Button
              variant="destructive"
              onClick={() => {
                onRemove()
                onClose()
              }}
            >
              Remove
            </Button>
          )}
          <Button onClick={submit}>
            {pct > limit ? "Request approval" : "Apply"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function SplitDialog({
  order,
  open,
  onClose,
}: {
  order: Order
  open: boolean
  onClose: () => void
}) {
  const lines = order.lines.filter((l) => l.status !== "Cancelled")
  const totals = calcBill(order)
  const [mode, setMode] = React.useState("items")
  const [count, setCount] = React.useState(2)
  const [assign, setAssign] = React.useState<Record<string, number>>({})

  const shareOfLine = (l: OrderLine) =>
    totals.gross ? (lineGross(l) / totals.gross) * totals.total : 0
  const bills: number[] = React.useMemo(() => {
    const out = Array.from({ length: count }, () => 0)
    if (mode === "equal") {
      const each = Math.floor((totals.total / count) * 100) / 100
      out.fill(each)
      out[count - 1] = round2(totals.total - each * (count - 1))
      return out
    }
    lines.forEach((l) => {
      const b =
        mode === "seats"
          ? Math.min((l.seat ?? 1) - 1, count - 1)
          : (assign[l.id] ?? 0)
      out[b] += shareOfLine(l)
    })
    const rounded = out.map(round2)
    rounded[count - 1] = round2(
      totals.total - rounded.slice(0, -1).reduce((s, n) => s + n, 0)
    )
    return rounded
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, count, assign, order])

  const sum = round2(bills.reduce((s, n) => s + n, 0))
  const ok = sum === totals.total && bills.every((b) => b > 0)
  const [saving, setSaving] = React.useState(false)
  const save = async (m: "single" | "equal" | "items" | "seats") => {
    setSaving(true)
    try {
      const made = await splitBills(order.id, m, count, Object.fromEntries(lines.map((l) => [l.id, assign[l.id] ?? 0])))
      toast.success(m === "single" ? "Split removed" : `Bill split into ${made.length}`)
      onClose()
    } catch (e) {
      report(e)
    } finally {
      setSaving(false)
    }
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Split bill {order.no}</DialogTitle>
          <DialogDescription>
            Amounts below are a preview. The server calculates each bill exactly, and the split is fixed once paying starts.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Tabs value={mode} onValueChange={(v) => setMode(String(v))}>
            <TabsList>
              <TabsTrigger value="items" className="px-3">
                By items
              </TabsTrigger>
              <TabsTrigger value="seats" className="px-3">
                By seats
              </TabsTrigger>
              <TabsTrigger value="equal" className="px-3">
                Equal shares
              </TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex items-center gap-2 text-sm">
            Bills{" "}
            <QuantityStepper
              value={count}
              onChange={(n) => setCount(Math.max(n, 2))}
              min={2}
              label="bills"
            />
          </div>
        </div>
        {mode !== "equal" && (
          <ul className="grid gap-1.5">
            {lines.map((l) => (
              <li
                key={l.id}
                className="flex items-center justify-between gap-2 rounded-lg border p-2 text-sm"
              >
                <span className="min-w-0 truncate">
                  {l.qty} × {l.name}
                  {mode === "seats" && (
                    <span className="text-muted-foreground">
                      {" "}
                      · seat {l.seat ?? 1}
                    </span>
                  )}
                </span>
                {mode === "items" ? (
                  <div className="flex gap-1">
                    {Array.from({ length: count }, (_, i) => (
                      <button
                        key={i}
                        aria-pressed={(assign[l.id] ?? 0) === i}
                        aria-label={`Move to bill ${i + 1}`}
                        className={cn(
                          chip((assign[l.id] ?? 0) === i),
                          "min-h-9 min-w-9 px-2 py-1"
                        )}
                        onClick={() => setAssign((a) => ({ ...a, [l.id]: i }))}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </div>
                ) : (
                  <span className="tabular">{usd(shareOfLine(l))}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {bills.map((b, i) => (
            <div key={i} className="rounded-lg bg-muted p-2">
              <p className="text-xs text-muted-foreground">Bill {i + 1}</p>
              <p className="tabular font-semibold">{usd(b)}</p>
            </div>
          ))}
        </div>
        <Notice tone={ok ? "success" : "danger"}>
          Σ {usd(sum)} of {usd(totals.total)}{" "}
          {ok ? "— balanced" : "— every bill needs an amount"}
        </Notice>
        <DialogFooter>
          {order.splits && (
            <Button variant="outline" disabled={saving} onClick={() => void save("single")}>
              Remove split
            </Button>
          )}
          <Button disabled={!ok || saving} onClick={() => void save(mode as "equal" | "items" | "seats")}>
            {saving ? "Splitting…" : "Confirm split"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const usdNotes = [5, 10, 20, 50, 100]
const khrNotes = [5000, 10000, 20000, 50000, 100000]
const methods = [
  { id: "Cash USD", cash: true, currency: "USD" as const },
  { id: "Cash KHR", cash: true, currency: "KHR" as const },
  { id: "KHQR", cash: false, currency: "USD" as const },
  { id: "Bank Transfer", cash: false, currency: "USD" as const },
  { id: "Card", cash: false, currency: "USD" as const },
]

export function PaymentDialog({
  orderId,
  open,
  onClose,
  onPaid,
}: {
  orderId: string
  open: boolean
  onClose: () => void
  onPaid?: () => void
}) {
  const { orders, sessions } = useRms()
  const order = orders.find((o) => o.id === orderId)
  const [methodId, setMethodId] = React.useState("Cash USD")
  const [tendered, setTendered] = React.useState("")
  const [ref, setRef] = React.useState("")
  const [changeCur, setChangeCur] = React.useState<"USD" | "KHR">("USD")
  const [busy, setBusy] = React.useState(false)
  const [err, setErr] = React.useState("")
  const [splitIdx, setSplitIdx] = React.useState(0)
  const [lastChange, setLastChange] = React.useState<string>()
  const [reprints, setReprints] = React.useState(0)
  // Bills (and any split) live on the server; load them whenever the dialog opens.
  React.useEffect(() => {
    if (open) loadBills(orderId).catch(() => undefined)
  }, [open, orderId])
  if (!order) return null
  const totals = calcBill(order)
  const split = order.splits?.[splitIdx]
  const balance = split ? (split.balance ?? split.total) : totals.balance
  const method = methods.find((m) => m.id === methodId)!
  const num = Number(tendered)
  const result = method.cash
    ? cashResult({
        method: "cash",
        currency: method.currency,
        tendered: num,
        balance,
        changeCurrency: changeCur,
      })
    : null
  const hasSession = sessions.some((s) => s.status === "Open" && s.mine)
  const fullyPaid = totals.balance === 0

  const submit = async (amount?: number) => {
    setErr("")
    const value = amount ?? num
    // Cashier session, amounts, rounding and change are checked by the backend (BR-021).
    if (!method.cash && !ref.trim())
      return setErr("A reference is required for this payment method.")
    if (method.cash && !(value > 0)) return setErr("Enter the amount tendered.")
    setBusy(true)
    try {
      const r = await pay(order.id, {
        method: method.id,
        currency: method.currency,
        tendered: method.cash ? value : undefined,
        changeCurrency: method.cash ? changeCur : undefined,
        reference: ref.trim() || undefined,
        billId: split?.billId,
      })
      // Move on to the next split bill that still has a balance.
      const next = r.splits?.findIndex((s) => (s.balance ?? 0) > 0)
      if (next !== undefined && next >= 0) setSplitIdx(next)
      const ch = r.change && Number(r.change.amount) > 0 ? r.change : null
      setLastChange(ch ? (ch.currency === "USD" ? usd(Number(ch.amount)) : khr(Number(ch.amount))) : undefined)
      setTendered("")
      setRef("")
      onPaid?.()
    } catch (e) {
      if (e instanceof ApiError) setErr(e.message)
      else report(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[94vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {fullyPaid
              ? `Receipt ${order.receiptNo ?? ""}`
              : `Take payment · ${order.no}`}
          </DialogTitle>
          <DialogDescription>
            Rate 1 USD = {billing.usdKhr.toLocaleString()} KHR (illustrative) ·
            cash rounding {billing.khrIncrement} riel
          </DialogDescription>
        </DialogHeader>
        {fullyPaid ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border p-4 font-mono text-xs">
              <p className="text-center font-semibold">RMS DEMO RESTAURANT</p>
              <p className="mb-2 text-center">
                Riverside · {order.receiptNo}
                {reprints > 0 && (
                  <span className="font-bold"> · COPY {reprints}</span>
                )}
              </p>
              {order.lines
                .filter((l) => l.status !== "Cancelled")
                .map((l) => (
                  <p key={l.id} className="flex justify-between gap-2">
                    <span className="truncate">
                      {l.qty} {l.name}
                    </span>
                    <span>{usd(lineGross(l))}</span>
                  </p>
                ))}
              <hr className="my-2 border-dashed" />
              <KV
                className="text-xs"
                items={[
                  ["Subtotal", usd(totals.subtotal)],
                  ["Service charge", usd(totals.service)],
                  ["Tax", usd(totals.tax)],
                  ["Total", usd(totals.total)],
                ]}
              />
              <hr className="my-2 border-dashed" />
              {order.payments.map((p) => (
                <p key={p.id} className="flex justify-between">
                  <span>{p.method}</span>
                  <span>
                    {p.currency === "USD" ? usd(p.tendered) : khr(p.tendered)}
                    {p.change > 0 &&
                      ` · chg ${p.changeCurrency === "USD" ? usd(p.change) : khr(p.change)}`}
                  </span>
                </p>
              ))}
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 rounded-lg bg-success-soft p-3 text-success">
                <Check className="size-5" />
                <div>
                  <p className="font-semibold">Paid in full</p>
                  {lastChange && (
                    <p className="text-lg font-bold">Change {lastChange}</p>
                  )}
                </div>
              </div>
              <Button
                className="h-11"
                onClick={() => toast.success("Receipt sent to printer")}
              >
                <Printer />
                Print receipt
              </Button>
              <Button
                className="h-11"
                variant="outline"
                onClick={() => {
                  setReprints(reprints + 1)
                  toast.success("Reprint queued, marked COPY")
                }}
              >
                <Receipt />
                Reprint (COPY)
              </Button>
              <Button
                className="h-11"
                variant="outline"
                onClick={() => toast.success("Receipt emailed")}
              >
                <Mail />
                Email
              </Button>
              <Button
                className="h-11"
                variant="outline"
                onClick={() =>
                  toast.info("QR link displayed on customer screen")
                }
              >
                <QrCode />
                Show QR link
              </Button>
              <Button
                className="mt-auto h-11"
                variant="secondary"
                onClick={onClose}
              >
                Done
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-[1fr_260px]">
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-muted p-3">
                  <p className="text-xs text-muted-foreground">
                    {split ? `${split.label} balance` : "Balance"} USD
                  </p>
                  <p className="tabular text-2xl font-bold">{usd(balance)}</p>
                </div>
                <div className="rounded-lg bg-muted p-3">
                  <p className="text-xs text-muted-foreground">Balance KHR</p>
                  <p className="tabular text-2xl font-bold">
                    {khr(toKhr(balance))}
                  </p>
                </div>
              </div>
              {order.splits && (
                <div className="flex gap-1.5">
                  {order.splits.map((s, i) => (
                    <button
                      key={s.label}
                      aria-pressed={i === splitIdx}
                      className={chip(i === splitIdx)}
                      onClick={() => setSplitIdx(i)}
                    >
                      {s.label} · {usd(s.total)}
                      {s.balance === 0 && " ✓"}
                    </button>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                {methods.map((m) => (
                  <button
                    key={m.id}
                    aria-pressed={m.id === methodId}
                    className={chip(m.id === methodId)}
                    onClick={() => {
                      setMethodId(m.id)
                      setTendered("")
                      setErr("")
                    }}
                  >
                    {m.id}
                  </button>
                ))}
              </div>
              {method.cash ? (
                <>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      className="h-11"
                      disabled={busy || balance === 0}
                      onClick={() =>
                        submit(
                          method.currency === "USD" ? balance : toKhr(balance)
                        )
                      }
                    >
                      Exact
                    </Button>
                    {(method.currency === "USD" ? usdNotes : khrNotes).map(
                      (n) => (
                        <Button
                          key={n}
                          variant="outline"
                          className="tabular h-11"
                          onClick={() => setTendered(String(n))}
                        >
                          {method.currency === "USD"
                            ? `$${n}`
                            : n.toLocaleString()}
                        </Button>
                      )
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg border p-3">
                      <p className="text-xs text-muted-foreground">
                        Change {changeCur}
                      </p>
                      <p className="tabular text-xl font-semibold">
                        {result && result.covered && num > 0
                          ? changeCur === "USD"
                            ? usd(result.change)
                            : khr(result.change)
                          : "—"}
                      </p>
                    </div>
                    <FormRow label="Give change in">
                      <SimpleSelect
                        aria-label="Change currency"
                        value={changeCur}
                        onChange={(v) => setChangeCur(v as "USD" | "KHR")}
                        options={opts("USD", "KHR")}
                      />
                    </FormRow>
                  </div>
                  {!hasSession && (
                    <Notice tone="danger">
                      No cashier session is open. Cash payments are blocked.
                    </Notice>
                  )}
                </>
              ) : (
                <FormRow
                  label={`${method.id} reference`}
                  required
                  htmlFor="pay-ref"
                >
                  <Input
                    id="pay-ref"
                    value={ref}
                    onChange={(e) => setRef(e.target.value)}
                    placeholder="Terminal or transaction reference"
                  />
                </FormRow>
              )}
              {order.payments.length > 0 && (
                <ul className="rounded-lg border text-sm">
                  {order.payments.map((p) => (
                    <li
                      key={p.id}
                      className="flex justify-between border-b p-2 last:border-0"
                    >
                      <span>
                        {p.method}
                        {p.reference && ` · ${p.reference}`}
                      </span>
                      <span className="tabular">{usd(p.applied)}</span>
                    </li>
                  ))}
                </ul>
              )}
              {err && (
                <p role="alert" className="text-sm text-danger">
                  {err}
                </p>
              )}
            </div>
            <div className="flex flex-col gap-2">
              {method.cash && (
                <>
                  <div
                    className="tabular rounded-lg border p-2 text-right text-2xl font-semibold"
                    aria-live="polite"
                  >
                    {tendered ? (
                      method.currency === "USD" ? (
                        `$${tendered}`
                      ) : (
                        `៛${Number(tendered).toLocaleString()}`
                      )
                    ) : (
                      <span className="text-muted-foreground">0</span>
                    )}
                  </div>
                  <Keypad
                    value={tendered}
                    onChange={setTendered}
                    decimals={method.currency === "USD"}
                  />
                </>
              )}
              <Button
                className="mt-auto h-12 text-base"
                disabled={busy || balance === 0}
                onClick={() => submit()}
              >
                {busy
                  ? "Recording…"
                  : method.cash
                    ? "Record payment"
                    : `Confirm ${usd(balance)}`}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
