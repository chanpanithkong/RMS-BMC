"use client"

import * as React from "react"
import { Check, Download, Plus } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { KV, Notice, Page, PageHeader, Panel, StatusBadge, useTab } from "@/components/rms/kit"
import { SettingsForm, type SettingField } from "@/components/rms/settings-form"
import { api, download, ApiError } from "@/lib/api/client"
import { can, reloadMe, useSession } from "@/lib/api/session"
import { act, apiMessage, num, save, useApi, when } from "@/lib/api/use-api"
import { cn } from "@/lib/utils"

const groups = [
  { id: "restaurant", label: "Restaurant" },
  { id: "branch", label: "Branch details" },
  { id: "features", label: "Features" },
  { id: "currency", label: "Currency & rounding" },
  { id: "taxes", label: "Tax & service charge" },
  { id: "payments", label: "Payment methods" },
  { id: "operations", label: "Orders & kitchen" },
  { id: "stations", label: "Kitchen stations" },
  { id: "cash", label: "Cash control" },
  { id: "inventory", label: "Inventory & purchasing" },
  { id: "reservations", label: "Reservations" },
  { id: "messages", label: "Text messages" },
  { id: "accounting", label: "Accounting export" },
  { id: "dayend", label: "Day end" },
  { id: "history", label: "Change history" },
]

interface TaxProfile {
  id: string
  code: string
  name: string
  is_active: boolean
  rates: {
    id: string
    charge_kind: string
    name: string
    rate: string
    base_rule: string
    inclusive: boolean
    applies_to_order_types: string[]
    valid_from: string | null
    valid_to: string | null
    verified?: boolean
  }[]
}

