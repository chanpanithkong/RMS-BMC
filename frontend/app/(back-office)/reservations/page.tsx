"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { Ban, BellRing, Pencil, Plus, UserRoundCheck, UserX } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { RecordDialog, type Field } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  Page,
  PageHeader,
  PageTabs,
  Panel,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { can, useSession } from "@/lib/api/session"
import { act, apiMessage, save, useApi } from "@/lib/api/use-api"
import { cn } from "@/lib/utils"

const OPEN = 11,
  CLOSE = 22
const slots = Array.from({ length: (CLOSE - OPEN) * 2 }, (_, i) => OPEN + i / 2)
const fmt = (h: number) =>
  `${String(Math.floor(h)).padStart(2, "0")}:${h % 1 ? "30" : "00"}`
const parse = (t: string) => {
  const [h, m] = t.split(":").map(Number)
  return h + (m >= 30 ? 0.5 : 0)
}
interface Reservation {
  id: string
  name: string
  phone: string
  party: number
  date: string
  start: number
  duration: number
  table?: string
  tableIds: string[]
  status: "Requested" | "Confirmed" | "Seated" | "Completed" | "Cancelled" | "No-show"
  notes: string
  version: number
}
interface ApiReservation {
  id: string
  guest_name: string
  guest_phone: string | null
  reserved_at: string
  party_size: number
  duration_minutes: number
  status: string
  notes: string | null
  table_ids: string[]
  version: number
}
interface Wait {
  id: string
  name: string
  party: number
  phone: string
  added: string
  quoted: number
  status: string
}
interface Table {
  id: string
  table_code: string
  capacity: number
  is_out_of_service: boolean
}

/** Local date + "HH:MM" -> ISO time. */
const at = (day: string, time: string) => new Date(`${day}T${time}`).toISOString()

async function loadDay(day: string) {
  const [rs, tables, waits] = await Promise.all([
    api<ApiReservation[]>("GET", "/reservations", { query: { on: day } }),
    api<Table[]>("GET", "/tables"),
    api<{ id: string; party_name: string; party_size: number; phone: string | null; quoted_minutes: number | null; status: string; added_at: string }[]>("GET", "/waitlist", {
      query: { include_closed: true },
    }),
  ])
  const code = Object.fromEntries(tables.map((t) => [t.id, t.table_code]))
  const reservations: Reservation[] = rs.map((r) => {
    const d = new Date(r.reserved_at)
    return {
      id: r.id,
      name: r.guest_name,
      phone: r.guest_phone ?? "",
      party: r.party_size,
      date: d.toLocaleDateString("en-CA"),
      start: d.getHours() + d.getMinutes() / 60,
      duration: r.duration_minutes / 60,
      table: r.table_ids.map((t) => code[t]).filter(Boolean).join("+") || undefined,
      tableIds: r.table_ids,
      status: (r.status === "NoShow" ? "No-show" : r.status) as Reservation["status"],
      notes: r.notes ?? "",
      version: r.version,
    }
  })
  const waitlist: Wait[] = waits.map((w) => ({
    id: w.id,
    name: w.party_name,
    party: w.party_size,
    phone: w.phone ?? "",
    added: new Date(w.added_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }),
    quoted: w.quoted_minutes ?? 0,
    status: w.status,
  }))
  return { reservations, waitlist, tables }
}

const barTone: Record<Reservation["status"], string> = {
  Requested: "bg-warning-soft text-warning border-warning",
  Confirmed: "bg-info-soft text-info border-info",
  Seated: "bg-success-soft text-success border-success",
  Completed: "bg-muted text-muted-foreground",
  Cancelled: "bg-muted text-muted-foreground line-through",
  "No-show": "bg-danger-soft text-danger border-danger",
}

