"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import { Check, Minus, Plus, ShoppingBag } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/rms/kit"
import { ModifierDialog } from "@/components/rms/pos-dialogs"
import * as pub from "@/lib/api/public"
import { apiMessage } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"
import { categories } from "@/lib/rms/store"
import type { ComboPick, LineModifier, MenuItem } from "@/lib/rms/types"
import { cn } from "@/lib/utils"

interface Line {
  key: string
  item: MenuItem
  variant?: string
  price: number
  modifiers: LineModifier[]
  qty: number
  note?: string
  combo?: ComboPick[]
}

/** Table QR ordering (FR-ONL-012): guests add items to their table's order; staff may confirm first. */
export default function QrOrderingPage() {
  const { token } = useParams<{ token: string }>()
  const [menu, setMenu] = React.useState<Awaited<ReturnType<typeof pub.qrMenu>> | null>(null)
  const [items, setItems] = React.useState<MenuItem[]>([])
  const [error, setError] = React.useState("")
  const [cat, setCat] = React.useState("")
  const [mod, setMod] = React.useState<MenuItem | null>(null)
  const [cart, setCart] = React.useState<Line[]>([])
  const [busy, setBusy] = React.useState(false)
  const [sent, setSent] = React.useState<{ order_no: string; status: string } | null>(null)
  const attempt = React.useRef(pub.newIdempotencyKey())

  React.useEffect(() => {
    let live = true
    pub.qrMenu(token).then(
      (m) => {
        if (!live) return
        setItems(pub.loadPublicMenu(m))
        setMenu(m)
      },
      (e) => live && setError(apiMessage(e))
    )
    return () => {
      live = false
    }
  }, [token])

  const activeCat = categories.some((c) => c.id === cat) ? cat : categories[0]?.id
  const shown = items.filter((m) => m.cat === activeCat)
  const estimate = cart.reduce((s, l) => s + (l.price + l.modifiers.reduce((a, m) => a + m.delta, 0)) * l.qty, 0)
  const addLine = (item: MenuItem, o: Omit<Line, "key" | "item">) => setCart((c) => [...c, { ...o, item, key: `${item.id}-${Date.now()}` }])
  const add = (m: MenuItem) => (m.variants || m.groups.length || m.combo ? setMod(m) : addLine(m, { price: m.price, modifiers: [], qty: 1 }))
  const send = async () => {
    setBusy(true)
    setError("")
    try {
      const r = await pub.qrOrder(
        token,
        cart.map((l) => ({
          variant_id: l.item.variantIds?.[l.variant ?? "Regular"] ?? Object.values(l.item.variantIds ?? {})[0],
          quantity: String(l.qty),
          modifiers: l.modifiers.filter((m) => m.id).map((m) => ({ modifier_id: m.id! })),
          note: l.note,
          combo: l.combo,
        })),
        undefined,
        undefined,
        attempt.current
      )
      setSent(r)
      setCart([])
      attempt.current = pub.newIdempotencyKey()
    } catch (e) {
      setError(apiMessage(e))
    } finally {
      setBusy(false)
    }
  }

  if (error && !menu)
    return (
      <main className="flex min-h-svh items-center justify-center p-6 text-center">
        <p className="max-w-sm">{error} Please ask a member of staff.</p>
      </main>
    )
  if (!menu) return <main className="p-6 text-center text-sm text-muted-foreground">Loading the menu…</main>

  return (
    <div className="min-h-svh bg-muted/30 pb-28">
      <header className="sticky top-0 z-10 border-b bg-background px-4 py-3">
        <h1 className="font-semibold">{menu.branch.name_en}</h1>
        <p className="text-xs text-muted-foreground">Table {menu.table} · order from your phone</p>
      </header>
      {sent && (
        <Notice tone="success" className="m-4">
          <span className="flex items-center gap-1.5">
            <Check className="size-4" />
            Sent{sent.order_no ? ` to order ${sent.order_no}` : ""}.{" "}
            {menu.staff_confirmation ? "A member of staff will confirm it shortly." : "The kitchen has it."}
          </span>
        </Notice>
      )}
      <nav className="flex gap-1.5 overflow-x-auto px-4 pt-3 pb-1" aria-label="Menu categories">
        {categories.map((c) => (
          <button
            key={c.id}
            aria-current={c.id === activeCat ? "true" : undefined}
            onClick={() => setCat(c.id)}
            className={cn("shrink-0 rounded-full border px-3 py-1.5 text-sm font-medium", c.id === activeCat ? "border-primary bg-primary text-primary-foreground" : "bg-background")}
          >
            {c.name}
          </button>
        ))}
      </nav>
      <ul className="grid gap-2 p-4 sm:grid-cols-2">
        {shown.map((m) => (
          <li key={m.id} className="flex items-center justify-between gap-3 rounded-xl border bg-card p-3">
            <div className="min-w-0">
              <p className="font-medium">{m.name}</p>
              <p className="text-xs text-muted-foreground">{m.km}</p>
              <p className="tabular mt-1 text-sm font-semibold">{usd(m.price)}</p>
            </div>
            <Button size="icon-lg" aria-label={`Add ${m.name}`} onClick={() => add(m)}>
              <Plus />
            </Button>
          </li>
        ))}
      </ul>
      {cart.length > 0 && (
        <div className="fixed inset-x-0 bottom-0 border-t bg-background p-3 shadow-lg">
          <ul className="mx-auto mb-2 max-h-40 max-w-xl divide-y overflow-y-auto text-sm">
            {cart.map((l) => (
              <li key={l.key} className="flex items-center justify-between gap-2 py-1.5">
                <span className="min-w-0 truncate">
                  {l.item.name}
                  {l.variant && ` (${l.variant})`}
                </span>
                <span className="flex items-center gap-1">
                  <Button variant="outline" size="icon-sm" aria-label="Decrease" onClick={() => setCart((c) => c.flatMap((x) => (x.key === l.key ? (x.qty > 1 ? [{ ...x, qty: x.qty - 1 }] : []) : [x])))}>
                    <Minus />
                  </Button>
                  <span className="tabular w-5 text-center">{l.qty}</span>
                  <Button variant="outline" size="icon-sm" aria-label="Increase" onClick={() => setCart((c) => c.map((x) => (x.key === l.key ? { ...x, qty: x.qty + 1 } : x)))}>
                    <Plus />
                  </Button>
                </span>
              </li>
            ))}
          </ul>
          {error && (
            <p role="alert" className="mx-auto mb-2 max-w-xl text-xs text-danger">
              {error}
            </p>
          )}
          <Button className="mx-auto flex h-12 w-full max-w-xl" disabled={busy} onClick={() => void send()}>
            <ShoppingBag />
            {busy ? "Sending…" : `Send to the kitchen · about ${usd(estimate)} before tax`}
          </Button>
          <p className="mx-auto mt-1 max-w-xl text-center text-xs text-muted-foreground">Pay at the table when you are done. The bill shows the exact total.</p>
        </div>
      )}
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
