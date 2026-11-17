"use client"

import * as React from "react"
import { CalendarPlus } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { CrudTable, RecordDialog, newId } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import {
  Page,
  PageHeader,
  PageTabs,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import { employees } from "@/lib/rms/back-office"
import { cn } from "@/lib/utils"

const days = [
  "Mon 02",
  "Tue 03",
  "Wed 04",
  "Thu 05",
  "Fri 06",
  "Sat 07",
  "Sun 08",
]
const shiftTone: Record<string, string> = {
  Morning: "bg-info-soft text-info",
  Evening: "bg-warning-soft text-warning",
  Split: "bg-success-soft text-success",
}
const initialSchedule = (): Record<string, string[]> =>
  Object.fromEntries(
    employees
      .slice(0, 9)
      .map((e, i) => [
        e.id,
        days.map((_, d) =>
          (i + d) % 6 === 5
            ? "Off"
            : (i + d) % 3 === 0
              ? "Evening"
              : (i * d) % 5 === 4
                ? "Split"
                : "Morning"
        ),
      ])
  )

export default function EmployeesPage() {
  const [tab, setTab] = useTab("employees")
  const [schedule, setSchedule] = React.useState(initialSchedule)
  const [open, setOpen] = React.useState(false)
  return (
    <Page>
      <PageHeader
        title="Employees"
        description="Employee records are kept separately from system user accounts. Payroll is out of scope."
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "employees", label: "Employees", count: employees.length },
          { value: "schedule", label: "Schedule" },
          { value: "departments", label: "Departments" },
          { value: "positions", label: "Positions" },
          { value: "attendance", label: "Attendance" },
          { value: "activity", label: "Activity" },
        ]}
      />
      {tab === "employees" && (
        <CrudTable
          noun="Employee"
          seed={employees}
          filters={[
            { key: "department", label: "Department" },
            { key: "status", label: "Status", options: ["Active", "Inactive"] },
          ]}
          columns={[
            { key: "code", header: "Code" },
            {
              key: "name",
              header: "Name",
              render: (e) => <span className="font-medium">{e.name}</span>,
            },
            { key: "km", header: "Khmer name" },
            { key: "department", header: "Department" },
            { key: "position", header: "Position" },
            { key: "branch", header: "Branch" },
            { key: "start", header: "Start date" },
            {
              key: "user",
              header: "User account",
              render: (e) => e.user || "Not linked",
            },
            {
              key: "status",
              header: "Status",
              render: (e) => <StatusBadge status={e.status} />,
            },
          ]}
          fields={[
            {
              name: "name",
              label: "Name (English)",
              required: true,
              half: true,
            },
            { name: "km", label: "Name (Khmer)", required: true, half: true },
            {
              name: "code",
              label: "Employee code",
              required: true,
              half: true,
            },
            { name: "phone", label: "Phone", type: "tel", half: true },
            {
              name: "department",
              label: "Department",
              type: "select",
              options: [
                "Management",
                "Front of house",
                "Kitchen",
                "Bar",
                "Stores",
                "Finance",
                "Delivery",
              ],
              required: true,
              half: true,
            },
            { name: "position", label: "Position", required: true, half: true },
            {
              name: "branch",
              label: "Branch",
              type: "select",
              options: ["Riverside", "BKK1", "Siem Reap"],
              required: true,
              half: true,
            },
            {
              name: "start",
              label: "Start date (DD/MM/YYYY)",
              required: true,
              half: true,
            },
            { name: "user", label: "Linked user account (optional)" },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            status: e?.status ?? "Active",
            code: String(v.code),
            name: String(v.name),
            km: String(v.km),
            department: String(v.department),
            position: String(v.position),
            branch: String(v.branch),
            start: String(v.start),
            phone: String(v.phone ?? ""),
            user: String(v.user ?? ""),
          })}
        />
      )}
      {tab === "schedule" && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Week of 02/11/2026. Click a cell to change the shift.
            </p>
            <Button onClick={() => setOpen(true)}>
              <CalendarPlus />
              Add shift
            </Button>
          </div>
          <div className="overflow-x-auto rounded-xl border bg-card">
            <table className="w-full min-w-3xl text-sm">
              <thead className="bg-muted">
                <tr>
                  <th className="p-2 text-left font-medium">Employee</th>
                  {days.map((d) => (
                    <th key={d} className="p-2 text-center font-medium">
                      {d}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {employees.slice(0, 9).map((e) => (
                  <tr key={e.id} className="border-t">
                    <td className="p-2 font-medium whitespace-nowrap">
                      {e.name}
                      <span className="block text-xs font-normal text-muted-foreground">
                        {e.position}
                      </span>
                    </td>
                    {schedule[e.id].map((s, d) => (
                      <td key={d} className="p-1">
                        <button
                          aria-label={`${e.name} ${days[d]}: ${s}`}
                          className={cn(
                            "w-full rounded-md px-1.5 py-2 text-xs font-medium",
                            shiftTone[s] ??
                              "text-muted-foreground hover:bg-muted"
                          )}
                          onClick={() =>
                            setSchedule((c) => ({
                              ...c,
                              [e.id]: c[e.id].map((x, i) =>
                                i === d
                                  ? ["Morning", "Evening", "Split", "Off"][
                                      ([
                                        "Morning",
                                        "Evening",
                                        "Split",
                                        "Off",
                                      ].indexOf(x) +
                                        1) %
                                        4
                                    ]
                                  : x
                              ),
                            }))
                          }
                        >
                          {s}
                        </button>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {tab === "departments" && (
        <CrudTable
          noun="Department"
          seed={[
            "Management",
            "Front of house",
            "Kitchen",
            "Bar",
            "Stores",
            "Finance",
            "Delivery",
          ].map((name, i) => ({
            id: `d${i}`,
            name,
            staff: employees.filter((e) => e.department === name).length,
          }))}
          columns={[
            { key: "name", header: "Department" },
            { key: "staff", header: "Employees", align: "right" },
          ]}
          fields={[{ name: "name", label: "Name", required: true }]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            staff: e?.staff ?? 0,
          })}
        />
      )}
      {tab === "positions" && (
        <CrudTable
          noun="Position"
          seed={[...new Set(employees.map((e) => e.position))].map(
            (name, i) => ({
              id: `p${i}`,
              name,
              staff: employees.filter((e) => e.position === name).length,
            })
          )}
          columns={[
            { key: "name", header: "Position" },
            { key: "staff", header: "Employees", align: "right" },
          ]}
          fields={[{ name: "name", label: "Name", required: true }]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            staff: e?.staff ?? 0,
          })}
        />
      )}
      {tab === "attendance" && (
        <DataTable
          rows={employees
            .slice(2, 9)
            .map((e, i) => ({
              id: e.id,
              name: e.name,
              shift: i % 2 ? "Evening" : "Morning",
              in: i % 2 ? "—" : `07:5${i}`,
              out: "—",
              status: i % 2 ? "Scheduled" : "Active",
            }))}
          exportName="attendance"
          columns={[
            { key: "name", header: "Employee" },
            { key: "shift", header: "Shift" },
            { key: "in", header: "Clock in" },
            { key: "out", header: "Clock out" },
            {
              key: "status",
              header: "Status",
              render: (r) => (
                <StatusBadge
                  status={r.status === "Active" ? "On shift" : r.status}
                  tone={r.status === "Active" ? "success" : "info"}
                />
              ),
            },
          ]}
          rowActions={(r) => [
            {
              label: "Clock in",
              onClick: () => toast.success(`${r.name} clocked in`),
              hidden: () => r.in !== "—",
            },
          ]}
        />
      )}
      {tab === "activity" && (
        <DataTable
          rows={[
            {
              id: "1",
              name: "Lina Chhay",
              sessions: 4,
              sales: 2120.75,
              voids: 2,
              discounts: 6,
              refunds: 1,
            },
            {
              id: "2",
              name: "Sokha Heng",
              sessions: 0,
              sales: 3041.2,
              voids: 3,
              discounts: 2,
              refunds: 0,
            },
            {
              id: "3",
              name: "Dara Mean",
              sessions: 0,
              sales: 2688.4,
              voids: 1,
              discounts: 1,
              refunds: 0,
            },
            {
              id: "4",
              name: "Vuthy Sam",
              sessions: 3,
              sales: 1102,
              voids: 0,
              discounts: 4,
              refunds: 0,
            },
          ]}
          exportName="staff-activity"
          columns={[
            { key: "name", header: "Employee" },
            { key: "sessions", header: "Sessions", align: "right" },
            {
              key: "sales",
              header: "Sales",
              align: "right",
              render: (r) => usd(r.sales),
            },
            { key: "voids", header: "Voids", align: "right" },
            { key: "discounts", header: "Discounts", align: "right" },
            { key: "refunds", header: "Refunds", align: "right" },
          ]}
        />
      )}
      <RecordDialog
        open={open}
        onOpenChange={setOpen}
        title="Add shift"
        fields={[
          {
            name: "employee",
            label: "Employee",
            type: "select",
            options: employees.slice(0, 9).map((e) => e.name),
            required: true,
          },
          {
            name: "day",
            label: "Day",
            type: "select",
            options: days,
            required: true,
            half: true,
          },
          {
            name: "shift",
            label: "Shift",
            type: "select",
            options: ["Morning", "Evening", "Split", "Off"],
            required: true,
            half: true,
          },
        ]}
        onSubmit={(v) => {
          const e = employees.find((x) => x.name === v.employee)!
          setSchedule((c) => ({
            ...c,
            [e.id]: c[e.id].map((x, i) =>
              days[i] === v.day ? String(v.shift) : x
            ),
          }))
          toast.success("Shift scheduled")
        }}
      />
    </Page>
  )
}
