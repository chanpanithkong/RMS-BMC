"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  Ban,
  BellRing,
  Check,
  Pencil,
  Plus,
  UserRoundCheck,
  UserX,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { RecordDialog, newId, type Field } from "@/components/rms/crud"
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
import { BUSINESS_DATE } from "@/lib/rms/seed"
import { rms, useRms } from "@/lib/rms/store"
import type { Reservation } from "@/lib/rms/types"
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
const barTone: Record<Reservation["status"], string> = {
  Requested: "bg-warning-soft text-warning border-warning",
  Confirmed: "bg-info-soft text-info border-info",
  Seated: "bg-success-soft text-success border-success",
  Completed: "bg-muted text-muted-foreground",
  Cancelled: "bg-muted text-muted-foreground line-through",
  "No-show": "bg-danger-soft text-danger border-danger",
}

export default function ReservationsPage() {
  const { reservations, waitlist, tables, userName } = useRms()
  const router = useRouter()
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
        r.table === table &&
        !["Cancelled", "No-show", "Completed"].includes(r.status) &&
        start < r.start + r.duration &&
        r.start < start + duration
    )
  const fields: Field[] = [
    { name: "name", label: "Customer name", required: true, half: true },
    { name: "phone", label: "Phone", type: "tel", required: true, half: true },
    {
      name: "party",
      label: "Party size",
      type: "number",
      required: true,
      min: 1,
      max: 20,
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
  const seat = (r: Reservation) => {
    if (!r.table) {
      toast.error("Assign a table first")
      return
    }
    rms.setReservationStatus(r.id, "Seated")
    rms.seat(r.table, r.party, userName.split(" ")[0])
    toast.success(`${r.name} seated at ${r.table}`)
    router.push(`/pos?table=${r.table}&guests=${r.party}`)
  }
  const cancel = (r: Reservation) =>
    confirmAction({
      title: `Cancel ${r.name}'s reservation?`,
      effect: "The table hold is released.",
      reasons: ["Customer request", "Duplicate", "Restaurant closed"],
      destructive: true,
      confirmLabel: "Cancel reservation",
      onConfirm: () => {
        rms.setReservationStatus(r.id, "Cancelled")
        toast.success("Reservation cancelled")
      },
    })
  const actions = (r: Reservation) => [
    {
      label: "Seat now",
      icon: UserRoundCheck,
      onClick: seat,
      hidden: () => !["Confirmed", "Requested"].includes(r.status),
    },
    {
      label: "Confirm",
      icon: Check,
      onClick: () => rms.setReservationStatus(r.id, "Confirmed"),
      hidden: () => r.status !== "Requested",
    },
    {
      label: "Edit",
      icon: Pencil,
      onClick: (x: Reservation) => {
        setEdit(x)
        setOpen(true)
      },
      hidden: () => !["Confirmed", "Requested"].includes(r.status),
    },
    {
      label: "Mark no-show",
      icon: UserX,
      onClick: () => rms.setReservationStatus(r.id, "No-show"),
      hidden: () => r.status !== "Confirmed",
    },
    {
      label: "Cancel",
      icon: Ban,
      destructive: true,
      onClick: cancel,
      hidden: () => !["Confirmed", "Requested"].includes(r.status),
    },
  ]
  const waiting = waitlist.filter(
    (w) => w.status === "Waiting" || w.status === "Notified"
  )
  return (
    <Page>
      <PageHeader
        title="Reservations"
        description={`${BUSINESS_DATE}. Each table can hold only one reservation per time window.`}
        actions={
          <>
            <Button variant="outline" onClick={() => setWaitOpen(true)}>
              <Plus />
              Add to waiting list
            </Button>
            <Button
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
                        setEdit(null)
                        setTablePick({ code: t.code, start: s })
                        setOpen(true)
                      }}
                    />
                  ))}
                  {reservations
                    .filter(
                      (r) => r.table === t.code && r.status !== "Cancelled"
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
                        onClick={() => {
                          rms.setWait(w.id, "Notified")
                          toast.success(`${w.name} notified`)
                        }}
                      >
                        <BellRing />
                      </Button>
                    ) : (
                      <Button
                        size="icon-sm"
                        aria-label={`Seat ${w.name}`}
                        onClick={() => {
                          rms.setWait(w.id, "Seated")
                          router.push("/tables")
                        }}
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
              onClick: () => rms.setWait(w.id, "Notified"),
              hidden: () => w.status !== "Waiting",
            },
            {
              label: "Seat",
              icon: UserRoundCheck,
              onClick: () => rms.setWait(w.id, "Seated"),
              hidden: () => w.status === "Seated" || w.status === "Left",
            },
            {
              label: "Mark left",
              icon: UserX,
              destructive: true,
              onClick: () => rms.setWait(w.id, "Left"),
              hidden: () => w.status === "Seated" || w.status === "Left",
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
        onSubmit={(v) => {
          rms.saveReservation({
            id: edit?.id ?? newId(),
            name: String(v.name),
            phone: String(v.phone),
            party: Number(v.party),
            date: BUSINESS_DATE,
            start: parse(String(v.time)),
            duration: Number(v.duration),
            table: v.table ? String(v.table) : undefined,
            status: edit?.status ?? "Confirmed",
            notes: String(v.notes ?? ""),
          })
          toast.success("Reservation saved")
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
            required: true,
            half: true,
            hint: "Estimated: 15 min",
          },
        ]}
        initial={{ quoted: "15" }}
        onSubmit={(v) => {
          rms.addWait({
            id: newId(),
            name: String(v.name),
            party: Number(v.party),
            phone: String(v.phone ?? ""),
            added: "13:02",
            quoted: Number(v.quoted),
            status: "Waiting",
          })
          toast.success("Added to waiting list")
        }}
      />
    </Page>
  )
}
