"use client"

import * as React from "react"
import { Moon, ShieldCheck } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import {
  CrudTable,
  RecordForm,
  newId,
  validateFields,
  type Field,
  type FieldValue,
} from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction, requestApproval } from "@/components/rms/dialog-host"
import {
  Notice,
  Page,
  PageHeader,
  Panel,
  StatusBadge,
  useTab,
  SimpleSelect,
  opts,
} from "@/components/rms/kit"
import { rms, useRms } from "@/lib/rms/store"
import { cn } from "@/lib/utils"

const groups: { id: string; label: string }[] = [
  { id: "restaurant", label: "Restaurant" },
  { id: "modules", label: "Modules & profile" },
  { id: "currencies", label: "Currencies & rates" },
  { id: "taxes", label: "Taxes & service charges" },
  { id: "receipts", label: "Receipts" },
  { id: "numbering", label: "Numbering" },
  { id: "service", label: "Service & dining" },
  { id: "stations", label: "Stations & printers" },
  { id: "payments", label: "Payment methods" },
  { id: "languages", label: "Languages & format" },
  { id: "inventory", label: "Inventory rules" },
  { id: "limits", label: "Approval limits" },
  { id: "notifications", label: "Notifications" },
  { id: "devices", label: "Devices" },
  { id: "dayend", label: "Day-end" },
  { id: "history", label: "Change history" },
]
const moduleList = [
  "Tables",
  "Reservations",
  "Kitchen display",
  "Customers",
  "Inventory",
  "Recipes",
  "Purchasing",
  "Expenses",
  "Staff schedules",
  "Delivery",
  "Promotions",
  "Loyalty",
  "Multi-branch",
  "Online ordering",
]
const profiles: Record<string, string[]> = {
  "Small restaurant": ["Tables", "Kitchen display", "Inventory"],
  "Full-service restaurant": [
    "Tables",
    "Reservations",
    "Kitchen display",
    "Customers",
    "Inventory",
    "Recipes",
    "Purchasing",
    "Expenses",
    "Staff schedules",
    "Promotions",
  ],
  "Café / coffee shop": [
    "Kitchen display",
    "Customers",
    "Inventory",
    "Recipes",
    "Loyalty",
  ],
  "Fast-food restaurant": ["Kitchen display", "Inventory", "Promotions"],
  "Food court stall": ["Kitchen display"],
  "Takeaway-focused": ["Kitchen display", "Inventory", "Customers"],
  "Delivery-focused": ["Kitchen display", "Delivery", "Customers"],
  "Multi-branch business": [
    "Tables",
    "Reservations",
    "Kitchen display",
    "Customers",
    "Inventory",
    "Recipes",
    "Purchasing",
    "Expenses",
    "Staff schedules",
    "Promotions",
    "Multi-branch",
  ],
}

function GroupForm({
  title,
  description,
  fields,
  initial,
  financial,
}: {
  title: string
  description?: string
  fields: Field[]
  initial: Record<string, FieldValue>
  financial?: boolean
}) {
  const [values, setValues] = React.useState(initial)
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const [dirty, setDirty] = React.useState(false)
  const save = () => {
    const e = validateFields(fields, values)
    setErrors(e)
    if (Object.keys(e).length) return
    if (financial)
      requestApproval({
        action: `Change: ${title}`,
        reason: "Takes effect at the chosen time",
        onApproved: (by) => {
          toast.success(`Approved by ${by}; before and after values recorded`)
          setDirty(false)
        },
      })
    else {
      toast.success("Saved")
      setDirty(false)
    }
  }
  return (
    <Panel title={title} description={description}>
      {financial && (
        <Notice tone="warning" className="mb-3">
          Financial setting: saving creates a change request that needs
          approval.
        </Notice>
      )}
      <RecordForm
        fields={fields}
        values={values}
        errors={errors}
        setValue={(k, v) => {
          setValues((s) => ({ ...s, [k]: v }))
          setDirty(true)
        }}
      />
      <div className="mt-4 flex items-center justify-end gap-2">
        {dirty && <span className="text-xs text-warning">Unsaved changes</span>}
        <Button onClick={save}>
          {financial ? "Submit for approval" : "Save"}
        </Button>
      </div>
    </Panel>
  )
}

