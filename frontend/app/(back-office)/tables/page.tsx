"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  AlertTriangle,
  Armchair,
  Ban,
  Brush,
  CalendarClock,
  Check,
  ClipboardList,
  Combine,
  Hourglass,
  PencilRuler,
  ReceiptText,
  Soup,
  UserRoundCheck,
  Users,
  Wrench,
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
import { confirmAction } from "@/components/rms/dialog-host"
import { ApiError } from "@/lib/api/client"
import * as pos from "@/lib/api/pos"
import {
  FormRow,
  LinkButton,
  Notice,
  Page,
  PageHeader,
  QuantityStepper,
  SimpleSelect,
  Stat,
  opts,
} from "@/components/rms/kit"
import { initials, minLabel, useClock, useRms } from "@/lib/rms/store"
import type { FloorTable, TableState } from "@/lib/rms/types"
import { cn } from "@/lib/utils"

const stateStyle: Record<
  TableState | "Out of Service",
  { cls: string; icon: typeof Check }
> = {
  Available: {
    cls: "border-emerald-500 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
    icon: Check,
  },
  Reserved: {
    cls: "border-violet-500 bg-violet-50 text-violet-900 dark:bg-violet-950 dark:text-violet-100",
    icon: CalendarClock,
  },
  Seated: {
    cls: "border-sky-500 bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100",
    icon: Users,
  },
  Ordering: {
    cls: "border-amber-500 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
    icon: ClipboardList,
  },
  Served: {
    cls: "border-teal-500 bg-teal-50 text-teal-900 dark:bg-teal-950 dark:text-teal-100",
    icon: Soup,
  },
  "Awaiting Payment": {
    cls: "border-orange-600 bg-orange-100 text-orange-950 dark:bg-orange-950 dark:text-orange-100",
    icon: ReceiptText,
  },
  Cleaning: {
    cls: "border-slate-400 bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100",
    icon: Brush,
  },
  "Out of Service": {
    cls: "border-zinc-400 border-dashed bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
    icon: Wrench,
  },
}

function TableTile({ t, onClick }: { t: FloorTable; onClick: () => void }) {
  const at = useClock()
  const label: TableState | "Out of Service" = t.outOfService
    ? "Out of Service"
    : t.state
  const s = stateStyle[label]
  return (
    <button
      onClick={onClick}
      style={{ left: `${t.x}%`, top: `${t.y}%` }}
      aria-label={`Table ${t.code}, ${label}`}
      className={cn(
        "absolute flex flex-col justify-between border-2 p-1.5 text-left shadow-sm transition-transform hover:scale-[1.03]",
        s.cls,
        t.shape === "round"
          ? "h-24 w-24 items-center rounded-full text-center"
          : t.shape === "rect"
            ? "h-24 w-44 rounded-xl"
            : "h-24 w-28 rounded-xl"
      )}
    >
      <span className="flex w-full items-center justify-between gap-1 font-bold">
        <span className={cn(t.shape === "round" && "mx-auto")}>{t.code}</span>
        {t.shape !== "round" && (
          <span className="flex items-center gap-1 text-[11px] font-medium">
            {t.flagged && <AlertTriangle className="size-3.5 text-danger" />}
            {t.server && initials(t.server)}
          </span>
        )}
      </span>
      <span className="text-[11px] leading-tight font-medium">
        <s.icon className="mr-0.5 inline size-3" aria-hidden />
        {label}
      </span>
      <span className="tabular text-[11px]">
        {t.guests > 0 ? `${t.guests}/${t.capacity}` : `${t.capacity} seats`}
        {t.seatedAt !== undefined && ` · ${minLabel(at - t.seatedAt)}`}
      </span>
    </button>
  )
}

