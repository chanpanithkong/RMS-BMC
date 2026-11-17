"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { Minus, Plus, ShoppingBag, UtensilsCrossed } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FormRow, Notice, SimpleSelect, opts } from "@/components/rms/kit"
import { ModifierDialog } from "@/components/rms/pos-dialogs"
import { round2, usd } from "@/lib/rms/billing"
import { categories, rms, useRms } from "@/lib/rms/store"
import type { LineModifier, MenuItem } from "@/lib/rms/types"
import { cn } from "@/lib/utils"

interface CartLine {
  key: string
  item: MenuItem
  variant?: string
  price: number
  modifiers: LineModifier[]
  qty: number
  note?: string
}
const MIN_ORDER = 3

export default function OnlineOrderingPage() {
  const { menu, onlinePaused } = useRms()
  const router = useRouter()
  const [cat, setCat] = React.useState("rice")
  const [mod, setMod] = React.useState<MenuItem | null>(null)
  const [cart, setCart] = React.useState<CartLine[]>([])
  const [mode, setMode] = React.useState("Pickup")
  const [when, setWhen] = React.useState("ASAP")
  const [name, setName] = React.useState("")
  const [phone, setPhone] = React.useState("")
  const [address, setAddress] = React.useState("")
  const [code, setCode] = React.useState("")
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const [busy, setBusy] = React.useState(false)
  const items = menu.filter(
    (m) => m.active && m.channels.includes("Online") && m.cat === cat
  )
  const sub = round2(
    cart.reduce(
      (s, l) =>
        s + (l.price + l.modifiers.reduce((a, m) => a + m.delta, 0)) * l.qty,
      0
    )
  )
  const discount = code.toUpperCase() === "WELCOME10" ? round2(sub * 0.1) : 0
  const fee = mode === "Delivery" ? 1 : 0
  const tax = round2((sub - discount) * 0.1)
  const total = round2(sub - discount + tax + fee)
  const addLine = (item: MenuItem, o: Omit<CartLine, "key" | "item">) =>
    setCart((c) => [
      ...c,
      { ...o, item, key: `${item.id}-${c.length}-${o.qty}` },
    ])
  const add = (m: MenuItem) =>
    m.variants || m.groups.length
      ? setMod(m)
      : addLine(m, { price: m.price, modifiers: [], qty: 1 })
  const place = () => {
    const e: Record<string, string> = {}
    if (!name.trim()) e.name = "Enter your name"
    if (!/^(\+855|0)[\d ]{7,12}$/.test(phone))
      e.phone = "Enter a Cambodian phone number"
    if (mode === "Delivery" && !address.trim())
      e.address = "Enter a delivery address"
    if (sub < MIN_ORDER) e.cart = `Minimum order is ${usd(MIN_ORDER)}`
    setErrors(e)
    if (Object.keys(e).length) return
    setBusy(true)
    setTimeout(() => {
      const id = rms.createOrder(mode === "Pickup" ? "TAKEAWAY" : "DELIVERY", {
        channel: "ONLINE",
        pickup: name,
        server: "Online",
        onlineState: "Received",
        customer: name,
        status: "Open",
        delivery:
          mode === "Delivery"
            ? {
                phone,
                address,
                zone: "Zone A",
                fee,
                status: "Pending Assignment",
              }
            : undefined,
      })
      cart.forEach((l) =>
        rms.addLine(id, {
          itemId: l.item.id,
          name: l.item.name,
          km: l.item.km,
          variant: l.variant,
          modifiers: l.modifiers,
          unitPrice: l.price,
          qty: l.qty,
          station: l.item.station,
          note: l.note,
        })
      )
      rms.updateOrder(id, { status: "Open" })
      toast.success("Order placed")
      router.push(`/online/track/${id}`)
    }, 400)
  }
  return (
    <div className="min-h-svh bg-muted/30">
      <header className="sticky top-0 z-10 flex items-center gap-2 border-b bg-background px-4 py-3">
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <UtensilsCrossed className="size-4" />
        </span>
        <div>
          <h1 className="leading-tight font-semibold">RMS Demo Restaurant</h1>
          <p className="text-xs text-muted-foreground">
            Riverside · open until 23:00
          </p>
        </div>
        <a
          href="/signup"
          className="ml-auto text-sm text-primary hover:underline"
        >
          Create account
        </a>
      </header>
      {onlinePaused && (
        <Notice className="rounded-none" tone="warning">
          We&apos;re not taking online orders right now. Please check back soon.
        </Notice>
      )}
      <div className="mx-auto grid max-w-6xl grid-cols-1 items-start gap-4 p-4 lg:grid-cols-[1fr_360px]">
        <main className="min-w-0">
          <nav
            className="mb-3 flex gap-1.5 overflow-x-auto pb-1"
            aria-label="Menu categories"
          >
            {categories.map((c) => (
              <button
                key={c.id}
                aria-current={c.id === cat ? "true" : undefined}
                onClick={() => setCat(c.id)}
                className={cn(
                  "shrink-0 rounded-full border px-3 py-1.5 text-sm font-medium",
                  c.id === cat
                    ? "border-primary bg-primary text-primary-foreground"
                    : "bg-background"
                )}
              >
                {c.name}
              </button>
            ))}
          </nav>
          <ul className="grid gap-2 sm:grid-cols-2">
            {items.map((m) => (
              <li
                key={m.id}
                className={cn(
                  "flex items-center justify-between gap-3 rounded-xl border bg-card p-3",
                  !m.available && "opacity-55"
                )}
              >
                <div className="min-w-0">
                  <p className="font-medium">{m.name}</p>
                  <p className="text-xs text-muted-foreground">{m.km}</p>
                  <p className="tabular mt-1 text-sm font-semibold">
                    {usd(m.price)}
                  </p>
                </div>
                <Button
                  size="icon-lg"
                  aria-label={`Add ${m.name}`}
                  disabled={!m.available || onlinePaused}
                  onClick={() => add(m)}
                >
                  <Plus />
                </Button>
              </li>
            ))}
          </ul>
        </main>
        <aside className="rounded-xl border bg-card p-4 lg:sticky lg:top-20">
          <h2 className="flex items-center gap-2 font-semibold">
            <ShoppingBag className="size-4" />
            Your order
          </h2>
          {cart.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Your cart is empty.
            </p>
          ) : (
            <ul className="my-2 divide-y">
              {cart.map((l) => (
                <li
                  key={l.key}
                  className="flex items-center justify-between gap-2 py-2 text-sm"
                >
                  <span className="min-w-0">
                    <span className="font-medium">
                      {l.item.name}
                      {l.variant && ` (${l.variant})`}
                    </span>
                    {l.modifiers.length > 0 && (
                      <span className="block truncate text-xs text-muted-foreground">
                        {l.modifiers.map((m) => m.name).join(", ")}
                      </span>
                    )}
                  </span>
                  <span className="flex items-center gap-1">
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Decrease"
                      onClick={() =>
                        setCart((c) =>
                          c.flatMap((x) =>
                            x.key === l.key
                              ? x.qty > 1
                                ? [{ ...x, qty: x.qty - 1 }]
                                : []
                              : [x]
                          )
                        )
                      }
                    >
                      <Minus />
                    </Button>
                    <span className="tabular w-5 text-center">{l.qty}</span>
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Increase"
                      onClick={() =>
                        setCart((c) =>
                          c.map((x) =>
                            x.key === l.key ? { ...x, qty: x.qty + 1 } : x
                          )
                        )
                      }
                    >
                      <Plus />
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="grid gap-2">
            <div className="grid grid-cols-2 gap-2">
              <FormRow label="Order type">
                <SimpleSelect
                  aria-label="Order type"
                  value={mode}
                  onChange={setMode}
                  options={opts("Pickup", "Delivery")}
                />
              </FormRow>
              <FormRow label="When">
                <SimpleSelect
                  aria-label="When"
                  value={when}
                  onChange={setWhen}
                  options={opts("ASAP", "In 30 min", "In 1 hour", "In 2 hours")}
                />
              </FormRow>
            </div>
            <FormRow label="Name" required error={errors.name} htmlFor="on-n">
              <Input
                id="on-n"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
              />
            </FormRow>
            <FormRow label="Phone" required error={errors.phone} htmlFor="on-p">
              <Input
                id="on-p"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                autoComplete="tel"
                placeholder="012 345 678"
              />
            </FormRow>
            {mode === "Delivery" && (
              <FormRow
                label="Delivery address"
                required
                error={errors.address}
                htmlFor="on-a"
              >
                <Input
                  id="on-a"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  autoComplete="street-address"
                />
              </FormRow>
            )}
            <FormRow
              label="Promotion code"
              htmlFor="on-c"
              hint={code && !discount ? "This code isn't valid" : undefined}
            >
              <Input
                id="on-c"
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </FormRow>
          </div>
          <dl className="tabular mt-3 space-y-0.5 border-t pt-2 text-sm">
            <div className="flex justify-between">
              <dt>Subtotal</dt>
              <dd>{usd(sub)}</dd>
            </div>
            {discount > 0 && (
              <div className="flex justify-between text-success">
                <dt>Promotion</dt>
                <dd>−{usd(discount)}</dd>
              </div>
            )}
            <div className="flex justify-between">
              <dt>Tax</dt>
              <dd>{usd(tax)}</dd>
            </div>
            {fee > 0 && (
              <div className="flex justify-between">
                <dt>Delivery</dt>
                <dd>{usd(fee)}</dd>
              </div>
            )}
            <div className="flex justify-between text-base font-bold">
              <dt>Total</dt>
              <dd>{usd(total)}</dd>
            </div>
          </dl>
          {errors.cart && (
            <p role="alert" className="mt-1 text-xs text-danger">
              {errors.cart}
            </p>
          )}
          <Button
            className="mt-3 h-11 w-full"
            disabled={busy || onlinePaused}
            onClick={place}
          >
            {busy ? "Placing order…" : "Place order"}
          </Button>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Pay at pickup or on delivery. Online payment connects through a
            hosted gateway.
          </p>
        </aside>
      </div>
      <ModifierDialog
        item={mod}
        onClose={() => setMod(null)}
        onConfirm={(c) => {
          addLine(mod!, {
            variant: c.variant,
            price: c.price,
            modifiers: c.modifiers,
            qty: c.qty,
            note: c.note,
          })
          setMod(null)
        }}
      />
    </div>
  )
}
