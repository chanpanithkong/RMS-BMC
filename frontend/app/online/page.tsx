"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Minus, Plus, ShoppingBag, UtensilsCrossed } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FormRow, Notice, SimpleSelect, opts } from "@/components/rms/kit"
import { ModifierDialog } from "@/components/rms/pos-dialogs"
import { ApiError } from "@/lib/api/client"
import * as pub from "@/lib/api/public"
import { apiMessage } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"
import { categories } from "@/lib/rms/store"
import type { ComboPick, LineModifier, MenuItem } from "@/lib/rms/types"
import { cn } from "@/lib/utils"

interface CartLine {
  key: string
  item: MenuItem
  variant?: string
  price: number
  modifiers: LineModifier[]
  qty: number
  note?: string
  combo?: ComboPick[]
}
const WHEN: Record<string, number> = { "As soon as possible": 0, "In 30 minutes": 30, "In 1 hour": 60, "In 2 hours": 120 }

function OnlineOrdering() {
  const router = useRouter()
  const code = pub.branchCode(useSearchParams().get("branch"))
  const [menu, setMenu] = React.useState<pub.PublicMenu | null>(null)
  const [items, setItems] = React.useState<MenuItem[]>([])
  const [zones, setZones] = React.useState<Awaited<ReturnType<typeof pub.zones>>>([])
  const [loadError, setLoadError] = React.useState("")
  const [cat, setCat] = React.useState("")
  const [mod, setMod] = React.useState<MenuItem | null>(null)
  const [cart, setCart] = React.useState<CartLine[]>([])
  const [mode, setMode] = React.useState<"Pickup" | "Delivery">("Pickup")
  const [when, setWhen] = React.useState("As soon as possible")
  const [name, setName] = React.useState("")
  const [phone, setPhone] = React.useState("")
  const [zone, setZone] = React.useState("")
  const [address, setAddress] = React.useState("")
  const [promo, setPromo] = React.useState("")
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const [totals, setTotals] = React.useState<pub.Totals | null>(null)
  const [quoteError, setQuoteError] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [payNow, setPayNow] = React.useState<boolean | null>(null)
  const attempt = React.useRef(pub.newIdempotencyKey())
  const [requote, setRequote] = React.useState(0)

  React.useEffect(() => {
    if (!code) return
    let live = true
    Promise.all([pub.menu(code), pub.zones(code).catch(() => [])]).then(
      ([m, z]) => {
        if (!live) return
        setItems(pub.loadPublicMenu(m))
        setMenu(m)
        setZones(z)
      },
      (e) => live && setLoadError(apiMessage(e))
    )
    return () => {
      live = false
    }
  }, [code])
  // Prefill name and phone for signed-in customers.
  React.useEffect(() => {
    if (!pub.customerToken()) return
    pub.account().then(
      (a) => {
        setName((n) => n || a.name)
        setPhone((p) => p || a.phone)
      },
      () => pub.setCustomerToken(null)
    )
  }, [])

  const cartBody = (): pub.Cart => ({
    fulfilment: mode,
    name: name.trim() || "Guest",
    // The quote only prices the cart; until a valid number is typed, a neutral one keeps validation from failing.
    phone: /^(\+855|0)[\d ]{7,12}$/.test(phone.trim()) ? phone.trim() : "012 000 000",
    scheduled_at: WHEN[when] ? new Date(Date.now() + WHEN[when] * 60_000).toISOString() : undefined,
    delivery: mode === "Delivery" && zone ? { zone_id: zones.find((z) => z.name === zone)?.id ?? "", address: address.trim() || "—" } : undefined,
    promo_code: promo.trim() || undefined,
    items: cart.map((l) => ({
      variant_id: l.item.variantIds?.[l.variant ?? "Regular"] ?? Object.values(l.item.variantIds ?? {})[0],
      quantity: String(l.qty),
      modifiers: l.modifiers.filter((m) => m.id).map((m) => ({ modifier_id: m.id! })),
      note: l.note,
      combo: l.combo,
    })),
  })
  // The server prices the cart (tax, service, delivery fee, promotions) whenever it changes.
  const cartKey = JSON.stringify([cart.map((l) => [l.key, l.qty]), mode, zone, promo.trim(), when, requote])
  React.useEffect(() => {
    if (!code || cart.length === 0 || (mode === "Delivery" && !zone)) return
    let live = true
    const t = setTimeout(() => {
      pub.quote(code, cartBody()).then(
        (q) => {
          if (!live) return
          setTotals(q.totals)
          setQuoteError("")
        },
        (e) => live && setQuoteError(apiMessage(e))
      )
    }, 300)
    return () => {
      live = false
      clearTimeout(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, cartKey])

  const shown = items.filter((m) => m.cat === (categories.some((c) => c.id === cat) ? cat : categories[0]?.id))
  const sub = cart.reduce((s, l) => s + (l.price + l.modifiers.reduce((a, m) => a + m.delta, 0)) * l.qty, 0)
  const priced = cart.length > 0 && (mode === "Pickup" || !!zone) ? totals : null
  const addLine = (item: MenuItem, o: Omit<CartLine, "key" | "item">) => setCart((c) => [...c, { ...o, item, key: `${item.id}-${Date.now()}` }])
  const add = (m: MenuItem) => (m.variants || m.groups.length || m.combo ? setMod(m) : addLine(m, { price: m.price, modifiers: [], qty: 1 }))

  const khqr = menu?.payment?.online === "khqr"
  const payLater = menu?.payment?.pay_later ?? true
  const online = khqr && (payNow ?? !payLater)
  const place = async () => {
    const e: Record<string, string> = {}
    if (!name.trim()) e.name = "Enter your name"
    if (!/^(\+855|0)[\d ]{7,12}$/.test(phone.trim())) e.phone = "Enter a Cambodian phone number"
    if (mode === "Delivery" && !zone) e.zone = "Choose your area"
    if (mode === "Delivery" && address.trim().length < 3) e.address = "Enter a delivery address"
    if (!cart.length) e.cart = "Add something to your order"
    setErrors(e)
    if (Object.keys(e).length || !priced) return
    setBusy(true)
    try {
      const r = await pub.checkout(code, cartBody(), priced.total, attempt.current, online ? "Online" : "PayLater")
      router.push(`/track/${r.tracking_token}`)
    } catch (err) {
      setBusy(false)
      if (err instanceof ApiError && err.code === "PRICE_CHANGED") {
        attempt.current = pub.newIdempotencyKey()
        setQuoteError("Prices changed while you were ordering. Check the new total and place the order again.")
        setTotals(null)
        setRequote((n) => n + 1)
      } else setQuoteError(apiMessage(err))
    }
  }

  if (!code)
    return (
      <main className="flex min-h-svh items-center justify-center p-6 text-center">
        <p className="max-w-sm text-muted-foreground">Open the ordering link from the restaurant. It tells us which branch you are ordering from.</p>
      </main>
    )
  if (loadError)
    return (
      <main className="flex min-h-svh items-center justify-center p-6 text-center">
        <p className="max-w-sm">{loadError}</p>
      </main>
    )
  const closed = menu ? !menu.branch.open_now : false

  return (
    <div className="min-h-svh bg-muted/30">
      <header className="sticky top-0 z-10 flex items-center gap-2 border-b bg-background px-4 py-3">
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <UtensilsCrossed className="size-4" />
        </span>
        <div>
          <h1 className="leading-tight font-semibold">{menu?.branch.name_en ?? "Online ordering"}</h1>
          <p className="text-xs text-muted-foreground">
            {menu?.branch.address ?? ""}
            {menu?.branch.opening_hours ? ` · ${menu.branch.opening_hours}` : ""}
          </p>
        </div>
        <Link href={`/signup?branch=${code}`} className="ml-auto text-sm text-primary hover:underline">
          Account
        </Link>
      </header>
      {closed && (
        <Notice className="rounded-none" tone="warning">
          We&apos;re closed right now. You can order for later today.
        </Notice>
      )}
      <div className="mx-auto grid max-w-6xl grid-cols-1 items-start gap-4 p-4 lg:grid-cols-[1fr_360px]">
        <main className="min-w-0">
          <nav className="mb-3 flex gap-1.5 overflow-x-auto pb-1" aria-label="Menu categories">
            {categories.map((c) => (
              <button
                key={c.id}
                aria-current={c.id === (cat || categories[0]?.id) ? "true" : undefined}
                onClick={() => setCat(c.id)}
                className={cn("shrink-0 rounded-full border px-3 py-1.5 text-sm font-medium", c.id === (cat || categories[0]?.id) ? "border-primary bg-primary text-primary-foreground" : "bg-background")}
              >
                {c.name}
              </button>
            ))}
          </nav>
          {!menu && <p className="text-sm text-muted-foreground">Loading the menu…</p>}
          <ul className="grid gap-2 sm:grid-cols-2">
            {shown.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-3 rounded-xl border bg-card p-3">
                <div className="min-w-0">
                  <p className="font-medium">{m.name}</p>
                  <p className="text-xs text-muted-foreground">{m.km}</p>
                  {m.desc && <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{m.desc}</p>}
                  <p className="tabular mt-1 text-sm font-semibold">{usd(m.price)}</p>
                </div>
                <Button size="icon-lg" aria-label={`Add ${m.name}`} onClick={() => add(m)}>
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
            <p className="py-6 text-center text-sm text-muted-foreground">Your cart is empty.</p>
          ) : (
            <ul className="my-2 divide-y">
              {cart.map((l) => (
                <li key={l.key} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="min-w-0">
                    <span className="font-medium">
                      {l.item.name}
                      {l.variant && ` (${l.variant})`}
                    </span>
                    {l.modifiers.length > 0 && <span className="block truncate text-xs text-muted-foreground">{l.modifiers.map((m) => m.name).join(", ")}</span>}
                  </span>
                  <span className="flex items-center gap-1">
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Decrease"
                      onClick={() => setCart((c) => c.flatMap((x) => (x.key === l.key ? (x.qty > 1 ? [{ ...x, qty: x.qty - 1 }] : []) : [x])))}
                    >
                      <Minus />
                    </Button>
                    <span className="tabular w-5 text-center">{l.qty}</span>
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Increase"
                      disabled={!!menu?.max_qty_per_line && l.qty >= menu.max_qty_per_line}
                      onClick={() => setCart((c) => c.map((x) => (x.key === l.key ? { ...x, qty: x.qty + 1 } : x)))}
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
                <SimpleSelect aria-label="Order type" value={mode} onChange={(v) => setMode(v as "Pickup" | "Delivery")} options={opts("Pickup", ...(zones.length ? ["Delivery"] : []))} />
              </FormRow>
              <FormRow label="When">
                <SimpleSelect aria-label="When" value={when} onChange={setWhen} options={opts(...Object.keys(WHEN))} />
              </FormRow>
            </div>
            <FormRow label="Name" required error={errors.name} htmlFor="on-n">
              <Input id="on-n" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </FormRow>
            <FormRow label="Phone" required error={errors.phone} htmlFor="on-p">
              <Input id="on-p" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" placeholder="012 345 678" />
            </FormRow>
            {mode === "Delivery" && (
              <>
                <FormRow label="Area" required error={errors.zone}>
                  <SimpleSelect
                    aria-label="Delivery area"
                    value={zone}
                    onChange={setZone}
                    options={zones.map((z) => ({ value: z.name, label: `${z.name} · ${usd(Number(z.fee))}${z.free_over ? ` (free over ${usd(Number(z.free_over))})` : ""}` }))}
                    placeholder="Choose your area"
                  />
                </FormRow>
                <FormRow label="Delivery address" required error={errors.address} htmlFor="on-a">
                  <Input id="on-a" value={address} onChange={(e) => setAddress(e.target.value)} autoComplete="street-address" />
                </FormRow>
              </>
            )}
            <FormRow label="Promotion code" htmlFor="on-c">
              <Input id="on-c" value={promo} onChange={(e) => setPromo(e.target.value)} />
            </FormRow>
          </div>
          <dl className="tabular mt-3 space-y-0.5 border-t pt-2 text-sm">
            <div className="flex justify-between">
              <dt>Subtotal</dt>
              <dd>{usd(priced ? Number(priced.subtotal) : sub)}</dd>
            </div>
            {priced && Number(priced.discount_total) > 0 && (
              <div className="flex justify-between text-success">
                <dt>Promotions</dt>
                <dd>−{usd(Number(priced.discount_total))}</dd>
              </div>
            )}
            {priced && Number(priced.service_charge) > 0 && (
              <div className="flex justify-between">
                <dt>Service charge</dt>
                <dd>{usd(Number(priced.service_charge))}</dd>
              </div>
            )}
            {priced && (
              <div className="flex justify-between">
                <dt>Tax</dt>
                <dd>{usd(Number(priced.tax))}</dd>
              </div>
            )}
            {priced && Number(priced.delivery_fee) > 0 && (
              <div className="flex justify-between">
                <dt>Delivery</dt>
                <dd>{usd(Number(priced.delivery_fee))}</dd>
              </div>
            )}
            <div className="flex justify-between text-base font-bold">
              <dt>Total</dt>
              <dd>{priced ? usd(Number(priced.total)) : "—"}</dd>
            </div>
          </dl>
          {(errors.cart || quoteError) && (
            <p role="alert" className="mt-1 text-xs text-danger">
              {errors.cart || quoteError}
            </p>
          )}
          {khqr && payLater && (
            <fieldset className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <legend className="mb-1 text-xs font-medium text-muted-foreground">Payment</legend>
              {[
                { on: true, label: "Pay now (KHQR)" },
                { on: false, label: mode === "Delivery" ? "Pay on delivery" : "Pay at pickup" },
              ].map((o) => (
                <button
                  key={o.label}
                  type="button"
                  aria-pressed={online === o.on}
                  onClick={() => setPayNow(o.on)}
                  className={cn("rounded-lg border px-3 py-2", online === o.on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}
                >
                  {o.label}
                </button>
              ))}
            </fieldset>
          )}
          <Button className="mt-3 h-11 w-full" disabled={busy || !priced} onClick={() => void place()}>
            {busy ? "Placing order…" : online ? "Place order and pay" : "Place order"}
          </Button>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            {online ? "Scan the KHQR code on the next page with your banking app." : "Pay when you collect or when it is delivered."}
          </p>
        </aside>
      </div>
      <ModifierDialog
        item={mod}
        onClose={() => setMod(null)}
        onConfirm={(c) => {
          addLine(mod!, { variant: c.variant, price: c.price, modifiers: c.modifiers, qty: c.qty, note: c.note, combo: c.combo })
          setMod(null)
        }}
      />
    </div>
  )
}

export default function OnlineOrderingPage() {
  return (
    <React.Suspense>
      <OnlineOrdering />
    </React.Suspense>
  )
}