export default function SettingsPage() {
  const [tab, setTab] = useTab("restaurant")
  const { orders, sessions } = useRms()
  const [enabled, setEnabled] = React.useState<string[]>(
    profiles["Full-service restaurant"]
  )
  const [profile, setProfile] = React.useState("Full-service restaurant")
  const openOrders = orders.filter((o) => o.status === "Open").length
  const openSessions = sessions.filter((s) => s.status === "Open").length
  return (
    <Page>
      <PageHeader
        title="Settings"
        description="Restaurant and branch configuration. All changes are recorded with before and after values."
      />
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[210px_1fr]">
        <nav
          aria-label="Settings groups"
          className="flex gap-1 overflow-x-auto lg:sticky lg:top-18 lg:flex-col"
        >
          {groups.map((g) => (
            <button
              key={g.id}
              aria-current={tab === g.id ? "page" : undefined}
              onClick={() => setTab(g.id)}
              className={cn(
                "shrink-0 rounded-md px-2.5 py-1.5 text-left text-sm",
                tab === g.id
                  ? "bg-accent font-medium text-accent-foreground"
                  : "text-muted-foreground hover:bg-muted"
              )}
            >
              {g.label}
            </button>
          ))}
        </nav>
        <div className="grid min-w-0 gap-4">
          {tab === "restaurant" && (
            <GroupForm
              title="Restaurant profile"
              initial={{
                legal: "RMS Demo Restaurant Co., Ltd.",
                en: "RMS Demo Restaurant",
                km: "ភោជនីយដ្ឋានសាកល្បង",
                address: "Sisowath Quay, Phnom Penh",
                phone: "023 100 100",
                tin: "",
              }}
              fields={[
                { name: "legal", label: "Legal name", required: true },
                {
                  name: "en",
                  label: "Trade name (English)",
                  required: true,
                  half: true,
                },
                {
                  name: "km",
                  label: "Trade name (Khmer)",
                  required: true,
                  half: true,
                },
                { name: "address", label: "Address", required: true },
                { name: "phone", label: "Phone", type: "tel", half: true },
                { name: "tin", label: "Tax ID (if applicable)", half: true },
                { name: "logo", label: "Logo", type: "file" },
              ]}
            />
          )}
          {tab === "modules" && (
            <Panel
              title="Modules"
              description="Apply a business-type profile, then fine-tune."
            >
              <div className="max-w-sm">
                <SimpleSelect
                  aria-label="Business type"
                  value={profile}
                  onChange={(p) => {
                    setProfile(p)
                    setEnabled(profiles[p])
                    toast.success(`${p} profile applied`)
                  }}
                  options={opts(...Object.keys(profiles))}
                />
              </div>
              <ul className="mt-4 grid gap-x-6 sm:grid-cols-2">
                {moduleList.map((m) => (
                  <li
                    key={m}
                    className="flex items-center justify-between border-b py-2 text-sm"
                  >
                    {m}
                    <Switch
                      aria-label={m}
                      checked={enabled.includes(m)}
                      onCheckedChange={(c) =>
                        setEnabled(
                          c ? [...enabled, m] : enabled.filter((x) => x !== m)
                        )
                      }
                    />
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          {tab === "currencies" && (
            <>
              <GroupForm
                financial
                title="Base currency and rounding"
                description="Illustrative values."
                initial={{ base: "USD", usdDec: "2", khrDec: "0", inc: "100" }}
                fields={[
                  {
                    name: "base",
                    label: "Base currency",
                    type: "select",
                    options: ["USD", "KHR"],
                    required: true,
                    half: true,
                  },
                  {
                    name: "inc",
                    label: "KHR cash rounding increment",
                    type: "number",
                    min: 1,
                    required: true,
                    half: true,
                  },
                  {
                    name: "usdDec",
                    label: "USD decimals",
                    type: "number",
                    min: 0,
                    required: true,
                    half: true,
                  },
                  {
                    name: "khrDec",
                    label: "KHR decimals",
                    type: "number",
                    min: 0,
                    required: true,
                    half: true,
                  },
                ]}
              />
              <CrudTable
                noun="Exchange rate"
                canEdit={false}
                seed={[
                  {
                    id: "1",
                    rate: 4100,
                    from: "01/11/2026 00:00",
                    source: "Manual",
                    user: "Sreyleak Mao",
                    status: "Active",
                  },
                  {
                    id: "2",
                    rate: 4080,
                    from: "01/10/2026 00:00",
                    source: "Manual",
                    user: "Sreyleak Mao",
                    status: "Expired",
                  },
                ]}
                columns={[
                  { key: "rate", header: "KHR per USD", align: "right" },
                  { key: "from", header: "Effective from" },
                  { key: "source", header: "Source" },
                  { key: "user", header: "Set by" },
                  {
                    key: "status",
                    header: "Status",
                    render: (r) => <StatusBadge status={r.status} />,
                  },
                ]}
                fields={[
                  {
                    name: "rate",
                    label: "KHR per USD",
                    type: "number",
                    min: 1,
                    required: true,
                    half: true,
                  },
                  {
                    name: "from",
                    label: "Effective from",
                    required: true,
                    half: true,
                  },
                  { name: "source", label: "Source", required: true },
                ]}
                description="New rates need approval before their effective time."
                toRow={(v) => ({
                  id: newId(),
                  rate: Number(v.rate),
                  from: String(v.from),
                  source: String(v.source),
                  user: "Dara Pich",
                  status: "Pending Approval",
                })}
              />
            </>
          )}
          {tab === "taxes" && (
            <>
              <Notice tone="warning">
                Rates are placeholders until verified against current official
                Cambodian sources (V-01, D-03).
              </Notice>
              <CrudTable
                noun="Tax profile"
                seed={[
                  {
                    id: "1",
                    name: "VAT Standard",
                    kind: "Tax",
                    rate: 10,
                    base: "Subtotal + service",
                    mode: "Exclusive",
                    applies: "All order types",
                    from: "01/01/2026",
                    verified: "Unverified",
                  },
                  {
                    id: "2",
                    name: "Service charge",
                    kind: "Service",
                    rate: 5,
                    base: "Discounted subtotal",
                    mode: "Exclusive",
                    applies: "Dine-in",
                    from: "01/01/2026",
                    verified: "Unverified",
                  },
                  {
                    id: "3",
                    name: "Tax inclusive",
                    kind: "Tax",
                    rate: 10,
                    base: "Line amount",
                    mode: "Inclusive",
                    applies: "Online",
                    from: "01/06/2026",
                    verified: "Unverified",
                  },
                ]}
                columns={[
                  { key: "name", header: "Profile" },
                  { key: "kind", header: "Type" },
                  {
                    key: "rate",
                    header: "Rate",
                    align: "right",
                    render: (r) => `${r.rate}%`,
                  },
                  { key: "base", header: "Base" },
                  { key: "mode", header: "Mode" },
                  { key: "applies", header: "Applies to" },
                  { key: "from", header: "Effective" },
                  {
                    key: "verified",
                    header: "Verification",
                    render: (r) => <StatusBadge status={r.verified} />,
                  },
                ]}
                fields={[
                  { name: "name", label: "Name", required: true, half: true },
                  {
                    name: "kind",
                    label: "Type",
                    type: "select",
                    options: ["Tax", "Service"],
                    required: true,
                    half: true,
                  },
                  {
                    name: "rate",
                    label: "Rate (%)",
                    type: "number",
                    min: 0,
                    max: 99.99,
                    required: true,
                    half: true,
                  },
                  {
                    name: "mode",
                    label: "Mode",
                    type: "select",
                    options: ["Exclusive", "Inclusive"],
                    required: true,
                    half: true,
                  },
                  { name: "base", label: "Base", required: true, half: true },
                  {
                    name: "applies",
                    label: "Applies to",
                    required: true,
                    half: true,
                  },
                  { name: "from", label: "Effective from", required: true },
                ]}
                description="Changes need approval and take effect at the effective date."
                toRow={(v, e) => ({
                  id: e?.id ?? newId(),
                  name: String(v.name),
                  kind: String(v.kind),
                  rate: Number(v.rate),
                  base: String(v.base),
                  mode: String(v.mode),
                  applies: String(v.applies),
                  from: String(v.from),
                  verified: "Unverified",
                })}
              />
            </>
          )}
          {tab === "receipts" && (
            <GroupForm
              title="Receipt template"
              description="Required invoice fields are subject to verification (V-02)."
              initial={{
                language: "Khmer and English",
                width: "80 mm",
                header: "RMS Demo Restaurant",
                footer: "Thank you / អរគុណ",
                qr: true,
                copies: "1",
              }}
              fields={[
                {
                  name: "language",
                  label: "Language",
                  type: "select",
                  options: ["Khmer", "English", "Khmer and English"],
                  required: true,
                  half: true,
                },
                {
                  name: "width",
                  label: "Paper width",
                  type: "select",
                  options: ["58 mm", "80 mm"],
                  required: true,
                  half: true,
                },
                { name: "header", label: "Header", required: true },
                { name: "footer", label: "Footer" },
                {
                  name: "copies",
                  label: "Copies",
                  type: "number",
                  min: 1,
                  half: true,
                },
                {
                  name: "qr",
                  label: "Show QR receipt link",
                  type: "switch",
                  half: true,
                },
              ]}
            />
          )}
          {tab === "numbering" && (
            <CrudTable
              noun="Numbering series"
              canAdd={false}
              seed={[
                ["Orders", "#", "Daily"],
                ["Receipts", "R-2026-", "Yearly"],
                ["Invoices", "INV-", "Yearly"],
                ["Credit notes", "CN-", "Yearly"],
                ["Purchase orders", "PO-", "Never"],
                ["Goods receipts", "GRN-", "Never"],
              ].map(([series, prefix, reset], i) => ({
                id: String(i),
                series,
                prefix,
                reset,
              }))}
              columns={[
                { key: "series", header: "Series" },
                { key: "prefix", header: "Prefix" },
                { key: "reset", header: "Reset" },
              ]}
              fields={[
                { name: "prefix", label: "Prefix", required: true },
                {
                  name: "reset",
                  label: "Reset",
                  type: "select",
                  options: ["Daily", "Yearly", "Never"],
                  required: true,
                },
              ]}
              toRow={(v, e) => ({
                ...e!,
                prefix: String(v.prefix),
                reset: String(v.reset),
              })}
            />
          )}
          {tab === "service" && (
            <GroupForm
              title="Service model and dining"
              initial={{
                dine: "Pay later",
                take: "Pay first",
                del: "Pay first",
                duration: "90",
                hold: "15",
                grace: "15",
                buffer: "15",
              }}
              fields={[
                {
                  name: "dine",
                  label: "Dine-in",
                  type: "select",
                  options: ["Pay later", "Pay first"],
                  required: true,
                  half: true,
                },
                {
                  name: "take",
                  label: "Takeaway",
                  type: "select",
                  options: ["Pay later", "Pay first"],
                  required: true,
                  half: true,
                },
                {
                  name: "del",
                  label: "Delivery",
                  type: "select",
                  options: ["Pay later", "Pay first"],
                  required: true,
                  half: true,
                },
                {
                  name: "duration",
                  label: "Default dining duration (min)",
                  type: "number",
                  min: 15,
                  required: true,
                  half: true,
                },
                {
                  name: "hold",
                  label: "Reservation hold (min)",
                  type: "number",
                  min: 0,
                  required: true,
                  half: true,
                },
                {
                  name: "grace",
                  label: "No-show grace (min)",
                  type: "number",
                  min: 0,
                  required: true,
                  half: true,
                },
                {
                  name: "buffer",
                  label: "Buffer between bookings (min)",
                  type: "number",
                  min: 0,
                  required: true,
                  half: true,
                },
              ]}
            />
          )}
          {tab === "stations" && (
            <>
              <CrudTable
                noun="Kitchen station"
                seed={[
                  ["Hot", 10, 20, "Printer 1"],
                  ["Cold", 8, 15, "Printer 2"],
                  ["Beverage", 5, 10, "Printer 3"],
                  ["Dessert", 8, 15, "Printer 2"],
                  ["Bar", 5, 10, "Printer 3"],
                ].map(([name, warn, crit, backup], i) => ({
                  id: String(i),
                  name: String(name),
                  warn: Number(warn),
                  crit: Number(crit),
                  backup: String(backup),
                  status: "Online",
                }))}
                columns={[
                  { key: "name", header: "Station" },
                  { key: "warn", header: "Warning (min)", align: "right" },
                  { key: "crit", header: "Critical (min)", align: "right" },
                  { key: "backup", header: "Backup printer" },
                  {
                    key: "status",
                    header: "KDS",
                    render: (r) => <StatusBadge status={r.status} />,
                  },
                ]}
                fields={[
                  { name: "name", label: "Name", required: true },
                  {
                    name: "warn",
                    label: "Warning (min)",
                    type: "number",
                    min: 1,
                    required: true,
                    half: true,
                  },
                  {
                    name: "crit",
                    label: "Critical (min)",
                    type: "number",
                    min: 1,
                    required: true,
                    half: true,
                    validate: (v, a) =>
                      Number(v) <= Number(a.warn)
                        ? "Must be greater than warning"
                        : undefined,
                  },
                  {
                    name: "backup",
                    label: "Backup printer",
                    type: "select",
                    options: ["Printer 1", "Printer 2", "Printer 3"],
                    required: true,
                  },
                ]}
                toRow={(v, e) => ({
                  id: e?.id ?? newId(),
                  name: String(v.name),
                  warn: Number(v.warn),
                  crit: Number(v.crit),
                  backup: String(v.backup),
                  status: e?.status ?? "Online",
                })}
              />
              <CrudTable
                noun="Printer"
                seed={[
                  {
                    id: "p1",
                    name: "Printer 1",
                    kind: "Network",
                    ip: "10.0.1.91",
                    width: "80 mm",
                    route: "Hot station",
                    status: "Online",
                  },
                  {
                    id: "p2",
                    name: "Printer 2",
                    kind: "Network",
                    ip: "10.0.1.92",
                    width: "80 mm",
                    route: "Cold, Dessert",
                    status: "Offline",
                  },
                  {
                    id: "p3",
                    name: "Printer 3",
                    kind: "USB agent",
                    ip: "POS-1",
                    width: "58 mm",
                    route: "Bar, Beverage",
                    status: "Online",
                  },
                ]}
                columns={[
                  { key: "name", header: "Printer" },
                  { key: "kind", header: "Connection" },
                  { key: "ip", header: "Address" },
                  { key: "width", header: "Paper" },
                  { key: "route", header: "Routing" },
                  {
                    key: "status",
                    header: "Status",
                    render: (r) => <StatusBadge status={r.status} />,
                  },
                ]}
                fields={[
                  { name: "name", label: "Name", required: true, half: true },
                  {
                    name: "kind",
                    label: "Connection",
                    type: "select",
                    options: ["Network", "USB agent"],
                    required: true,
                    half: true,
                  },
                  { name: "ip", label: "Address", required: true, half: true },
                  {
                    name: "width",
                    label: "Paper width",
                    type: "select",
                    options: ["58 mm", "80 mm"],
                    required: true,
                    half: true,
                  },
                  { name: "route", label: "Routing", required: true },
                ]}
                toRow={(v, e) => ({
                  id: e?.id ?? newId(),
                  name: String(v.name),
                  kind: String(v.kind),
                  ip: String(v.ip),
                  width: String(v.width),
                  route: String(v.route),
                  status: e?.status ?? "Online",
                })}
              />
            </>
          )}
          {tab === "payments" && (
            <CrudTable
              noun="Payment method"
              seed={[
                ["Cash USD", "Cash", "USD", "No", "Yes"],
                ["Cash KHR", "Cash", "KHR", "No", "Yes"],
                ["KHQR", "QR", "USD, KHR", "Yes", "No"],
                ["Bank Transfer", "Bank", "USD", "Yes", "No"],
                ["Card", "Card terminal", "USD", "Yes", "No"],
              ].map(([name, type, currency, reference, change], i) => ({
                id: String(i),
                name,
                type,
                currency,
                reference,
                change,
                status: "Active",
              }))}
              columns={[
                { key: "name", header: "Method" },
                { key: "type", header: "Type" },
                { key: "currency", header: "Currencies" },
                { key: "reference", header: "Reference required" },
                { key: "change", header: "Change allowed" },
                {
                  key: "status",
                  header: "Status",
                  render: (r) => <StatusBadge status={r.status} />,
                },
              ]}
              fields={[
                { name: "name", label: "Name", required: true, half: true },
                {
                  name: "type",
                  label: "Type",
                  type: "select",
                  options: ["Cash", "QR", "Bank", "Card terminal"],
                  required: true,
                  half: true,
                },
                { name: "currency", label: "Currencies", required: true },
                {
                  name: "reference",
                  label: "Reference required",
                  type: "select",
                  options: ["Yes", "No"],
                  required: true,
                  half: true,
                },
                {
                  name: "change",
                  label: "Change allowed",
                  type: "select",
                  options: ["Yes", "No"],
                  required: true,
                  half: true,
                },
              ]}
              description="Changes need approval."
              toRow={(v, e) => ({
                id: e?.id ?? newId(),
                name: String(v.name),
                type: String(v.type),
                currency: String(v.currency),
                reference: String(v.reference),
                change: String(v.change),
                status: e?.status ?? "Active",
              })}
            />
          )}
          {tab === "languages" && (
            <GroupForm
              title="Languages and format"
              initial={{
                def: "Khmer",
                date: "DD/MM/YYYY",
                time: "24-hour",
                tz: "Asia/Phnom_Penh",
              }}
              fields={[
                {
                  name: "def",
                  label: "Default language",
                  type: "select",
                  options: ["Khmer", "English"],
                  required: true,
                  half: true,
                },
                {
                  name: "date",
                  label: "Date format",
                  type: "select",
                  options: ["DD/MM/YYYY", "YYYY-MM-DD"],
                  required: true,
                  half: true,
                },
                {
                  name: "time",
                  label: "Time format",
                  type: "select",
                  options: ["24-hour", "12-hour"],
                  required: true,
                  half: true,
                },
                {
                  name: "tz",
                  label: "Time zone",
                  type: "select",
                  options: ["Asia/Phnom_Penh"],
                  required: true,
                  half: true,
                },
              ]}
            />
          )}
          {tab === "inventory" && (
            <GroupForm
              title="Inventory rules"
              initial={{
                point: "When sent to kitchen",
                negative: "Allow and flag",
                method: "Weighted average",
                threshold: "25",
                expiry: "3",
              }}
              fields={[
                {
                  name: "point",
                  label: "Consumption point",
                  type: "select",
                  options: ["When sent to kitchen", "When ready", "When paid"],
                  required: true,
                  half: true,
                },
                {
                  name: "negative",
                  label: "Negative stock policy",
                  type: "select",
                  options: ["Allow and flag", "Block sale"],
                  required: true,
                  half: true,
                },
                {
                  name: "method",
                  label: "Valuation method",
                  type: "select",
                  options: ["Weighted average"],
                  required: true,
                  half: true,
                },
                {
                  name: "threshold",
                  label: "Adjustment approval over ($)",
                  type: "number",
                  min: 0,
                  required: true,
                  half: true,
                },
                {
                  name: "expiry",
                  label: "Expiry warning (days)",
                  type: "number",
                  min: 0,
                  required: true,
                  half: true,
                },
              ]}
            />
          )}
          {tab === "limits" && (
            <CrudTable
              noun="Approval limit"
              canAdd={false}
              seed={[
                ["Supervisor", "20%", 10, 25, 0, 0],
                ["Branch Manager", "30%", 50, 100, 1000, 300],
                ["General Manager", "50%", 200, 500, 5000, 2000],
                ["Owner", "100%", 9999, 9999, 99999, 99999],
              ].map(([role, discount, voids, refunds, po, expense], i) => ({
                id: String(i),
                role: String(role),
                discount: String(discount),
                voids: Number(voids),
                refunds: Number(refunds),
                po: Number(po),
                expense: Number(expense),
              }))}
              columns={[
                { key: "role", header: "Role" },
                { key: "discount", header: "Discount", align: "right" },
                { key: "voids", header: "Void ($)", align: "right" },
                { key: "refunds", header: "Refund ($)", align: "right" },
                { key: "po", header: "PO ($)", align: "right" },
                { key: "expense", header: "Expense ($)", align: "right" },
              ]}
              fields={[
                {
                  name: "discount",
                  label: "Discount",
                  required: true,
                  half: true,
                },
                {
                  name: "voids",
                  label: "Void ($)",
                  type: "number",
                  min: 0,
                  required: true,
                  half: true,
                },
                {
                  name: "refunds",
                  label: "Refund ($)",
                  type: "number",
                  min: 0,
                  required: true,
                  half: true,
                },
                {
                  name: "po",
                  label: "PO ($)",
                  type: "number",
                  min: 0,
                  required: true,
                  half: true,
                },
                {
                  name: "expense",
                  label: "Expense ($)",
                  type: "number",
                  min: 0,
                  required: true,
                },
              ]}
              description="Changes need approval."
              toRow={(v, e) => ({
                ...e!,
                discount: String(v.discount),
                voids: Number(v.voids),
                refunds: Number(v.refunds),
                po: Number(v.po),
                expense: Number(v.expense),
              })}
            />
          )}
          {tab === "notifications" && (
            <GroupForm
              title="Notification channels"
              description="Credentials are stored as secrets and are not shown after saving."
              initial={{
                sender: "noreply@example.com",
                smsOn: false,
                retry: "5",
              }}
              fields={[
                {
                  name: "sender",
                  label: "Email sender",
                  type: "email",
                  required: true,
                  half: true,
                },
                {
                  name: "retry",
                  label: "Retry limit",
                  type: "number",
                  min: 0,
                  required: true,
                  half: true,
                },
                {
                  name: "apiKey",
                  label: "Provider API key",
                  hint: "Leave blank to keep the saved key",
                },
                {
                  name: "smsOn",
                  label: "Enable SMS and messaging",
                  type: "switch",
                },
              ]}
            />
          )}
          {tab === "devices" && (
            <CrudTable
              noun="Device"
              seed={[
                {
                  id: "1",
                  name: "POS-1",
                  kind: "POS terminal",
                  branch: "Riverside",
                  seen: "Now",
                  status: "Online",
                },
                {
                  id: "2",
                  name: "POS-2",
                  kind: "POS terminal",
                  branch: "Riverside",
                  seen: "Now",
                  status: "Online",
                },
                {
                  id: "3",
                  name: "KDS-1",
                  kind: "KDS screen",
                  branch: "Riverside",
                  seen: "Now",
                  status: "Online",
                },
                {
                  id: "4",
                  name: "KDS-2",
                  kind: "KDS screen",
                  branch: "Riverside",
                  seen: "2 h ago",
                  status: "Offline",
                },
                {
                  id: "5",
                  name: "Agent-1",
                  kind: "Print agent",
                  branch: "Riverside",
                  seen: "Now",
                  status: "Online",
                },
              ]}
              filters={[{ key: "kind", label: "Type" }]}
              columns={[
                { key: "name", header: "Device" },
                { key: "kind", header: "Type" },
                { key: "branch", header: "Branch" },
                { key: "seen", header: "Last seen" },
                {
                  key: "status",
                  header: "Status",
                  render: (r) => <StatusBadge status={r.status} />,
                },
              ]}
              fields={[
                { name: "name", label: "Name", required: true, half: true },
                {
                  name: "kind",
                  label: "Type",
                  type: "select",
                  options: ["POS terminal", "KDS screen", "Print agent"],
                  required: true,
                  half: true,
                },
                {
                  name: "branch",
                  label: "Branch",
                  type: "select",
                  options: ["Riverside", "BKK1", "Siem Reap"],
                  required: true,
                },
              ]}
              extraActions={(d, update) => [
                {
                  label: "Revoke device",
                  icon: ShieldCheck,
                  destructive: true,
                  onClick: () =>
                    confirmAction({
                      title: `Revoke ${d.name}?`,
                      effect:
                        "It must be registered again before it can connect.",
                      destructive: true,
                      confirmLabel: "Revoke",
                      onConfirm: () => update({ status: "Revoked" }),
                    }),
                },
              ]}
              toRow={(v, e) => ({
                id: e?.id ?? newId(),
                name: String(v.name),
                kind: String(v.kind),
                branch: String(v.branch),
                seen: e?.seen ?? "Never",
                status: e?.status ?? "Online",
              })}
            />
          )}
          {tab === "dayend" && (
            <>
              <GroupForm
                title="Business day"
                description="Sales after midnight count toward this business day until the end time."
                initial={{ end: "04:00" }}
                fields={[
                  {
                    name: "end",
                    label: "Business day ends at",
                    type: "time",
                    required: true,
                  },
                ]}
              />
              <Panel title="Close business day 08/11/2026">
                <ul className="grid gap-1.5 text-sm">
                  <li className="flex justify-between">
                    <span>Open orders</span>
                    <StatusBadge
                      status={`${openOrders} open`}
                      tone={openOrders ? "warning" : "success"}
                    />
                  </li>
                  <li className="flex justify-between">
                    <span>Open cashier sessions</span>
                    <StatusBadge
                      status={`${openSessions} open`}
                      tone={openSessions ? "warning" : "success"}
                    />
                  </li>
                  <li className="flex justify-between">
                    <span>Pending electronic payments</span>
                    <StatusBadge status="1 pending" tone="warning" />
                  </li>
                </ul>
                <Button
                  className="mt-3"
                  onClick={() =>
                    confirmAction({
                      title: "Close the business day with open items?",
                      effect: `${openOrders} open orders and ${openSessions} open sessions will carry over. Your acknowledgement is recorded.`,
                      requireReason: true,
                      confirmLabel: "Acknowledge and close",
                      onConfirm: () => {
                        rms.markAllRead()
                        toast.success("Business day closed")
                      },
                    })
                  }
                >
                  <Moon />
                  Run day-end close
                </Button>
              </Panel>
            </>
          )}
          {tab === "history" && (
            <DataTable
              rows={[
                {
                  id: "1",
                  time: "07/11/2026 18:44",
                  setting: "VAT Standard rate",
                  before: "10%",
                  after: "10% effective 01/12/2026",
                  user: "Sreyleak Mao",
                  approver: "Vannak Keo",
                },
                {
                  id: "2",
                  time: "01/11/2026 09:00",
                  setting: "Exchange rate",
                  before: "4,080",
                  after: "4,100",
                  user: "Sreyleak Mao",
                  approver: "Dara Pich",
                },
                {
                  id: "3",
                  time: "28/10/2026 10:12",
                  setting: "Receipt footer",
                  before: "Thank you",
                  after: "Thank you / អរគុណ",
                  user: "Sopheak Nou",
                  approver: "—",
                },
              ]}
              exportName="setting-history"
              columns={[
                { key: "time", header: "Time" },
                { key: "setting", header: "Setting" },
                { key: "before", header: "Before" },
                { key: "after", header: "After" },
                { key: "user", header: "Changed by" },
                { key: "approver", header: "Approved by" },
              ]}
            />
          )}
        </div>
      </div>
    </Page>
  )
}