export default function SettingsPage() {
  const { me } = useSession()
  const [tab, setTab] = useTab("restaurant")
  return (
    <Page>
      <PageHeader title="Settings" description="Restaurant and branch configuration. Every change is recorded with its before and after values." />
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[210px_1fr]">
        <nav aria-label="Settings groups" className="flex gap-1 overflow-x-auto lg:sticky lg:top-18 lg:flex-col">
          {groups.map((g) => (
            <button
              key={g.id}
              aria-current={tab === g.id ? "page" : undefined}
              onClick={() => setTab(g.id)}
              className={cn("shrink-0 rounded-md px-2.5 py-1.5 text-left text-sm", tab === g.id ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted")}
            >
              {g.label}
            </button>
          ))}
        </nav>
        <div className="grid min-w-0 gap-4">
          {!can(me, "settings.manage") && <Notice tone="info">You can view settings. Changing them needs the settings permission.</Notice>}
          {tab === "restaurant" && <RestaurantProfile />}
          {tab === "branch" && <BranchDetails />}
          {tab === "features" && (
            <>
              <SettingsForm group="online" title="Online ordering" fields={[{ name: "enabled", label: "Customers can order online", type: "switch" }, { name: "auto_accept", label: "Accept online orders automatically", type: "switch" }]} />
              <SettingsForm group="qr" title="Table QR ordering" fields={[{ name: "enabled", label: "Guests can order from the table QR code", type: "switch" }, { name: "require_staff_confirmation", label: "Staff confirm QR orders before the kitchen sees them", type: "switch" }]} />
              <SettingsForm group="loyalty" title="Loyalty" fields={[{ name: "enabled", label: "Customers earn and redeem points", type: "switch" }]} description="Rules are under Promotions → Loyalty." />
              <SettingsForm group="credit" title="Customer credit accounts" fields={[{ name: "enabled", label: "Bills can be charged to credit accounts", type: "switch" }, { name: "default_terms_days", label: "Default payment terms (days)", type: "number", min: 0, asNumber: true }]} />
              <SettingsForm
                group="grabfood"
                title="GrabFood"
                description="Orders arrive automatically once Grab gives partner access. The commission rate is only used for estimates before settlement."
                fields={[
                  { name: "enabled", label: "Receive GrabFood orders", type: "switch" },
                  { name: "merchant_id", label: "Grab merchant ID", half: true },
                  { name: "commission_rate", label: "Commission rate (e.g. 0.25 = 25%)", type: "number", min: 0, max: 1, half: true },
                ]}
              />
            </>
          )}
          {tab === "currency" && <Currency />}
          {tab === "taxes" && <Taxes />}
          {tab === "payments" && <PaymentMethods />}
          {tab === "operations" && (
            <>
              <SettingsForm
                group="orders"
                title="Orders"
                fields={[
                  { name: "require_table_for_dine_in", label: "Dine-in orders need a table", type: "switch" },
                  { name: "pay_first_order_types", label: "Pay before the kitchen starts (comma separated)", list: true, hint: "DineIn, Takeaway, Delivery" },
                ]}
              />
              <SettingsForm
                group="kitchen"
                title="Kitchen"
                fields={[
                  { name: "late_ticket_minutes", label: "A ticket is late after (minutes)", type: "number", min: 1, asNumber: true, half: true },
                  { name: "printer_fallback_seconds", label: "Print a backup ticket if the screen hasn't seen it within (seconds)", type: "number", min: 1, asNumber: true, half: true },
                ]}
              />
              <SettingsForm group="recipes" title="Food cost" fields={[{ name: "target_food_cost_pct", label: "Target food cost (%)", type: "number", min: 0, max: 100 }]} />
            </>
          )}
          {tab === "stations" && <Stations />}
          {tab === "cash" && (
            <SettingsForm
              group="cash"
              title="Cash variance tolerance"
              description="A closing count further from the expected amount than this needs a manager's approval. Financial setting: needs settings approval."
              fields={[
                { name: "usd", path: "variance_tolerance.USD", label: "USD", type: "number", min: 0, half: true },
                { name: "khr", path: "variance_tolerance.KHR", label: "KHR", type: "number", min: 0, half: true },
              ]}
            />
          )}
          {tab === "inventory" && (
            <>
              <SettingsForm
                group="inventory"
                title="Inventory"
                fields={[
                  { name: "consumption_point", label: "Ingredients are consumed when items are", type: "select", options: ["Send", "Ready", "Served"], half: true },
                  { name: "expiry_warning_days", label: "Warn about expiry this many days ahead", type: "number", min: 0, asNumber: true, half: true },
                  { name: "allow_negative_from_sales", label: "Sales may take stock below zero (flagged for review)", type: "switch" },
                ]}
              />
              <SettingsForm
                group="purchasing"
                title="Purchasing"
                fields={[
                  { name: "receipt_tolerance_pct", label: "Over-receipt tolerance (%)", type: "number", min: 0, half: true },
                  { name: "price_tolerance_pct", label: "Price difference tolerance (%)", type: "number", min: 0, half: true },
                  { name: "invoice_tolerance", label: "Invoice matching tolerance (USD)", type: "number", min: 0, half: true },
                  { name: "separate_receiver", label: "The person who orders can't receive the goods", type: "switch", half: true },
                ]}
              />
            </>
          )}
          {tab === "reservations" && (
            <SettingsForm
              group="reservations"
              title="Reservations"
              fields={(
                [
                  ["default_duration_minutes", "Default dining time (minutes)"],
                  ["buffer_minutes", "Buffer between bookings (minutes)"],
                  ["hold_minutes", "Hold the table before arrival (minutes)"],
                  ["grace_minutes", "Grace period before no-show (minutes)"],
                  ["max_party_size", "Largest party"],
                  ["walkin_warning_minutes", "Warn before seating walk-ins this close to a booking (minutes)"],
                ] as const
              ).map(([name, label]): SettingField => ({ name, label, type: "number", min: 0, asNumber: true, half: true }))}
            />
          )}
          {tab === "messages" && (
            <SettingsForm
              group="sms"
              title="Text messages (PlasGate)"
              description="Messages are sent only after the provider account is configured on the server."
              fields={[
                { name: "enabled", label: "Send text messages", type: "switch" },
                { name: "order_updates", label: "Online order updates", type: "switch", half: true },
                { name: "reservations", label: "Reservation confirmations and reminders", type: "switch", half: true },
                { name: "reservation_reminder_minutes", label: "Reminder before the booking (minutes)", type: "number", min: 0, asNumber: true, half: true },
                { name: "customer_session_days", label: "Customer sign-in lasts (days)", type: "number", min: 1, asNumber: true, half: true },
              ]}
            />
          )}
          {tab === "accounting" && <Accounting />}
          {tab === "dayend" && <DayEnd />}
          {tab === "history" && <History />}
        </div>
      </div>
    </Page>
  )
}

interface Restaurant {
  id: string
  name_en: string
  name_km: string | null
  legal_name: string
  tax_id: string | null
  address: string | null
  phone: string | null
  base_currency: string
}

/** Restaurant-wide details printed on bills and receipts. Placeholders from the first setup are flagged until replaced. */
function RestaurantProfile() {
  const { me } = useSession()
  const r = useApi(() => api<Restaurant>("GET", "/restaurant"), [], null)
  const [open, setOpen] = React.useState(false)
  const d = r.data
  if (!d) return <Panel title="Restaurant">{r.loading ? "Loading…" : "Not available."}</Panel>
  const placeholder = d.name_en === "RMS Demo Restaurant" || d.legal_name.startsWith("RMS Demo Restaurant")
  return (
    <Panel
      title="Restaurant"
      description="Shown at the top of every bill and receipt, for all branches."
      actions={
        can(me, "branches.manage") && (
          <Button variant="outline" onClick={() => setOpen(true)}>
            Edit
          </Button>
        )
      }
    >
      {placeholder && (
        <Notice tone="warning" className="mb-3">
          These are the placeholder details from the first setup. Enter your restaurant&apos;s name, legal name and tax ID before printing bills for customers.
        </Notice>
      )}
      <KV
        items={[
          ["Name", d.name_en],
          ["Khmer name", d.name_km ?? "—"],
          ["Legal name", d.legal_name],
          ["Tax ID", d.tax_id ?? "Not set (not printed)"],
          ["Address", d.address ?? "—"],
          ["Phone", d.phone ?? "—"],
          ["Base currency", d.base_currency],
        ]}
      />
      <RecordDialog
        open={open}
        onOpenChange={setOpen}
        title="Edit restaurant"
        description="Changes apply to bills and receipts printed from now on. The change is recorded in the audit trail."
        fields={[
          { name: "name", label: "Name (English)", required: true, half: true },
          { name: "km", label: "Name (Khmer)", half: true },
          { name: "legal", label: "Legal name", required: true },
          { name: "tax", label: "Tax ID", half: true, hint: "Leave empty if not registered" },
          { name: "phone", label: "Phone", type: "tel", half: true },
          { name: "address", label: "Registered address", type: "textarea" },
        ]}
        initial={{ name: d.name_en, km: d.name_km ?? "", legal: d.legal_name, tax: d.tax_id ?? "", phone: d.phone ?? "", address: d.address ?? "" }}
        onSubmit={(v) =>
          save(() =>
            api("PATCH", "/restaurant", {
              body: {
                name_en: String(v.name),
                name_km: String(v.km ?? ""),
                legal_name: String(v.legal),
                tax_id: String(v.tax ?? ""),
                phone: String(v.phone ?? ""),
                address: String(v.address ?? ""),
              },
            })
          ).then(r.reload)
        }
      />
    </Panel>
  )
}

function BranchDetails() {
  const { me } = useSession()
  const b = me?.current_branch
  const [open, setOpen] = React.useState(false)
  // /auth/me has no day-end time; /branches does.
  const list = useApi(() => api<{ id: string; day_end_time: string }[]>("GET", "/branches"), [], [])
  const dayEnd = String(list.data.find((x) => x.id === b?.id)?.day_end_time ?? "").slice(0, 5)
  if (!b) return null
  return (
    <Panel
      title={b.name_en}
      description="This branch. Other branches are managed under Branches."
      actions={
        can(me, "branches.manage") && (
          <Button variant="outline" onClick={() => setOpen(true)}>
            Edit
          </Button>
        )
      }
    >
      <KV
        items={[
          ["Code", b.code],
          ["Khmer name", b.name_km ?? "—"],
          ["Time zone", b.timezone],
          ["Business day ends", dayEnd || "—"],
          ["Business day now", me.business_date],
        ]}
      />
      <RecordDialog
        open={open}
        onOpenChange={setOpen}
        title="Edit branch details"
        description="Only the fields you fill in are changed."
        fields={[
          { name: "name", label: "English name", half: true },
          { name: "km", label: "Khmer name", half: true },
          { name: "address", label: "Address" },
          { name: "phone", label: "Phone", type: "tel", half: true },
          { name: "hours", label: "Opening hours", half: true },
          { name: "dayEnd", label: "Business day ends at", type: "time", half: true },
        ]}
        initial={{ name: b.name_en, km: b.name_km ?? "", dayEnd }}
        onSubmit={(v) => {
          const body = Object.fromEntries(
            Object.entries({ name_en: v.name, name_km: v.km, address: v.address, phone: v.phone, opening_hours: v.hours, day_end_time: v.dayEnd }).filter(([, x]) => x !== undefined && x !== "")
          )
          return save(() => api("PATCH", `/branches/${b.id}`, { body })).then(() => {
            list.reload()
            return reloadMe()
          })
        }}
      />
    </Panel>
  )
}

function Currency() {
  const { me } = useSession()
  const rates = useApi(() => api<{ id: string; base_currency: string; quote_currency: string; rate: string; effective_from: string; source: string }[]>("GET", "/exchange-rates"), [], [])
  const [add, setAdd] = React.useState(false)
  return (
    <>
      <SettingsForm
        group="billing"
        title="Rounding and bills"
        description="Base currency is USD. Financial setting: needs settings approval."
        fields={[
          { name: "khr_rounding_increment", label: "Round riel cash to the nearest", type: "number", min: 1, half: true, hint: "e.g. 100" },
          { name: "partial_payments", label: "Allow paying a bill in several parts", type: "switch", half: true },
        ]}
      />
      <Panel
        title="Exchange rates (1 USD in riel)"
        description="The rate in effect when a payment is taken is stored with the payment."
        actions={
          can(me, "exchange_rates.manage") && (
            <Button onClick={() => setAdd(true)}>
              <Plus />
              New rate
            </Button>
          )
        }
      >
        <DataTable
          rows={rates.data.map((r) => ({ ...r, from: when(r.effective_from), value: num(r.rate) }))}
          exportName="exchange-rates"
          emptyTitle="No rates entered"
          columns={[
            { key: "from", header: "Effective from" },
            { key: "value", header: "Riel per USD", align: "right", render: (r) => r.value.toLocaleString() },
            { key: "source", header: "Source" },
          ]}
        />
      </Panel>
      <RecordDialog
        open={add}
        onOpenChange={setAdd}
        title="New exchange rate"
        description="Effective now or later. Back-dated rates need settings approval."
        fields={[
          { name: "rate", label: "Riel per 1 USD", type: "number", min: 1, required: true, half: true },
          { name: "from", label: "Effective from", type: "date", required: true, half: true },
          { name: "source", label: "Source", required: true, hint: "e.g. NBC official rate" },
        ]}
        initial={{ from: new Date().toLocaleDateString("en-CA") }}
        onSubmit={(v) => {
          const day = String(v.from)
          const at = day === new Date().toLocaleDateString("en-CA") ? new Date() : new Date(`${day}T00:00`)
          return save(() => api("POST", "/exchange-rates", { body: { rate: String(v.rate), effective_from: at.toISOString(), source: v.source } })).then(rates.reload)
        }}
      />
    </>
  )
}

function Taxes() {
  const { me } = useSession()
  const profiles = useApi(() => api<TaxProfile[]>("GET", "/tax-profiles"), [], [])
  const [addFor, setAddFor] = React.useState<TaxProfile | null>(null)
  return (
    <>
      <Notice tone="warning">Enter only verified tax and service-charge rates. Unverified rules are flagged until someone records the reference they were checked against.</Notice>
      {profiles.data.map((p) => (
        <Panel
          key={p.id}
          title={p.name}
          description={p.code}
          actions={
            can(me, "settings.approve") && (
              <Button variant="outline" onClick={() => setAddFor(p)}>
                <Plus />
                Schedule a rule
              </Button>
            )
          }
        >
          <DataTable
            rows={p.rates.map((r) => ({
              ...r,
              pct: `${(num(r.rate) * 100).toFixed(2)}%`,
              period: `${when(r.valid_from).slice(0, 10) || "—"} → ${r.valid_to ? when(r.valid_to).slice(0, 10) : "open"}`,
              types: r.applies_to_order_types.join(", "),
              base: r.base_rule === "DiscountedSubtotal" ? "Subtotal after discounts" : "Subtotal plus service charge",
            }))}
            exportName={`tax-${p.code}`}
            emptyTitle="No rules"
            columns={[
              { key: "charge_kind", header: "Kind" },
              { key: "name", header: "Name" },
              { key: "pct", header: "Rate", align: "right" },
              { key: "base", header: "Charged on" },
              { key: "inclusive", header: "Included in price", render: (r) => (r.inclusive ? "Yes" : "No") },
              { key: "types", header: "Order types" },
              { key: "period", header: "In effect" },
              { key: "verified", header: "Verified", render: (r) => <StatusBadge status={r.verified ? "Verified" : "Unverified"} tone={r.verified ? "success" : "warning"} /> },
            ]}
          />
        </Panel>
      ))}
      <RecordDialog
        open={!!addFor}
        onOpenChange={(o) => !o && setAddFor(null)}
        title={`New rule for ${addFor?.name ?? ""}`}
        description="The current rule of the same kind ends when this one starts."
        fields={[
          { name: "kind", label: "Kind", type: "select", options: ["Tax", "ServiceCharge"], required: true, half: true },
          { name: "name", label: "Name", required: true, half: true },
          { name: "pct", label: "Rate (%)", type: "number", min: 0, max: 99.99, required: true, half: true },
          { name: "base", label: "Charged on", type: "select", options: ["Subtotal after discounts", "Subtotal plus service charge"], required: true, half: true },
          { name: "types", label: "Order types (comma separated)", required: true, hint: "DineIn, Takeaway, Delivery" },
          { name: "from", label: "Starts", type: "date", required: true, half: true },
          { name: "inclusive", label: "Already included in menu prices", type: "switch", half: true },
          { name: "verified", label: "I have verified this rate", type: "switch", half: true },
          { name: "ref", label: "Verified against (document or reference)", half: true },
        ]}
        initial={{ types: "DineIn, Takeaway, Delivery" }}
        onSubmit={(v) =>
          save(() =>
            api("POST", `/tax-profiles/${addFor!.id}/rates`, {
              body: {
                charge_kind: v.kind,
                name: v.name,
                rate: String(Number(v.pct) / 100),
                base_rule: v.base === "Subtotal plus service charge" ? "SubtotalPlusServiceCharge" : "DiscountedSubtotal",
                inclusive: Boolean(v.inclusive),
                applies_to_order_types: String(v.types).split(",").map((s) => s.trim()).filter(Boolean),
                valid_from: new Date(`${v.from}T00:00`).toISOString(),
                verified: Boolean(v.verified),
                verified_ref: String(v.ref ?? "") || undefined,
              },
            })
          ).then(profiles.reload)
        }
      />
    </>
  )
}

function PaymentMethods() {
  const { me } = useSession()
  const list = useApi(
    () => api<{ id: string; code: string; name: string; kind: string; currencies: string[]; reference_required: boolean; change_allowed: boolean; is_active: boolean }[]>("GET", "/payment-methods"),
    [],
    []
  )
  const approver = can(me, "settings.approve")
  return (
    <Panel title="Payment methods" description="Turning a method off hides it at the till. Financial setting: needs settings approval.">
      <DataTable
        rows={list.data}
        exportName="payment-methods"
        columns={[
          { key: "name", header: "Method" },
          { key: "code", header: "Code" },
          { key: "currencies", header: "Currencies", render: (m) => m.currencies.join(", ") },
          { key: "change_allowed", header: "Change given", render: (m) => (m.change_allowed ? "Yes" : "No") },
          {
            key: "reference_required",
            header: "Reference required",
            render: (m) => (
              <Switch
                aria-label={`${m.name} needs a reference`}
                disabled={!approver}
                checked={m.reference_required}
                onCheckedChange={(c) => void act(() => api("PATCH", `/payment-methods/${m.id}`, { body: { reference_required: Boolean(c) } }), "Saved", list.reload)}
              />
            ),
          },
          {
            key: "is_active",
            header: "On",
            render: (m) => (
              <Switch
                aria-label={`${m.name} on`}
                disabled={!approver}
                checked={m.is_active}
                onCheckedChange={(c) => void act(() => api("PATCH", `/payment-methods/${m.id}`, { body: { is_active: Boolean(c) } }), `${m.name} ${c ? "on" : "off"}`, list.reload)}
              />
            ),
          },
        ]}
      />
    </Panel>
  )
}

function Stations() {
  const { me } = useSession()
  const list = useApi(() => api<{ id: string; code: string; name: string; warn_minutes: number; critical_minutes: number; backup_printer: string | null; is_active: boolean }[]>("GET", "/kitchen/stations"), [], [])
  const [add, setAdd] = React.useState(false)
  return (
    <Panel
      title="Kitchen stations"
      description="Menu items are routed to a station. A station's screen turns tickets amber and red after these times."
      actions={
        can(me, "settings.manage") && (
          <Button onClick={() => setAdd(true)}>
            <Plus />
            Station
          </Button>
        )
      }
    >
      <DataTable
        rows={list.data}
        exportName="stations"
        columns={[
          { key: "code", header: "Code" },
          { key: "name", header: "Name" },
          { key: "warn_minutes", header: "Late after (min)", align: "right" },
          { key: "critical_minutes", header: "Critical after (min)", align: "right" },
          { key: "backup_printer", header: "Backup printer", render: (s) => s.backup_printer ?? "—" },
          { key: "is_active", header: "Status", render: (s) => <StatusBadge status={s.is_active ? "Active" : "Inactive"} /> },
        ]}
      />
      <RecordDialog
        open={add}
        onOpenChange={setAdd}
        title="Configure a station"
        description="Using an existing code updates that station."
        fields={[
          { name: "code", label: "Code (capitals, e.g. GRILL)", required: true, half: true, validate: (v) => (/^[A-Z0-9_]{2,20}$/.test(String(v)) ? undefined : "2–20 capital letters, digits or _") },
          { name: "name", label: "Name", required: true, half: true },
          { name: "warn", label: "Late after (minutes)", type: "number", min: 1, required: true, half: true },
          { name: "crit", label: "Critical after (minutes)", type: "number", min: 2, required: true, half: true },
          { name: "printer", label: "Backup printer" },
        ]}
        initial={{ warn: "10", crit: "20" }}
        onSubmit={(v) =>
          save(() =>
            api("POST", "/kitchen-stations", {
              body: { code: v.code, name: v.name, warn_minutes: Number(v.warn), critical_minutes: Number(v.crit), backup_printer: String(v.printer ?? "") || undefined },
            })
          ).then(list.reload)
        }
      />
    </Panel>
  )
}

function Accounting() {
  const { me } = useSession()
  const allowed = can(me, "accounting.export")
  const mapping = useApi(
    () =>
      allowed
        ? api<{ accounts: Record<string, { code: string; name: string; placeholder: boolean }>; method_accounts: Record<string, { code: string; name: string; placeholder: boolean }>; mapping_confirmed: boolean }>("GET", "/accounting/mapping")
        : Promise.resolve(null),
    [allowed],
    null
  )
  const [from, setFrom] = React.useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 7)
    return d.toLocaleDateString("en-CA")
  })
  const [to, setTo] = React.useState(() => new Date().toLocaleDateString("en-CA"))
  const journals = useApi(
    () => (allowed ? api<{ journals: { date: string; narration: string; lines: { description: string; account_code: string; amount: string }[] }[] }>("GET", "/accounting/journals", { query: { date_from: from, date_to: to } }) : Promise.resolve(null)),
    [from, to, allowed],
    null
  )
  if (!allowed) return <Notice tone="info">The accounting export needs the accounting export permission.</Notice>
  const m = mapping.data
  const accountFields: SettingField[] = m
    ? [
        ...Object.entries(m.accounts).map(([k, a]): SettingField => ({ name: `a_${k}`, path: `accounts.${k}`, label: a.name, half: true, hint: a.placeholder ? `Placeholder ${a.code}` : undefined })),
        ...Object.entries(m.method_accounts).map(([k, a]): SettingField => ({ name: `m_${k}`, path: `method_accounts.${k}`, label: `Payments: ${a.name}`, half: true, hint: a.placeholder ? `Placeholder ${a.code}` : undefined })),
        { name: "tax_rate_name", label: "Xero tax rate name", half: true },
        { name: "tracking_name", label: "Xero tracking category", half: true },
        { name: "mapping_confirmed", label: "The accountant has confirmed these codes (export is allowed)", type: "switch" },
      ]
    : []
  return (
    <>
      {m && !m.mapping_confirmed && <Notice tone="warning">The export is blocked until real Xero account codes replace the placeholders and the mapping is confirmed.</Notice>}
      {m && <SettingsForm group="accounting" title="Xero account codes" description="One journal per business day. Empty fields use the placeholder code shown." fields={accountFields} allowRestaurantWide />}
      <Panel
        title="Daily journals"
        description="Each journal balances to zero (debits positive, credits negative)."
        actions={
          <Button
            variant="outline"
            disabled={!m?.mapping_confirmed}
            onClick={() => void download("/accounting/journals/xero.csv", `xero-${from}-${to}.csv`, { date_from: from, date_to: to }).catch((e) => toast.error(apiMessage(e)))}
          >
            <Download />
            Xero file
          </Button>
        }
      >
        <div className="mb-2 flex items-center gap-2 text-sm">
          <input type="date" aria-label="From" className="rounded-md border px-2 py-1" value={from} onChange={(e) => setFrom(e.target.value)} />
          to
          <input type="date" aria-label="To" className="rounded-md border px-2 py-1" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <DataTable
          rows={(journals.data?.journals ?? []).flatMap((j) => j.lines.map((l, i) => ({ id: `${j.date}-${i}`, date: i === 0 ? String(j.date) : "", ...l, amt: num(l.amount) })))}
          exportName="journals"
          emptyTitle="No journals in this period"
          columns={[
            { key: "date", header: "Date" },
            { key: "description", header: "Line" },
            { key: "account_code", header: "Account" },
            { key: "amt", header: "Amount", align: "right", render: (l) => l.amt.toFixed(2) },
          ]}
        />
      </Panel>
    </>
  )
}