export default function ReservationsPage() {
  const router = useRouter()
  const { me } = useSession()
  const manage = can(me, "reservations.manage")
  const [day, setDay] = React.useState("")
  const shownDay = day || me?.business_date || new Date().toLocaleDateString("en-CA")
  const { data, reload } = useApi(() => loadDay(shownDay), [shownDay], { reservations: [] as Reservation[], waitlist: [] as Wait[], tables: [] as Table[] })
  const { reservations, waitlist } = data
  const tables = data.tables.map((t) => ({ id: t.id, code: t.table_code, capacity: t.capacity, outOfService: t.is_out_of_service }))
  const [tab, setTab] = useTab("timeline")
  const [edit, setEdit] = React.useState<Reservation | null>(null)
  const [open, setOpen] = React.useState(false)
  const [waitOpen, setWaitOpen] = React.useState(false)
  const [tablePick, setTablePick] = React.useState<{
    code: string
    start: number
  } | null>(null)
  const list = tables.filter((t) => !t.outOfService)

  const conflict = (
    table: string,
    start: number,
    duration: number,
    id?: string
  ) =>
    reservations.find(
      (r) =>
        r.id !== id &&
        (r.table ?? "").split("+").includes(table) &&
        !["Cancelled", "No-show", "Completed"].includes(r.status) &&
        start < r.start + r.duration &&
        r.start < start + duration
    )
  const fields: Field[] = [
    { name: "name", label: "Customer name", required: true, half: true },
    { name: "phone", label: "Phone", type: "tel", half: true },
    {
      name: "party",
      label: "Party size",
      type: "number",
      required: true,
      min: 1,
      half: true,
    },
    {
      name: "time",
      label: "Time",
      type: "time",
      required: true,
      half: true,
      validate: (v) => {
        const h = parse(String(v))
        return v && (h < OPEN || h >= CLOSE)
          ? `Open ${OPEN}:00–${CLOSE}:00`
          : undefined
      },
    },
    {
      name: "duration",
      label: "Dining duration (hours)",
      type: "select",
      options: ["1", "1.5", "2", "2.5", "3"],
      required: true,
      half: true,
    },
    {
      name: "table",
      label: "Table (optional)",
      type: "select",
      options: list.map((t) => t.code),
      half: true,
      validate: (v, all) => {
        if (!v) return undefined
        const c = conflict(
          String(v),
          parse(String(all.time)),
          Number(all.duration || 1.5),
          edit?.id
        )
        if (c) return `Conflicts with ${c.name} at ${fmt(c.start)}`
        const t = tables.find((x) => x.code === v)
        return t && Number(all.party) > t.capacity
          ? `Seats only ${t.capacity}`
          : undefined
      },
    },
    { name: "notes", label: "Special requests", type: "textarea" },
  ]
  // The server checks capacity, table-time conflicts and status rules; its message is shown if it refuses.
  const seat = (r: Reservation) =>
    void act(
      async () => {
        const out = await api<{ order_id: string }>("POST", `/reservations/${r.id}/seat`)
        router.push(`/pos?order=${out.order_id}`)
      },
      `${r.name} seated`,
      reload
    )
  const cancel = (r: Reservation) =>
    confirmAction({
      title: `Cancel ${r.name}'s reservation?`,
      effect: "The table hold is released.",
      reasons: ["Customer request", "Duplicate", "Restaurant closed"],
      destructive: true,
      confirmLabel: "Cancel reservation",
      onConfirm: (reason) => void act(() => api("POST", `/reservations/${r.id}/cancel`, { body: { reason } }), "Reservation cancelled", reload),
    })
  const actions = (r: Reservation) => [
    {
      label: "Seat now",
      icon: UserRoundCheck,
      onClick: () => seat(r),
      hidden: () => !manage || !["Confirmed", "Requested"].includes(r.status),
    },
    {
      label: "Edit",
      icon: Pencil,
      onClick: (x: Reservation) => {
        setEdit(x)
        setOpen(true)
      },
      hidden: () => !manage || !["Confirmed", "Requested"].includes(r.status),
    },
    {
      label: "Mark no-show",
      icon: UserX,
      onClick: () => void act(() => api("POST", `/reservations/${r.id}/no-show`), `${r.name} marked as no-show`, reload),
      hidden: () => !manage || !["Confirmed", "Requested"].includes(r.status),
    },
    {
      label: "Cancel",
      icon: Ban,
      destructive: true,
      onClick: cancel,
      hidden: () => !manage || !["Confirmed", "Requested"].includes(r.status),
    },
  ]
  const waitAction = (w: Wait, action: "notify" | "seat" | "left", done: string) =>
    void act(() => api("POST", `/waitlist/${w.id}/${action}`), done, () => {
      reload()
      if (action === "seat") router.push("/tables")
    })
  const waiting = waitlist.filter(
    (w) => w.status === "Waiting" || w.status === "Notified"
  )
  return (
    <Page>
      <PageHeader
        title="Reservations"
        description="Each table can hold only one reservation per time window."
        actions={
          <>
            <input
              type="date"
              aria-label="Day"
              className="h-9 rounded-md border bg-transparent px-2 text-sm"
              value={shownDay}
              onChange={(e) => setDay(e.target.value)}
            />
            <Button variant="outline" disabled={!manage} onClick={() => setWaitOpen(true)}>
              <Plus />
              Add to waiting list
            </Button>
            <Button
              disabled={!manage}
              onClick={() => {
                setEdit(null)
                setTablePick(null)
                setOpen(true)
              }}
            >
              <Plus />
              New reservation
            </Button>
          </>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "timeline", label: "Timeline" },
          { value: "list", label: "List", count: reservations.length },
          { value: "waiting", label: "Waiting list", count: waiting.length },
        ]}
      />
      {tab === "timeline" && (
        <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[1fr_280px]">
          <div className="overflow-auto rounded-xl border bg-card">
            <div className="min-w-[1120px]">
              <div
                className="sticky top-0 z-10 grid border-b bg-muted text-xs font-medium"
                style={{
                  gridTemplateColumns: `72px repeat(${slots.length}, 1fr)`,
                }}
              >
                <div className="p-2">Table</div>
                {slots.map((s) => (
                  <div key={s} className="tabular border-l p-2 text-center">
                    {s % 1 ? "" : fmt(s)}
                  </div>
                ))}
              </div>
              {list.map((t) => (
                <div
                  key={t.id}
                  className="relative grid h-11 border-b last:border-0"
                  style={{
                    gridTemplateColumns: `72px repeat(${slots.length}, 1fr)`,
                  }}
                >
                  <div className="flex items-center gap-1 p-2 text-sm font-medium">
                    {t.code}
                    <span className="tabular text-xs font-normal text-muted-foreground">
                      {t.capacity}
                    </span>
                  </div>
                  {slots.map((s) => (
                    <button
                      key={s}
                      aria-label={`Reserve ${t.code} at ${fmt(s)}`}
                      className="border-l hover:bg-accent/40"
                      onClick={() => {
                        if (!manage) return
                        setEdit(null)
                        setTablePick({ code: t.code, start: s })
                        setOpen(true)
                      }}
                    />
                  ))}
                  {reservations
                    .filter(
                      (r) => r.tableIds.includes(t.id) && r.status !== "Cancelled"
                    )
                    .map((r) => {
                      const cell = `((100% - 72px) / ${slots.length})`
                      return (
                        <button
                          key={r.id}
                          onClick={() => {
                            setEdit(r)
                            setOpen(true)
                          }}
                          title={`${r.name} · ${r.party} pax · ${r.status}`}
                          className={cn(
                            "absolute top-1 bottom-1 truncate rounded-md border px-1.5 text-left text-xs font-medium",
                            barTone[r.status]
                          )}
                          style={{
                            left: `calc(72px + ${(r.start - OPEN) * 2} * ${cell})`,
                            width: `calc(${r.duration * 2} * ${cell})`,
                          }}
                        >
                          {r.name} · {r.party}
                        </button>
                      )
                    })}
                </div>
              ))}
            </div>
          </div>
          <Panel
            title="Waiting list"
            description="Estimated from current table turn times"
          >
            <ul className="divide-y text-sm">
              {waiting.length === 0 && (
                <li className="py-3 text-muted-foreground">
                  Nobody is waiting.
                </li>
              )}
              {waiting.map((w) => (
                <li
                  key={w.id}
                  className="flex items-center justify-between gap-2 py-2"
                >
                  <span>
                    <span className="font-medium">{w.name}</span>{" "}
                    <span className="text-muted-foreground">
                      · {w.party} pax
                    </span>
                    <span className="tabular block text-xs text-muted-foreground">
                      Added {w.added} · quoted {w.quoted} min
                    </span>
                  </span>
                  <span className="flex gap-1">
                    {w.status === "Waiting" ? (
                      <Button
                        size="icon-sm"
                        variant="outline"
                        aria-label={`Notify ${w.name}`}
                        onClick={() => waitAction(w, "notify", `${w.name} notified`)}
                      >
                        <BellRing />
                      </Button>
                    ) : (
                      <Button
                        size="icon-sm"
                        aria-label={`Seat ${w.name}`}
                        onClick={() => waitAction(w, "seat", `${w.name} seated`)}
                      >
                        <UserRoundCheck />
                      </Button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      )}
      {tab === "list" && (
        <DataTable
          rows={reservations}
          exportName="reservations"
          rowActions={actions}
          filters={[
            {
              key: "status",
              label: "Status",
              options: [
                "Requested",
                "Confirmed",
                "Seated",
                "Completed",
                "Cancelled",
                "No-show",
              ],
            },
          ]}
          columns={[
            { key: "name", header: "Customer" },
            { key: "phone", header: "Phone" },
            { key: "date", header: "Date" },
            {
              key: "start",
              header: "Time",
              align: "right",
              render: (r) => fmt(r.start),
            },
            { key: "party", header: "Party", align: "right" },
            { key: "table", header: "Table" },
            { key: "notes", header: "Requests" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
        />
      )}
      {tab === "waiting" && (
        <DataTable
          rows={waitlist}
          exportName="waiting-list"
          rowActions={(w) => [
            {
              label: "Notify",
              icon: BellRing,
              onClick: () => waitAction(w, "notify", `${w.name} notified`),
              hidden: () => !manage || w.status !== "Waiting",
            },
            {
              label: "Seat",
              icon: UserRoundCheck,
              onClick: () => waitAction(w, "seat", `${w.name} seated`),
              hidden: () => !manage || w.status === "Seated" || w.status === "Left",
            },
            {
              label: "Mark left",
              icon: UserX,
              destructive: true,
              onClick: () => waitAction(w, "left", `${w.name} marked as left`),
              hidden: () => !manage || w.status === "Seated" || w.status === "Left",
            },
          ]}
          columns={[
            { key: "name", header: "Party" },
            { key: "party", header: "Size", align: "right" },
            { key: "phone", header: "Phone" },
            { key: "added", header: "Added" },
            { key: "quoted", header: "Quoted (min)", align: "right" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
        />
      )}
      <RecordDialog
        open={open}
        onOpenChange={setOpen}
        title={edit ? `Reservation · ${edit.name}` : "New reservation"}
        fields={fields}
        wide
        initial={
          edit
            ? {
                name: edit.name,
                phone: edit.phone,
                party: String(edit.party),
                time: fmt(edit.start),
                duration: String(edit.duration),
                table: edit.table ?? "",
                notes: edit.notes ?? "",
              }
            : {
                duration: "1.5",
                party: "2",
                table: tablePick?.code ?? "",
                time: tablePick ? fmt(tablePick.start) : "",
              }
        }
        onSubmit={async (v) => {
          const table = tables.find((t) => t.code === v.table)
          const body = {
            guest_name: String(v.name),
            guest_phone: String(v.phone ?? "") || null,
            party_size: Number(v.party),
            reserved_at: at(edit?.date ?? shownDay, String(v.time)),
            duration_minutes: Math.round(Number(v.duration) * 60),
            table_ids: table ? [table.id] : [],
            notes: String(v.notes ?? "") || null,
          }
          try {
            if (edit) await api("PATCH", `/reservations/${edit.id}`, { body })
            else await api("POST", "/reservations", { body })
          } catch (e) {
            throw new Error(apiMessage(e))
          }
          toast.success("Reservation saved")
          reload()
        }}
      />
      <RecordDialog
        open={waitOpen}
        onOpenChange={setWaitOpen}
        title="Add to waiting list"
        fields={[
          { name: "name", label: "Party name", required: true, half: true },
          {
            name: "party",
            label: "Party size",
            type: "number",
            required: true,
            min: 1,
            half: true,
          },
          { name: "phone", label: "Phone", type: "tel", half: true },
          {
            name: "quoted",
            label: "Quoted wait (min)",
            type: "number",
            half: true,
            hint: "Leave empty to estimate from current table turn times",
          },
        ]}
        initial={{}}
        onSubmit={(v) =>
          save(() =>
            api("POST", "/waitlist", {
              body: { party_name: String(v.name), party_size: Number(v.party), phone: String(v.phone ?? "") || undefined, quoted_minutes: v.quoted ? Number(v.quoted) : undefined },
            })
          ).then(() => {
            toast.success("Added to waiting list")
            reload()
          })
        }
      />
    </Page>
  )
}
