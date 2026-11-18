"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  ArrowLeftRight,
  Ban,
  BadgePercent,
  CircleDollarSign,
  Coffee,
  Pause,
  Lock,
  Plus,
  ReceiptText,
  Search,
  Send,
  Split,
  UserPlus,
  UtensilsCrossed,
  WifiOff,
  Wifi,
  Wine,
  Soup,
  ClipboardList,
  Menu as MenuIcon,
} from "lucide-react"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { confirmAction } from "@/components/rms/dialog-host"
import * as pos from "@/lib/api/pos"
import {
  FormRow,
  LinkButton,
  Notice,
  QuantityStepper,
  StatusBadge,
} from "@/components/rms/kit"
import {
  DiscountDialog,
  ModifierDialog,
  PaymentDialog,
  SplitDialog,
} from "@/components/rms/pos-dialogs"
import {
  calcBill,
  khr,
  kitchenStatus,
  lineGross,
  toKhr,
  usd,
} from "@/lib/rms/billing"
import {
  categories,
  elapsed,
  minLabel,
  rms,
  useClock,
  useRms,
} from "@/lib/rms/store"
import type { MenuItem, OrderLine, OrderType } from "@/lib/rms/types"
import { customers } from "@/lib/rms/back-office"
import { cn } from "@/lib/utils"

const typeLabels: Record<OrderType, string> = {
  DINE_IN: "Dine-in",
  TAKEAWAY: "Takeaway",
  DELIVERY: "Delivery",
}
const itemIcon = (m: MenuItem) => {
  const cls = "size-4"
  if (m.cat === "bar") return <Wine className={cls} aria-hidden />
  if (m.type === "Beverage") return <Coffee className={cls} aria-hidden />
  return m.cat === "soups" ? (
    <Soup className={cls} aria-hidden />
  ) : (
    <UtensilsCrossed className={cls} aria-hidden />
  )
}
const voidReasons = [
  "Customer changed mind",
  "Wrong item entered",
  "Kitchen error",
  "Item unavailable",
  "Quality issue",
]

function ProductTile({ item, onAdd }: { item: MenuItem; onAdd: () => void }) {
  const off = !item.available
  return (
    <button
      onClick={onAdd}
      disabled={off}
      className={cn(
        "flex min-h-28 flex-col overflow-hidden rounded-xl border bg-card text-left transition-colors hover:border-primary active:scale-[.98]",
        off && "cursor-not-allowed opacity-50 grayscale hover:border-border"
      )}
    >
      <span className="flex h-11 items-center justify-between bg-accent/60 px-2.5 text-accent-foreground">
        {itemIcon(item)}
        {off ? (
          <span className="rounded bg-danger-soft px-1.5 text-xs font-medium text-danger">
            Sold out
          </span>
        ) : (
          (item.groups.length > 0 || item.variants) && (
            <span className="text-[11px] text-muted-foreground">options</span>
          )
        )}
      </span>
      <span className="flex flex-1 flex-col p-2.5">
        <span className="line-clamp-2 text-sm leading-tight font-medium">
          {item.name}
        </span>
        <span className="truncate text-xs text-muted-foreground">
          {item.km}
        </span>
        <span className="tabular mt-auto pt-1 text-sm font-semibold">
          {usd(item.price)}
        </span>
      </span>
    </button>
  )
}