function DayEnd() {
  const { me } = useSession()
  const [last, setLast] = React.useState<Record<string, unknown> | null>(null)
  const close = (acknowledge: boolean, reason?: string) =>
    api<Record<string, unknown>>("POST", "/day-end/close", { body: { acknowledge_open_items: acknowledge, reason } }).then(
      (r) => {
        setLast(r)
        toast.success(`Business day ${String(r.business_date)} closed`)
      },
      (e) => {
        if (e instanceof ApiError && e.code === "DAY_END_BLOCKED")
          confirmAction({
            title: "There are open items",
            effect: `${e.body.open_orders} open orders, ${e.body.open_sessions} open cashier sessions and ${e.body.pending_payments} pending payments. Close the day anyway?`,
            requireReason: true,
            destructive: true,
            confirmLabel: "Close with open items",
            onConfirm: (r) => void close(true, r),
          })
        else toast.error(apiMessage(e))
      }
    )
  return (
    <Panel title="Close the business day" description={`Business day ${me?.business_date}. Closing checks open orders, cashier sessions and pending payments, then finalises the day's summaries.`} className="max-w-xl">
      {last && (
        <KV
          className="mb-3"
          items={[
            ["Closed", String(last.business_date)],
            ["Open orders at close", String(last.open_orders)],
            ["Open sessions at close", String(last.open_sessions)],
            ["Pending payments at close", String(last.pending_payments)],
          ]}
        />
      )}
      <Button
        disabled={!can(me, "settings.manage")}
        onClick={() =>
          confirmAction({
            title: `Close business day ${me?.business_date}?`,
            effect: "Day-end summaries are finalised. This is recorded in the audit trail.",
            confirmLabel: "Close day",
            onConfirm: () => void close(false),
          })
        }
      >
        <Check />
        Close day
      </Button>
    </Panel>
  )
}

function History() {
  const { me } = useSession()
  const log = useApi(
    async () =>
      can(me, "audit.view")
        ? (await api<{ data: { id: number; occurred_at: string; action: string; entity_type: string; before_data: unknown; after_data: unknown }[] }>("GET", "/audit-logs", { query: { action: "settings.", page_size: 100 } })).data
        : [],
    [me?.id],
    []
  )
  return (
    <DataTable
      rows={log.data.map((e) => ({ ...e, id: String(e.id), time: when(e.occurred_at), change: JSON.stringify(e.after_data).slice(0, 120) }))}
      exportName="settings-history"
      emptyTitle={can(me, "audit.view") ? "No settings changes recorded" : "You can't view the audit trail"}
      columns={[
        { key: "time", header: "Time" },
        { key: "action", header: "Change" },
        { key: "change", header: "New value" },
      ]}
    />
  )
}
