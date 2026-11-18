"use client"

import * as React from "react"
import { Activity, Ban, CalendarPlus, Check, LogIn, LogOut, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { CrudTable, RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { KV, Page, PageHeader, PageTabs, Panel, SimpleSelect, StatusBadge, useTab } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { can, useSession } from "@/lib/api/session"
import { act, num, save, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

interface Employee {
  id: string
  employee_code: string
  name_en: string
  name_km: string | null
  department_id: string | null
  position_id: string | null
  status: string
  start_date: string
  phone: string | null
  user_id: string | null
}
interface Named {
  id: string
  name: string
  is_active: boolean
}
interface Shift {
  id: string
  employee_id: string
  employee: string
  shift_date: string
  start_time: string
  end_time: string
  note: string | null
}

const monday = (d = new Date()) => {
  const x = new Date(d)
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7))
  return x.toLocaleDateString("en-CA")
}

export default function EmployeesPage() {
  const { me } = useSession()
  const manage = can(me, "employees.manage")
  const [tab, setTab] = useTab("employees")
  const emps = useApi(() => api<Employee[]>("GET", "/employees"), [], [])
  const depts = useApi(() => api<Named[]>("GET", "/departments"), [], [])
  const positions = useApi(() => api<Named[]>("GET", "/positions"), [], [])
  const users = useApi(
    async () => (can(me, "users.view") ? (await api<{ data: { id: string; full_name: string; username: string }[] }>("GET", "/users", { query: { page_size: 200 } })).data : []),
    [me?.id],
    []
  )
  const [week, setWeek] = React.useState(monday())
  const shifts = useApi(() => api<Shift[]>("GET", "/shift-schedules", { query: { week_start: week } }), [week], [])
  const attendance = useApi(
    () => api<{ id: string; employee: string; employee_code: string; clock_in: string; clock_out: string | null; hours: number | null }[]>("GET", "/attendance"),
    [tab === "attendance"],
    []
  )
  const [actFor, setActFor] = React.useState("")
  const activity = useApi(
    () => (actFor ? api<Record<string, unknown>>("GET", `/employees/${actFor}/activity`) : Promise.resolve(null)),
    [actFor],
    null as Record<string, unknown> | null
  )
  const [addShift, setAddShift] = React.useState(false)
  const name = (list: Named[], id: string | null) => list.find((x) => x.id === id)?.name ?? "—"
  const byName = (list: Named[], n: unknown) => list.find((x) => x.name === n)?.id ?? null
  const userLabel = (u: { full_name: string; username: string }) => `${u.full_name} (${u.username})`

  const rows = emps.data.map((e) => ({
    ...e,
    department: name(depts.data, e.department_id),
    position: name(positions.data, e.position_id),
    account: users.data.find((u) => u.id === e.user_id)?.username ?? (e.user_id ? "Linked" : "—"),
  }))
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(`${week}T00:00`)
    d.setDate(d.getDate() + i)
    return d.toLocaleDateString("en-CA")
  })

  return (
    <Page>
      <PageHeader title="Employees" description="Staff records, shift schedules and attendance. An employee can be linked to one user account." />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "employees", label: "Employees", count: rows.length },
          { value: "schedule", label: "Schedule" },
          { value: "attendance", label: "Attendance" },
          { value: "departments", label: "Departments" },
          { value: "positions", label: "Positions" },
          { value: "activity", label: "Activity" },
        ]}
      />
      {tab === "employees" && (
        <CrudTable
          noun="Employee"
          rows={rows}
          canAdd={manage}
          canEdit={manage}
          onSave={(v, e) => {
            const user = users.data.find((u) => userLabel(u) === v.user)
            const common = {
              name_en: v.name,
              name_km: String(v.km ?? "") || null,
              department_id: byName(depts.data, v.department),
              position_id: byName(positions.data, v.position),
              phone: String(v.phone ?? "") || null,
              user_id: user?.id ?? null,
            }
            return save(() =>
              e ? api("PATCH", `/employees/${e.id}`, { body: common }) : api("POST", "/employees", { body: { ...common, employee_code: v.code, start_date: v.start } })
            ).then(emps.reload)
          }}
          filters={[
            { key: "department", label: "Department", options: depts.data.map((d) => d.name) },
            { key: "status", label: "Status", options: ["Active", "Inactive"] },
          ]}
          columns={[
            { key: "employee_code", header: "Code" },
            { key: "name_en", header: "Name", render: (e) => <span className="font-medium">{e.name_en}</span> },
            { key: "department", header: "Department" },
            { key: "position", header: "Position" },
            { key: "phone", header: "Phone", render: (e) => e.phone ?? "—" },
            { key: "start_date", header: "Started" },
            { key: "account", header: "User account" },
            { key: "status", header: "Status", render: (e) => <StatusBadge status={e.status} /> },
          ]}
          fields={[
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", half: true },
            { name: "code", label: "Employee code (can't change later)", required: true, half: true },
            { name: "start", label: "Start date (new employees)", type: "date", half: true },
            { name: "department", label: "Department", type: "select", options: depts.data.filter((d) => d.is_active).map((d) => d.name), half: true },
            { name: "position", label: "Position", type: "select", options: positions.data.filter((p) => p.is_active).map((p) => p.name), half: true },
            { name: "phone", label: "Phone", type: "tel", half: true },
            { name: "user", label: "User account", type: "select", options: users.data.map(userLabel), half: true },
          ]}
          toForm={(e) => ({
            name: e.name_en,
            km: e.name_km ?? "",
            code: e.employee_code,
            start: e.start_date,
            department: e.department === "—" ? "" : e.department,
            position: e.position === "—" ? "" : e.position,
            phone: e.phone ?? "",
            user: (() => {
              const u = users.data.find((x) => x.id === e.user_id)
              return u ? userLabel(u) : ""
            })(),
          })}
          extraActions={(e) => [
            { label: "Clock in", icon: LogIn, hidden: () => e.status !== "Active", onClick: () => void act(() => api("POST", `/employees/${e.id}/clock-in`), `${e.name_en} clocked in`) },
            { label: "Clock out", icon: LogOut, hidden: () => e.status !== "Active", onClick: () => void act(() => api("POST", `/employees/${e.id}/clock-out`), `${e.name_en} clocked out`) },
            {
              label: "Activity",
              icon: Activity,
              onClick: () => {
                setActFor(e.id)
                setTab("activity")
              },
            },
            ...(manage
              ? [
                  e.status === "Active"
                    ? {
                        label: "Deactivate",
                        icon: Ban,
                        destructive: true,
                        onClick: () => void act(() => api("PATCH", `/employees/${e.id}`, { body: { status: "Inactive" } }), `${e.name_en} deactivated (and the linked user)`, emps.reload),
                      }
                    : { label: "Activate", icon: Check, onClick: () => void act(() => api("PATCH", `/employees/${e.id}`, { body: { status: "Active" } }), `${e.name_en} activated`, emps.reload) },
                ]
              : []),
          ]}
        />
      )}
      {tab === "schedule" && (
        <Panel
          title={`Week of ${week}`}
          actions={
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setWeek(monday(new Date(new Date(`${week}T00:00`).getTime() - 7 * 86_400_000)))}>
                Previous
              </Button>
              <Button variant="outline" size="sm" onClick={() => setWeek(monday())}>
                This week
              </Button>
              <Button variant="outline" size="sm" onClick={() => setWeek(monday(new Date(new Date(`${week}T00:00`).getTime() + 7 * 86_400_000)))}>
                Next
              </Button>
              {manage && (
                <Button size="sm" onClick={() => setAddShift(true)}>
                  <CalendarPlus />
                  Add shift
                </Button>
              )}
            </div>
          }
        >
          <div className="grid gap-2 md:grid-cols-7">
            {days.map((d) => (
              <div key={d} className="min-h-28 rounded-lg border p-2">
                <p className="mb-1 text-xs font-medium text-muted-foreground">{new Date(`${d}T00:00`).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}</p>
                <ul className="grid gap-1">
                  {shifts.data
                    .filter((s) => s.shift_date === d)
                    .map((s) => (
                      <li key={s.id} className="flex items-start justify-between gap-1 rounded bg-muted px-1.5 py-1 text-xs">
                        <span>
                          <span className="font-medium">{s.employee}</span>
                          <span className="block tabular">
                            {s.start_time.slice(0, 5)}–{s.end_time.slice(0, 5)}
                          </span>
                          {s.note && <span className="block text-muted-foreground">{s.note}</span>}
                        </span>
                        {manage && (
                          <button
                            aria-label={`Remove ${s.employee}'s shift`}
                            className="text-muted-foreground hover:text-danger"
                            onClick={() => void act(() => api("DELETE", `/shift-schedules/${s.id}`), "Shift removed", shifts.reload)}
                          >
                            <Trash2 className="size-3.5" />
                          </button>
                        )}
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        </Panel>
      )}
      {tab === "attendance" && (
        <DataTable
          rows={attendance.data.map((a) => ({ ...a, in: when(a.clock_in), out: a.clock_out ? when(a.clock_out) : "Still clocked in" }))}
          exportName="attendance"
          emptyTitle="No attendance in the last two weeks"
          filters={[{ key: "employee", label: "Employee" }]}
          columns={[
            { key: "employee", header: "Employee" },
            { key: "in", header: "Clock in" },
            { key: "out", header: "Clock out" },
            { key: "hours", header: "Hours", align: "right", render: (a) => (a.hours === null ? "—" : a.hours.toFixed(2)) },
          ]}
        />
      )}
      {tab === "departments" && (
        <CrudTable
          noun="Department"
          rows={depts.data.map((d) => ({ ...d, status: d.is_active ? "Active" : "Inactive" }))}
          canAdd={manage}
          canEdit={false}
          onSave={(v) => save(() => api("POST", "/departments", { body: { name: v.name } })).then(depts.reload)}
          columns={[
            { key: "name", header: "Department" },
            { key: "people", header: "Employees", align: "right", value: (d) => emps.data.filter((e) => e.department_id === d.id).length },
            { key: "status", header: "Status", render: (d) => <StatusBadge status={d.status} /> },
          ]}
          fields={[{ name: "name", label: "Name", required: true }]}
        />
      )}
      {tab === "positions" && (
        <CrudTable
          noun="Position"
          rows={positions.data.map((p) => ({ ...p, status: p.is_active ? "Active" : "Inactive" }))}
          canAdd={manage}
          canEdit={false}
          onSave={(v) => save(() => api("POST", "/positions", { body: { name: v.name } })).then(positions.reload)}
          columns={[
            { key: "name", header: "Position" },
            { key: "people", header: "Employees", align: "right", value: (p) => emps.data.filter((e) => e.position_id === p.id).length },
            { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
          ]}
          fields={[{ name: "name", label: "Name", required: true }]}
        />
      )}
      {tab === "activity" && (
        <Panel title="Activity in the last 30 days" description="Taken from the user account linked to the employee." className="max-w-xl">
          <SimpleSelect
            aria-label="Employee"
            value={actFor}
            onChange={setActFor}
            options={emps.data.map((e) => ({ value: e.id, label: `${e.name_en} (${e.employee_code})` }))}
            placeholder="Choose an employee…"
          />
          {actFor && activity.data && (
            <div className="mt-3">
              {activity.data.linked_user ? (
                <KV
                  items={[
                    ["Period", `${activity.data.from} – ${activity.data.to}`],
                    ["Cashier sessions", String(activity.data.cashier_sessions)],
                    ["Orders served", String(activity.data.orders_served)],
                    ["Payments taken", usd(num(activity.data.payments_taken_base))],
                    ["Voided items", String(activity.data.voids)],
                    ["Discounts requested", String(activity.data.discounts)],
                    ["Refunds requested", String(activity.data.refunds_requested)],
                  ]}
                />
              ) : (
                <p className="text-sm text-muted-foreground">This employee has no linked user account, so there is no system activity.</p>
              )}
            </div>
          )}
        </Panel>
      )}
      <RecordDialog
        open={addShift}
        onOpenChange={setAddShift}
        title="Add shift"
        description="Overlapping shifts for the same person are refused."
        fields={[
          { name: "employee", label: "Employee", type: "select", options: emps.data.filter((e) => e.status === "Active").map((e) => e.name_en), required: true },
          { name: "date", label: "Date", type: "date", required: true, half: true },
          { name: "note", label: "Note", half: true },
          { name: "start", label: "Start", type: "time", required: true, half: true },
          { name: "end", label: "End", type: "time", required: true, half: true },
        ]}
        initial={{ date: week }}
        onSubmit={(v) =>
          save(() =>
            api("POST", "/shift-schedules", {
              body: {
                employee_id: emps.data.find((e) => e.name_en === v.employee)!.id,
                shift_date: v.date,
                start_time: v.start,
                end_time: v.end,
                note: String(v.note ?? "") || undefined,
              },
            })
          ).then(shifts.reload)
        }
      />
    </Page>
  )
}