function PosScreen() {
  const params = useSearchParams()
  const router = useRouter()
  const { orders, menu, tables, online, sessions, role, userName, branch } =
    useRms()
  const at = useClock()
  const [orderId, setOrderId] = React.useState<string | null>(
    params.get("order")
  )
  const [type, setType] = React.useState<OrderType>("DINE_IN")
  const [tableCode, setTableCode] = React.useState<string | undefined>(
    params.get("table") ?? undefined
  )
  const [guests, setGuests] = React.useState(Number(params.get("guests") ?? 2))
  const [pickup, setPickup] = React.useState("")
  const [cat, setCat] = React.useState("")
  const [search, setSearch] = React.useState("")
  const [dialog, setDialog] = React.useState<
    | null
    | "pay"
    | "split"
    | "discount"
    | "table"
    | "orders"
    | "customer"
    | "hold"
    | "transfer"
    | "line"
  >(null)
  const [modItem, setModItem] = React.useState<MenuItem | null>(null)
  const [editLine, setEditLine] = React.useState<string | null>(null)
  const [itemDiscount, setItemDiscount] = React.useState<OrderLine | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [holdLabel, setHoldLabel] = React.useState("")
  const [payFirst, setPayFirst] = React.useState(false)

  pos.useLiveSync()
  // Categories come from the API; until one is picked, show the first.
  const activeCat = categories.some((c) => c.id === cat) ? cat : (categories[0]?.id ?? "")
  const order = orders.find((o) => o.id === orderId)
  const canPay = ["GM", "BRMGR", "SUPV", "CASHIER", "BAR"].includes(role)
  const lines = order?.lines ?? []
  const pending = lines.filter((l) => l.status === "Pending")
  const totals = order ? calcBill(order) : null
  const session = sessions.find((s) => s.status === "Open" && s.mine)
  const held = orders.filter((o) => o.held)
  const open = orders.filter((o) => o.status === "Open" && !o.held)

  const shown = menu.filter(
    (m) =>
      m.active &&
      (search.trim().length >= 2
        ? `${m.name} ${m.km} ${m.code} ${m.sku ?? ""}`
            .toLowerCase()
            .includes(search.trim().toLowerCase())
        : m.cat === activeCat)
  )
  const editing = lines.find((l) => l.id === editLine)

  const reset = () => {
    setOrderId(null)
    setTableCode(undefined)
    setPickup("")
    setGuests(2)
  }
  /** Run an API action; errors are shown as toasts (the server's message). */
  const act = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true)
    try {
      return await fn()
    } catch (e) {
      pos.report(e)
      return undefined
    } finally {
      setBusy(false)
    }
  }
  const creating = React.useRef<Promise<string> | null>(null)
  const ensureOrder = async (): Promise<string> => {
    if (orderId) return orderId
    creating.current ??= (async () => {
      const table = tables.find((t) => t.code === tableCode)
      const o = await pos.createOrder(type, {
        tableId: table?.id,
        tableTag: table ? undefined : tableCode,
        guests,
        pickup,
      })
      setOrderId(o.id)
      return o.id
    })().finally(() => (creating.current = null))
    return creating.current
  }

  const addItem = (
    m: MenuItem,
    pick: { variant?: string; modifiers: OrderLine["modifiers"]; qty: number; note?: string }
  ) => act(async () => pos.addLine(await ensureOrder(), m, pick))
  const add = (m: MenuItem) => {
    if (m.variants || m.groups.length) return setModItem(m)
    void addItem(m, { modifiers: [], qty: 1 })
  }

  const send = () => {
    if (!order || !pending.length) return
    if (type === "DINE_IN" && !order.table && !tableCode) {
      setDialog("table")
      return toast.info("Choose a table first")
    }
    if (payFirst && totals!.balance > 0) {
      setDialog("pay")
      return toast.info("Pay-first mode: take payment before sending")
    }
    void act(async () => {
      const n = await pos.send(order.id)
      toast.success(`${n} item(s) sent to kitchen`)
    })
  }
  const voidLine = (l: OrderLine) => {
    const prepared = l.status === "In Preparation" || l.status === "Ready"
    confirmAction({
      title: `Cancel ${l.name}?`,
      effect: prepared
        ? "This item is already being prepared. It will be recorded as waste and needs manager approval."
        : "The kitchen will see this item struck through on its ticket.",
      reasons: voidReasons,
      destructive: true,
      confirmLabel: "Cancel item",
      onConfirm: (reason) =>
        // The backend decides whether a manager must approve (BR-012) and asks for it.
        void act(async () => {
          await pos.voidLine(order!.id, l, reason)
          toast.success("Item cancelled; kitchen notified")
        }),
    })
  }

  return (
    <div className="flex h-svh flex-col bg-muted/40">
      {!online && (
        <div className="flex items-center justify-center gap-2 bg-warning-soft py-1 text-sm font-medium text-warning">
          <WifiOff className="size-4" />
          Offline: orders and cash are queued on this device and will sync when
          you reconnect.
        </div>
      )}
      {/* Top bar */}
      <header className="flex flex-wrap items-center gap-2 border-b bg-background p-2">
        <LinkButton
          href="/"
          variant="outline"
          size="icon-lg"
          aria-label="Back office menu"
        >
          <MenuIcon />
        </LinkButton>
        <Tabs
          value={type}
          onValueChange={(v) => {
            setType(v as OrderType)
            if (!order) setPayFirst(v === "TAKEAWAY")
          }}
        >
          <TabsList className="h-11!">
            {(Object.keys(typeLabels) as OrderType[]).map((t) => (
              <TabsTrigger
                key={t}
                value={t}
                disabled={!!order}
                className="px-3"
              >
                {typeLabels[t]}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {type === "DINE_IN" ? (
          <>
            <Button
              variant="outline"
              className="h-11"
              onClick={() => setDialog("table")}
            >
              Table {order?.table ?? tableCode ?? "—"}
            </Button>
            <div className="flex items-center gap-1 text-sm">
              <span className="sr-only">Guests</span>
              <QuantityStepper
                value={guests}
                onChange={(n) => {
                  setGuests(n)
                  if (order) void act(() => pos.updateOrder(order.id, { guests: n }))
                }}
                min={1}
                size="lg"
                label="guests"
              />
              <span className="text-xs text-muted-foreground">guests</span>
            </div>
          </>
        ) : (
          <Input
            aria-label="Pickup name"
            className="h-11 w-40"
            placeholder={type === "TAKEAWAY" ? "Pickup name" : "Customer phone"}
            value={pickup}
            onChange={(e) => setPickup(e.target.value)}
            onBlur={() => {
              if (order && pickup !== (order.pickup ?? ""))
                void act(() => pos.updateOrder(order.id, { pickup }))
            }}
          />
        )}
        <Button
          variant="outline"
          className="h-11"
          onClick={() => setDialog("customer")}
        >
          <UserPlus />
          {order?.customer ?? "Customer"}
        </Button>
        <div className="relative min-w-40 flex-1">
          <Search
            className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            aria-label="Search menu"
            className="h-11 pl-9"
            placeholder="Search name, ខ្មែរ, code or scan barcode"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button
          variant="outline"
          className="h-11"
          onClick={() => setDialog("orders")}
        >
          <ClipboardList />
          Orders{" "}
          <span className="tabular rounded bg-muted px-1 text-xs">
            {held.length + open.length}
          </span>
        </Button>
        <button
          onClick={rms.toggleOnline}
          className={cn(
            "flex h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-medium",
            online ? "text-success" : "text-warning"
          )}
          aria-label="Toggle connection (demo)"
        >
          {online ? (
            <Wifi className="size-4" />
          ) : (
            <WifiOff className="size-4" />
          )}
          {online ? "Online" : "Offline"}
        </button>
        <LinkButton
          href="/lock"
          variant="ghost"
          className="h-11"
          aria-label="Lock and switch user"
        >
          <Lock />
          {userName.split(" ")[0]}
        </LinkButton>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Products */}
        <section
          className="flex min-h-0 flex-1 flex-col md:flex-row"
          aria-label="Menu"
        >
          <nav
            aria-label="Categories"
            className="flex shrink-0 gap-1.5 overflow-x-auto border-b bg-background p-2 md:w-36 md:flex-col md:overflow-y-auto md:border-r md:border-b-0"
          >
            {categories.map((c) => (
              <button
                key={c.id}
                aria-current={activeCat === c.id && !search ? "true" : undefined}
                onClick={() => {
                  setCat(c.id)
                  setSearch("")
                }}
                className={cn(
                  "touch-target shrink-0 rounded-lg px-3 py-2 text-left text-sm leading-tight font-medium",
                  activeCat === c.id && !search
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted"
                )}
              >
                {c.name}
                <span
                  className={cn(
                    "block text-xs font-normal",
                    activeCat === c.id && !search
                      ? "text-primary-foreground/80"
                      : "text-muted-foreground"
                  )}
                >
                  {c.km}
                </span>
              </button>
            ))}
          </nav>
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {shown.length === 0 ? (
              <p className="p-8 text-center text-muted-foreground">
                No items match “{search}”.
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
                {shown.map((m) => (
                  <ProductTile key={m.id} item={m} onAdd={() => add(m)} />
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Current order */}
        <aside
          className="flex max-h-[55svh] w-full shrink-0 flex-col border-t bg-background lg:max-h-none lg:w-96 lg:border-t-0 lg:border-l"
          aria-label="Current order"
        >
          <div className="flex items-center justify-between border-b p-3">
            <div>
              <p className="font-semibold">
                {order ? `Order ${order.no}` : "New order"}
              </p>
              <p className="text-xs text-muted-foreground">
                {typeLabels[order?.type ?? type]} · {branch}
                {order && ` · ${kitchenStatus(order)}`}
              </p>
            </div>
            <div className="flex items-center gap-1">
              {order && order.type !== "DINE_IN" && (
                <label className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={payFirst}
                    onChange={(e) => setPayFirst(e.target.checked)}
                  />
                  Pay first
                </label>
              )}
              <Button
                variant="ghost"
                size="icon-lg"
                aria-label="New order"
                onClick={reset}
              >
                <Plus />
              </Button>
            </div>
          </div>
          <ul className="min-h-0 flex-1 divide-y overflow-y-auto">
            {lines.length === 0 && (
              <li className="p-10 text-center text-sm text-muted-foreground">
                Tap a menu item to start this order.
              </li>
            )}
            {lines.map((l) => (
              <li
                key={l.id}
                className={cn(
                  "p-2.5",
                  l.status === "Cancelled" && "opacity-55"
                )}
              >
                <div className="flex items-start gap-2">
                  <button
                    className="min-w-0 flex-1 text-left"
                    onClick={() => {
                      setEditLine(l.id)
                      setDialog("line")
                    }}
                  >
                    <span
                      className={cn(
                        "block text-sm font-medium",
                        l.status === "Cancelled" && "line-through"
                      )}
                    >
                      {l.name}
                      {l.variant && (
                        <span className="font-normal"> ({l.variant})</span>
                      )}
                    </span>
                    {l.modifiers.length > 0 && (
                      <span className="block text-xs text-muted-foreground">
                        {l.modifiers.map((m) => m.name).join(", ")}
                      </span>
                    )}
                    {l.note && (
                      <span
                        className={cn(
                          "block text-xs",
                          l.allergy
                            ? "font-semibold text-danger"
                            : "text-warning"
                        )}
                      >
                        {l.note}
                      </span>
                    )}
                    {l.seat && (
                      <span className="block text-xs text-muted-foreground">
                        Seat {l.seat}
                      </span>
                    )}
                    {l.discount && (
                      <span className="block text-xs text-success">
                        Discount{" "}
                        {l.discount.kind === "percent"
                          ? `${l.discount.value}%`
                          : usd(l.discount.value)}
                      </span>
                    )}
                  </button>
                  <span className="tabular text-sm font-semibold">
                    {usd(lineGross(l))}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between">
                  {l.status === "Pending" ? (
                    <QuantityStepper
                      value={l.qty}
                      onChange={(q) => void act(() => pos.setQty(order!.id, l, q))}
                      label={l.name}
                    />
                  ) : (
                    <>
                      <span className="tabular text-xs text-muted-foreground">
                        Qty {l.qty}
                      </span>
                      <StatusBadge status={l.status} />
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {totals && lines.length > 0 && (
            <dl className="tabular space-y-0.5 border-t p-3 text-sm">
              <div className="flex justify-between">
                <dt>Subtotal</dt>
                <dd>{usd(totals.gross)}</dd>
              </div>
              {totals.itemDiscounts + totals.orderDiscount > 0 && (
                <div className="flex justify-between text-success">
                  <dt>Discounts</dt>
                  <dd>−{usd(totals.itemDiscounts + totals.orderDiscount)}</dd>
                </div>
              )}
              {totals.service > 0 && (
                <div className="flex justify-between">
                  <dt>Service charge</dt>
                  <dd>{usd(totals.service)}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt>Tax</dt>
                <dd>{usd(totals.tax)}</dd>
              </div>
              {totals.deliveryFee > 0 && (
                <div className="flex justify-between">
                  <dt>Delivery fee</dt>
                  <dd>{usd(totals.deliveryFee)}</dd>
                </div>
              )}
              <div className="flex justify-between pt-1 text-lg font-bold">
                <dt>Total</dt>
                <dd>{usd(totals.total)}</dd>
              </div>
              <div className="flex justify-between text-xs text-muted-foreground">
                <dt>Total KHR</dt>
                <dd>{khr(toKhr(totals.total))}</dd>
              </div>
              {totals.paid > 0 && (
                <div className="flex justify-between font-medium">
                  <dt>Balance</dt>
                  <dd>{usd(totals.balance)}</dd>
                </div>
              )}
            </dl>
          )}
          <div className="grid grid-cols-3 gap-1.5 border-t p-2">
            <Button
              className="col-span-3 h-12 text-base"
              disabled={!pending.length || busy}
              onClick={send}
            >
              <Send />
              {busy
                ? "Sending…"
                : `Send${pending.length ? ` (${pending.reduce((s, l) => s + l.qty, 0)})` : ""}`}
            </Button>
            <Button
              variant="outline"
              className="h-11"
              disabled={!order || !lines.length}
              onClick={() => {
                setHoldLabel("")
                setDialog("hold")
              }}
            >
              <Pause />
              Hold
            </Button>
            <Button
              variant="outline"
              className="h-11"
              disabled={!totals || totals.total === 0}
              onClick={() => setDialog("split")}
            >
              <Split />
              Split
            </Button>
            <Button
              variant="outline"
              className="h-11"
              disabled={!totals || totals.gross === 0}
              onClick={() => setDialog("discount")}
            >
              <BadgePercent />
              Disc.
            </Button>
            <Button
              variant="outline"
              className="h-11"
              disabled={!order || !lines.length}
              onClick={() =>
                void act(async () => {
                  await pos.printBill(order!.id)
                  toast.success("Bill printed")
                })
              }
            >
              <ReceiptText />
              Bill
            </Button>
            <Button
              variant="outline"
              className="h-11"
              disabled={!order?.table}
              onClick={() => setDialog("transfer")}
            >
              <ArrowLeftRight />
              Move
            </Button>
            <Button
              variant="secondary"
              className="h-11 font-semibold"
              disabled={!totals || totals.total === 0 || !canPay || busy}
              onClick={() => setDialog("pay")}
            >
              <CircleDollarSign />
              Pay
            </Button>
          </div>
          {!session && (
            <Notice tone="danger" className="m-2 mt-0">
              No cashier session is open.{" "}
              <a className="underline" href="/shifts">
                Open one
              </a>{" "}
              to take cash.
            </Notice>
          )}
        </aside>
      </div>

      <ModifierDialog
        item={modItem}
        onClose={() => setModItem(null)}
        onConfirm={(c) => {
          const m = modItem!
          setModItem(null)
          void addItem(m, { variant: c.variant, modifiers: c.modifiers, qty: c.qty, note: c.note })
        }}
      />
      {order && (
        <PaymentDialog
          orderId={order.id}
          open={dialog === "pay"}
          onClose={() => setDialog(null)}
          onPaid={() => {
            const fresh = calcBill(order)
            if (payFirst && pending.length && fresh.total)
              void act(async () => {
                const n = await pos.send(order.id)
                if (n) toast.success(`${n} item(s) sent to kitchen`)
              })
          }}
        />
      )}
      {order && (
        <SplitDialog
          order={order}
          open={dialog === "split"}
          onClose={() => setDialog(null)}
        />
      )}
      {order && totals && (
        <DiscountDialog
          open={dialog === "discount"}
          onClose={() => setDialog(null)}
          base={totals.gross - totals.itemDiscounts}
          title={`order ${order.no}`}
          current={order.discount}
          onApply={(d) => void act(() => pos.setDiscount(order.id, order, d))}
          onRemove={() => void act(() => pos.setDiscount(order.id, order, undefined))}
        />
      )}
      {order && itemDiscount && (
        <DiscountDialog
          open
          onClose={() => setItemDiscount(null)}
          base={lineGross(itemDiscount)}
          title={itemDiscount.name}
          current={itemDiscount.discount}
          onApply={(d) =>
            void act(() => pos.setDiscount(order.id, itemDiscount, d, itemDiscount.id))
          }
          onRemove={() =>
            void act(() => pos.setDiscount(order.id, itemDiscount, undefined, itemDiscount.id))
          }
        />
      )}

      <Dialog
        open={dialog === "line" && !!editing}
        onOpenChange={(o) => !o && setDialog(null)}
      >
        <DialogContent className="sm:max-w-md">
          {editing && (
            <>
              <DialogHeader>
                <DialogTitle>{editing.name}</DialogTitle>
                <DialogDescription>
                  {editing.status === "Pending"
                    ? "Not sent yet, so it can be changed freely."
                    : "Already sent: it can't be edited in place. Cancel it and add a new item."}
                </DialogDescription>
              </DialogHeader>
              {editing.status === "Pending" && (
                <>
                  <FormRow label="Kitchen note" htmlFor="l-note">
                    <Input
                      id="l-note"
                      key={editing.id}
                      defaultValue={editing.note ?? ""}
                      onBlur={(e) => {
                        if (e.target.value !== (editing.note ?? ""))
                          void act(() => pos.setLine(order!.id, editing.id, { note: e.target.value }))
                      }}
                    />
                  </FormRow>
                  <FormRow label="Seat">
                    <QuantityStepper
                      value={editing.seat ?? 1}
                      min={1}
                      label="seat"
                      onChange={(s) =>
                        void act(() => pos.setLine(order!.id, editing.id, { seat: s }))
                      }
                    />
                  </FormRow>
                </>
              )}
              <DialogFooter>
                {editing.status === "Pending" && (
                  <>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setItemDiscount(editing)
                        setDialog(null)
                      }}
                    >
                      <BadgePercent />
                      Item discount
                    </Button>
                    <Button
                      variant="destructive"
                      onClick={() => {
                        void act(() => pos.setQty(order!.id, editing, 0))
                        setDialog(null)
                      }}
                    >
                      Remove
                    </Button>
                  </>
                )}
                {!["Pending", "Cancelled", "Served", "Collected"].includes(
                  editing.status
                ) && (
                  <Button
                    variant="destructive"
                    onClick={() => {
                      setDialog(null)
                      voidLine(editing)
                    }}
                  >
                    <Ban />
                    Cancel item
                  </Button>
                )}
                <Button onClick={() => setDialog(null)}>Done</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={dialog === "table" || dialog === "transfer"}
        onOpenChange={(o) => !o && setDialog(null)}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {dialog === "transfer"
                ? `Move order from ${order?.table}`
                : "Choose a table"}
            </DialogTitle>
            <DialogDescription>
              {dialog === "transfer"
                ? "Only available tables can receive a transfer."
                : "Pick a table, or enter a table tag for counter service."}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
            {tables
              .filter(
                (t) =>
                  !t.outOfService &&
                  (dialog === "table" || t.state === "Available")
              )
              .map((t) => (
                <button
                  key={t.id}
                  onClick={() => {
                    if (dialog === "transfer") {
                      setDialog(null)
                      return void act(async () => {
                        await pos.transfer(order!.id, t.id)
                        setTableCode(t.code)
                        toast.success(`Moved to ${t.code}`)
                      })
                    }
                    if (t.orderId && t.state !== "Available") {
                      const o = orders.find((x) => x.id === t.orderId)
                      if (o) {
                        setOrderId(o.id)
                        setType("DINE_IN")
                        setTableCode(t.code)
                        setGuests(o.guests)
                        return setDialog(null)
                      }
                    }
                    // The table is seated when the order is created on it (or moved to it).
                    setTableCode(t.code)
                    if (order) void act(() => pos.transfer(order.id, t.id))
                    setDialog(null)
                  }}
                  className="touch-target rounded-lg border p-2 text-left hover:border-primary"
                >
                  <span className="block font-semibold">{t.code}</span>
                  <span className="block text-xs text-muted-foreground">
                    {t.state} · {t.capacity} seats
                  </span>
                </button>
              ))}
          </div>
          {dialog === "table" && (
            <FormRow label="Table tag (counter mode)" htmlFor="tag">
              <Input
                id="tag"
                placeholder="e.g. 42"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setTableCode((e.target as HTMLInputElement).value)
                    setDialog(null)
                  }
                }}
              />
            </FormRow>
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={dialog === "orders"}
        onOpenChange={(o) => !o && setDialog(null)}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Orders</DialogTitle>
            <DialogDescription>
              Resume a held order or open a running one.
            </DialogDescription>
          </DialogHeader>
          <Tabs defaultValue={held.length ? "held" : "open"}>
            <TabsList>
              <TabsTrigger value="held" className="px-3">
                Held ({held.length})
              </TabsTrigger>
              <TabsTrigger value="open" className="px-3">
                Open ({open.length})
              </TabsTrigger>
            </TabsList>
            {(["held", "open"] as const).map((k) => (
              <TabsContent key={k} value={k} className="mt-2 grid gap-1.5">
                {(k === "held" ? held : open).length === 0 && (
                  <p className="p-6 text-center text-sm text-muted-foreground">
                    No {k} orders.
                  </p>
                )}
                {(k === "held" ? held : open).map((o) => (
                  <button
                    key={o.id}
                    className="touch-target flex items-center justify-between rounded-lg border p-3 text-left hover:border-primary"
                    onClick={() => {
                      if (o.held) void act(() => pos.resume(o.id))
                      setOrderId(o.id)
                      setType(o.type)
                      setTableCode(o.table)
                      setGuests(o.guests)
                      setDialog(null)
                    }}
                  >
                    <span>
                      <span className="font-medium">{o.no}</span>{" "}
                      <span className="text-sm text-muted-foreground">
                        {o.held ??
                          (o.table
                            ? `Table ${o.table}`
                            : (o.pickup ?? typeLabels[o.type]))}
                      </span>
                    </span>
                    <span className="flex items-center gap-3 text-sm">
                      <span className="text-xs text-muted-foreground">
                        {minLabel(elapsed(o.createdAt, at))}
                      </span>
                      <span className="tabular font-medium">
                        {usd(calcBill(o).total)}
                      </span>
                    </span>
                  </button>
                ))}
              </TabsContent>
            ))}
          </Tabs>
        </DialogContent>
      </Dialog>

      <Dialog
        open={dialog === "hold"}
        onOpenChange={(o) => !o && setDialog(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Hold order</DialogTitle>
            <DialogDescription>
              Park this order and resume it from the Orders list.
            </DialogDescription>
          </DialogHeader>
          <FormRow label="Label" htmlFor="hold">
            <Input
              id="hold"
              autoFocus
              value={holdLabel}
              onChange={(e) => setHoldLabel(e.target.value)}
              placeholder="e.g. Man in blue shirt"
            />
          </FormRow>
          <DialogFooter>
            <Button
              onClick={() =>
                void act(async () => {
                  await pos.hold(order!.id, holdLabel || "Held order")
                  reset()
                  setDialog(null)
                  toast.success("Order held")
                })
              }
            >
              Hold
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={dialog === "customer"}
        onOpenChange={(o) => !o && setDialog(null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Attach customer</DialogTitle>
            <DialogDescription>
              Orders can stay anonymous unless the order type needs contact
              details.
            </DialogDescription>
          </DialogHeader>
          <ul className="max-h-72 divide-y overflow-y-auto rounded-lg border">
            {customers.map((c) => (
              <li key={c.id}>
                <button
                  className="flex w-full items-center justify-between p-2.5 text-left text-sm hover:bg-muted"
                  onClick={() => {
                    void act(async () => pos.updateOrder(await ensureOrder(), { customer: c.name }))
                    if (c.allergy) toast.warning(`${c.name}: ${c.allergy}`)
                    setDialog(null)
                  }}
                >
                  <span>
                    <span className="font-medium">{c.name}</span>{" "}
                    <span className="text-xs text-muted-foreground">
                      {c.phone}
                    </span>
                  </span>
                  <StatusBadge status={c.segment} tone="neutral" />
                </button>
              </li>
            ))}
          </ul>
          <DialogFooter>
            <Button variant="outline" onClick={() => router.push("/customers")}>
              Register new customer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default function PosPage() {
  return <PosScreen />
}