export default function FloorPlanPage() {
  const { tables } = useRms()
  const router = useRouter()
  pos.useLiveSync()
  const areas = [...new Set(tables.map((t) => t.area))]
  const [pickedArea, setArea] = React.useState("")
  const area = areas.includes(pickedArea) ? pickedArea : (areas[0] ?? "")
  const [selId, setSelId] = React.useState<string | null>(null)
  const [guests, setGuests] = React.useState(2)
  const [mode, setMode] = React.useState<"main" | "transfer" | "combine">(
    "main"
  )
  const [target, setTarget] = React.useState("")
  const sel = tables.find((t) => t.id === selId)
  const close = () => {
    setSelId(null)
    setMode("main")
    setTarget("")
  }

  const active = tables.filter((t) => !t.outOfService)
  const occ = active.filter((t) =>
    ["Seated", "Ordering", "Served", "Awaiting Payment"].includes(t.state)
  )
  const seats = active.reduce((s, t) => s + t.capacity, 0)
  const seated = active.reduce((s, t) => s + t.guests, 0)
  const flagged = tables.filter((t) => t.flagged)
  const free = tables.filter(
    (t) => t.state === "Available" && !t.outOfService && t.id !== selId
  )

  /** Run a table action against the API; the server's message is shown if it refuses. */
  const act = (fn: () => Promise<unknown>, done?: string) => {
    close()
    fn().then(() => done && toast.success(done), pos.report)
  }

  const seat = () => {
    if (!sel) return
    const t = sel
    close()
    const go = (o: { overCapacity?: boolean; overrideReservation?: boolean }) =>
      pos.seatTable(t.id, guests, o).then(
        (orderId) => {
          toast.success(`Seated at ${t.code}`)
          router.push(orderId ? `/pos?order=${orderId}` : `/pos?table=${t.code}&guests=${guests}`)
        },
        (e) => {
          // The backend decides; ask before overriding, then try again.
          if (e instanceof ApiError && e.code === "OVER_CAPACITY")
            confirmAction({
              title: "Party is larger than this table",
              effect: `${e.message} Seat them anyway?`,
              confirmLabel: "Seat anyway",
              onConfirm: () => void go({ ...o, overCapacity: true }),
            })
          else if (e instanceof ApiError && e.code === "TABLE_RESERVED_SOON")
            confirmAction({
              title: "This table is reserved soon",
              effect: `${e.message} Seating a walk-in may delay that reservation.`,
              confirmLabel: "Seat anyway",
              onConfirm: () => void go({ ...o, overrideReservation: true }),
            })
          else pos.report(e)
        }
      )
    void go({})
  }

  return (
    <Page>
      <PageHeader
        title="Floor plan"
        description="Live table status. Select a table to seat guests, transfer, combine or take it out of service."
        actions={
          <LinkButton href="/tables/editor" variant="outline">
            <PencilRuler />
            Edit layout
          </LinkButton>
        }
      />
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Table occupancy"
          value={`${active.length ? Math.round((occ.length / active.length) * 100) : 0}%`}
          icon={Armchair}
          hint={`${occ.length} of ${active.length} tables`}
        />
        <Stat
          label="Seat occupancy"
          value={`${seats ? Math.round((seated / seats) * 100) : 0}%`}
          icon={Users}
          hint={`${seated} of ${seats} seats`}
        />
        <Stat
          label="Awaiting payment"
          value={tables.filter((t) => t.state === "Awaiting Payment").length}
          icon={ReceiptText}
        />
        <Stat
          label="Being cleaned"
          value={tables.filter((t) => t.state === "Cleaning").length}
          icon={Hourglass}
        />
      </section>
      {flagged.map((t) => (
        <Notice key={t.id} tone="danger">
          <span>
            Table {t.code} is Available but still linked to an open order.{" "}
            {t.orderId && (
              <Link className="underline" href={`/pos?order=${t.orderId}`}>
                Open the order to resolve it
              </Link>
            )}
          </span>
        </Notice>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg bg-muted p-1">
          {areas.map((a) => (
            <button
              key={a}
              aria-current={a === area ? "true" : undefined}
              onClick={() => setArea(a)}
              className={cn(
                "rounded-md px-3 py-1 text-sm font-medium",
                a === area ? "bg-background shadow-sm" : "text-muted-foreground"
              )}
            >
              {a}
            </button>
          ))}
        </div>
        <ul
          className="ml-auto flex flex-wrap gap-x-3 gap-y-1 text-xs"
          aria-label="Legend"
        >
          {Object.entries(stateStyle).map(([k, v]) => (
            <li key={k} className="flex items-center gap-1">
              <span
                className={cn(
                  "inline-flex size-4 items-center justify-center rounded border",
                  v.cls
                )}
              >
                <v.icon className="size-2.5" />
              </span>
              {k}
            </li>
          ))}
        </ul>
      </div>
      <div className="overflow-x-auto rounded-xl border bg-card">
        <div className="relative h-[520px] min-w-[840px] bg-[radial-gradient(var(--border)_1px,transparent_1px)] [background-size:20px_20px]">
          {tables
            .filter((t) => t.area === area)
            .map((t) => (
              <TableTile
                key={t.id}
                t={t}
                onClick={() => {
                  setSelId(t.id)
                  setGuests(Math.min(2, t.capacity))
                }}
              />
            ))}
        </div>
      </div>

      <Dialog open={!!sel} onOpenChange={(o) => !o && close()}>
        <DialogContent className="sm:max-w-md">
          {sel && (
            <>
              <DialogHeader>
                <DialogTitle>Table {sel.code}</DialogTitle>
                <DialogDescription>
                  {sel.outOfService
                    ? `Out of service: ${sel.outOfService}`
                    : `${sel.state} · ${sel.area} · ${sel.capacity} seats${sel.server ? ` · ${sel.server}` : ""}${sel.group ? ` · group ${sel.group}` : ""}`}
                </DialogDescription>
              </DialogHeader>
              {sel.upcoming && (
                <Notice tone="info">Upcoming: {sel.upcoming}</Notice>
              )}
              {mode !== "main" ? (
                <>
                  <FormRow
                    label={
                      mode === "transfer" ? "Move party to" : "Combine with"
                    }
                    required
                  >
                    <SimpleSelect
                      aria-label="Target table"
                      value={target}
                      onChange={setTarget}
                      options={opts(...free.map((t) => t.code))}
                      placeholder="Choose a table…"
                    />
                  </FormRow>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setMode("main")}>
                      Back
                    </Button>
                    <Button
                      disabled={!target}
                      onClick={() => {
                        const to = tables.find((t) => t.code === target)
                        if (!to) return
                        if (mode === "transfer") {
                          if (!sel.orderId) return toast.error("This table has no open order to move.")
                          act(() => pos.transfer(sel.orderId!, to.id), `Party moved to ${target}`)
                        } else act(() => pos.combineTables([sel.id, to.id]), `${sel.code} and ${target} combined`)
                      }}
                    >
                      {mode === "transfer" ? "Move party" : "Combine"}
                    </Button>
                  </DialogFooter>
                </>
              ) : sel.outOfService ? (
                <DialogFooter>
                  <Button
                    onClick={() => act(() => pos.returnToService(sel.id), "Back in service")}
                  >
                    Return to service
                  </Button>
                </DialogFooter>
              ) : (
                <>
                  {(sel.state === "Available" || sel.state === "Reserved") && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Guests</span>
                      <QuantityStepper
                        value={guests}
                        onChange={setGuests}
                        min={1}
                        size="lg"
                        label="guests"
                      />
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-2">
                    {(sel.state === "Available" ||
                      sel.state === "Reserved") && (
                      <Button className="col-span-2 h-11" onClick={seat}>
                        <UserRoundCheck />
                        Seat and open order
                      </Button>
                    )}
                    {[
                      "Seated",
                      "Ordering",
                      "Served",
                      "Awaiting Payment",
                    ].includes(sel.state) && (
                      <>
                        <Button
                          className="col-span-2 h-11"
                          onClick={() =>
                            router.push(
                              sel.orderId
                                ? `/pos?order=${sel.orderId}`
                                : `/pos?table=${sel.code}&guests=${sel.guests}`
                            )
                          }
                        >
                          <ClipboardList />
                          Open order
                        </Button>
                        <Button
                          variant="outline"
                          className="h-11"
                          onClick={() => setMode("transfer")}
                        >
                          Transfer party
                        </Button>
                        {sel.orderId && sel.state !== "Awaiting Payment" && (
                          <Button
                            variant="outline"
                            className="h-11"
                            onClick={() => act(() => pos.printBill(sel.orderId!), "Bill printed")}
                          >
                            Print bill
                          </Button>
                        )}
                      </>
                    )}
                    {sel.state === "Cleaning" && (
                      <Button
                        className="col-span-2 h-11"
                        onClick={() => act(() => pos.setTableState(sel.id, "Available"), `${sel.code} is available`)}
                      >
                        <Check />
                        Cleaning done
                      </Button>
                    )}
                    {sel.group ? (
                      <Button
                        variant="outline"
                        className="h-11"
                        onClick={() => act(() => pos.splitGroup(sel.group!), "Group split")}
                      >
                        Split group
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        className="h-11"
                        onClick={() => setMode("combine")}
                      >
                        <Combine />
                        Combine
                      </Button>
                    )}
                    {sel.state === "Available" && (
                      <Button
                        variant="destructive"
                        className="h-11"
                        onClick={() => {
                          const { code, id } = sel
                          close()
                          confirmAction({
                            title: `Take ${code} out of service?`,
                            effect:
                              "It can't be seated until it's returned to service.",
                            reasons: [
                              "Broken furniture",
                              "Maintenance",
                              "Private event",
                            ],
                            destructive: true,
                            confirmLabel: "Take out of service",
                            onConfirm: (r) => act(() => pos.outOfService(id, r), `${code} is out of service`),
                          })
                        }}
                      >
                        <Ban />
                        Out of service
                      </Button>
                    )}
                  </div>
                </>
              )}
              <Link
                href="/reservations"
                className="text-center text-xs text-muted-foreground hover:underline"
              >
                View reservations
              </Link>
            </>
          )}
        </DialogContent>
      </Dialog>
    </Page>
  )
}
