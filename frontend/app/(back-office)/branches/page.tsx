"use client"

import * as React from "react"
import { Ban, PackageCheck, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { CrudTable, RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { Notice, Page, PageHeader, PageTabs, Stat, StatusBadge, useTab } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import * as inv from "@/lib/api/inventory"
import { can, reloadMe, useSession } from "@/lib/api/session"
import { act, num, save, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

interface Branch {
  id: string
  code: string
  name_en: string
  name_km: string | null
  timezone: string
  day_end_time: string
  is_active: boolean
}
interface Transfer {
  id: string
  transfer_no: string
  from_branch_id: string
  from_location_id: string
  to_branch_id: string
  to_location_id: string | null
  status: string
  note: string | null
  dispatched_at: string
  received_at: string | null
  cancel_reason: string | null
  lines: { id: string; ingredient_id: string; qty_dispatched: string; qty_received: string | null; variance_qty: string | null; variance_reason: string | null }[]
}
interface Row {
  branch_id: string
  name: string
  net_sales: string
  orders: number
  average_order_value: string
  covers: number
  discounts: string
  refunds: string
  food_cost_percent: string
  approved_expenses: string
  labour_hours: string
}

const monthStart = () => {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toLocaleDateString("en-CA")
}

export default function BranchesPage() {
  const { me } = useSession()
  const manage = can(me, "branches.manage")
  const [tab, setTab] = useTab("branches")
  const branches = useApi(() => api<Branch[]>("GET", "/branches"), [], [])
  const [from, setFrom] = React.useState(monthStart())
  const today = new Date().toLocaleDateString("en-CA")
  const compare = useApi(
    () => (can(me, "report.cross_branch") ? api<{ rows: Row[]; total: Record<string, string | number> }>("GET", "/branch-comparison", { query: { date_from: from, date_to: today } }) : Promise.resolve(null)),
    [from, me?.id, tab === "compare"],
    null as { rows: Row[]; total: Record<string, string | number> } | null
  )
  const transfers = useApi(() => (can(me, "inventory.view") ? api<Transfer[]>("GET", "/branch-transfers") : Promise.resolve([] as Transfer[])), [tab === "transfers", me?.id], [])
  // Ingredient names for transfers; only for roles that may see inventory.
  const refs = useApi(async () => (can(me, "inventory.view") ? { ingredients: await inv.ingredients(), units: await inv.units(), locations: await inv.locations() }
    : { ingredients: [], units: [], locations: [] }), [me?.id], {
    ingredients: [] as inv.Ingredient[],
    units: [] as inv.Unit[],
    locations: [] as inv.Location[],
  })
  const devices = useApi(() => api<{ id: string; name: string; kind: string; status: string; last_seen_at: string | null }[]>("GET", "/devices"), [tab === "devices"], [])
  const [dispatch, setDispatch] = React.useState(false)
  const [receiveFor, setReceiveFor] = React.useState<Transfer | null>(null)
  const [newDevice, setNewDevice] = React.useState(false)
  const [token, setToken] = React.useState<string | null>(null)
  const bName = (id: string) => branches.data.find((b) => b.id === id)?.name_en ?? "Other branch"
  const ing = (id: string) => refs.data.ingredients.find((i) => i.id === id)
  const here = me?.current_branch.id

  return (
    <Page>
      <PageHeader title="Branches" description="Branch details, consolidated figures, stock sent between branches and registered devices." />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "branches", label: "Branches", count: branches.data.length },
          { value: "compare", label: "Comparison" },
          { value: "transfers", label: "Stock between branches" },
          { value: "devices", label: "Devices" },
        ]}
      />
      {tab === "branches" && (
        <CrudTable
          noun="Branch"
          rows={branches.data.map((b) => ({ ...b, dayEnd: b.day_end_time.slice(0, 5), status: b.is_active ? "Active" : "Inactive" }))}
          canAdd={manage}
          canEdit={manage}
          description="New branches get default kitchen stations and storage locations. You are assigned to the branches you create."
          onSave={(v, e) =>
            save(() =>
              e
                ? api("PATCH", `/branches/${e.id}`, {
                    body: { name_en: v.name, name_km: String(v.km ?? "") || null, address: String(v.address ?? "") || null, phone: String(v.phone ?? "") || null, opening_hours: String(v.hours ?? "") || null, day_end_time: v.dayEnd || undefined },
                  })
                : api("POST", "/branches", {
                    body: { code: v.code, name_en: v.name, name_km: String(v.km ?? "") || undefined, address: String(v.address ?? "") || undefined, phone: String(v.phone ?? "") || undefined, opening_hours: String(v.hours ?? "") || undefined, day_end_time: v.dayEnd || undefined },
                  })
            ).then(async () => {
              await reloadMe() // the branch list in the header comes from /auth/me
              branches.reload()
            })
          }
          columns={[
            { key: "code", header: "Code" },
            { key: "name_en", header: "Name", render: (b) => <span className="font-medium">{b.name_en}</span> },
            { key: "name_km", header: "Khmer", render: (b) => b.name_km ?? "" },
            { key: "timezone", header: "Time zone" },
            { key: "dayEnd", header: "Business day ends" },
            { key: "status", header: "Status", render: (b) => <StatusBadge status={b.id === here ? "Current" : b.status} tone={b.id === here ? "info" : undefined} /> },
          ]}
          fields={[
            { name: "code", label: "Code (can't change later)", required: true, half: true },
            { name: "phone", label: "Phone", type: "tel", half: true },
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", half: true },
            { name: "address", label: "Address" },
            { name: "hours", label: "Opening hours", half: true, hint: "e.g. 07:00–22:00" },
            { name: "dayEnd", label: "Business day ends at", type: "time", half: true, hint: "Sales after midnight count for the previous day until this time" },
          ]}
          toForm={(b) => ({ code: b.code, name: b.name_en, km: b.name_km ?? "", dayEnd: b.day_end_time.slice(0, 5) })}
        />
      )}
      {tab === "compare" &&
        (!can(me, "report.cross_branch") ? (
          <Notice tone="info">Comparing branches needs the cross-branch reporting permission.</Notice>
        ) : (
          <>
            <label className="flex items-center gap-2 text-sm">
              From
              <input type="date" className="rounded-md border px-2 py-1" value={from} onChange={(e) => setFrom(e.target.value)} />
              to today
            </label>
            {compare.data && (
              <section className="grid gap-3 sm:grid-cols-4">
                <Stat label="Net sales, all branches" value={usd(num(compare.data.total.net_sales))} />
                <Stat label="Orders" value={num(compare.data.total.orders)} />
                <Stat label="Average order" value={usd(num(compare.data.total.average_order_value))} />
                <Stat label="Food cost" value={`${num(compare.data.total.food_cost_percent)}%`} />
              </section>
            )}
            <DataTable
              rows={(compare.data?.rows ?? []).map((r) => ({ ...r, id: r.branch_id }))}
              exportName="branch-comparison"
              emptyTitle="No branches to compare"
              columns={[
                { key: "name", header: "Branch" },
                { key: "net_sales", header: "Net sales", align: "right", render: (r) => usd(num(r.net_sales)) },
                { key: "orders", header: "Orders", align: "right" },
                { key: "average_order_value", header: "Avg order", align: "right", render: (r) => usd(num(r.average_order_value)) },
                { key: "covers", header: "Covers", align: "right" },
                { key: "discounts", header: "Discounts", align: "right", render: (r) => usd(num(r.discounts)) },
                { key: "refunds", header: "Refunds", align: "right", render: (r) => usd(num(r.refunds)) },
                { key: "food_cost_percent", header: "Food cost", align: "right", render: (r) => `${num(r.food_cost_percent)}%` },
                { key: "approved_expenses", header: "Expenses", align: "right", render: (r) => usd(num(r.approved_expenses)) },
                { key: "labour_hours", header: "Labour hours", align: "right", render: (r) => num(r.labour_hours).toFixed(1) },
              ]}
            />
          </>
        ))}
      {tab === "transfers" && (
        <DataTable
          rows={transfers.data.map((t) => ({
            ...t,
            direction: t.from_branch_id === here ? `To ${bName(t.to_branch_id)}` : `From ${bName(t.from_branch_id)}`,
            sent: when(t.dispatched_at),
            items: t.lines.map((l) => `${ing(l.ingredient_id)?.name_en ?? "?"} ${inv.qty(l.qty_dispatched)}`).join(", "),
            short: t.lines.some((l) => num(l.variance_qty) > 0),
          }))}
          exportName="branch-transfers"
          emptyTitle="No transfers"
          toolbar={can(me, "inventory.manage") && branches.data.length > 1 && <Button onClick={() => setDispatch(true)}>Send stock</Button>}
          columns={[
            { key: "transfer_no", header: "Transfer" },
            { key: "direction", header: "Direction" },
            { key: "sent", header: "Sent" },
            { key: "items", header: "Items" },
            { key: "status", header: "Status", render: (t) => <StatusBadge status={t.short ? "Short" : t.status === "InTransit" ? "In Transit" : t.status} /> },
          ]}
          rowActions={(t) => [
            { label: "Receive", icon: PackageCheck, hidden: () => t.to_branch_id !== here || t.status !== "InTransit" || !can(me, "inventory.manage"), onClick: () => setReceiveFor(t) },
            {
              label: "Cancel",
              icon: X,
              destructive: true,
              hidden: () => t.from_branch_id !== here || t.status !== "InTransit" || !can(me, "inventory.manage"),
              onClick: () =>
                confirmAction({
                  title: `Cancel ${t.transfer_no}?`,
                  effect: "The stock goes back to the location it was sent from.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Cancel transfer",
                  onConfirm: (reason) => void act(() => api("POST", `/branch-transfers/${t.id}/cancel`, { body: { reason } }), `${t.transfer_no} cancelled`, transfers.reload),
                }),
            },
          ]}
        />
      )}
      {tab === "devices" && (
        <DataTable
          rows={devices.data.map((d) => ({ ...d, seen: when(d.last_seen_at) || "Never" }))}
          exportName="devices"
          emptyTitle="No registered devices"
          toolbar={manage && <Button onClick={() => setNewDevice(true)}>Register device</Button>}
          columns={[
            { key: "name", header: "Device" },
            { key: "kind", header: "Type" },
            { key: "seen", header: "Last seen" },
            { key: "status", header: "Status", render: (d) => <StatusBadge status={d.status} /> },
          ]}
          rowActions={(d) => [
            {
              label: "Revoke",
              icon: Ban,
              destructive: true,
              hidden: () => !manage || d.status !== "Active",
              onClick: () =>
                confirmAction({
                  title: `Revoke ${d.name}?`,
                  effect: "PIN sign-in stops working on that device until it is registered again.",
                  destructive: true,
                  confirmLabel: "Revoke",
                  onConfirm: () => void act(() => api("POST", `/devices/${d.id}/revoke`), `${d.name} revoked`, devices.reload),
                }),
            },
          ]}
        />
      )}
      <RecordDialog
        open={dispatch}
        onOpenChange={setDispatch}
        title="Send stock to another branch"
        description="Stock leaves this branch now; the other branch receives it and records any shortage."
        fields={[
          { name: "to", label: "To branch", type: "select", options: branches.data.filter((b) => b.id !== here && b.is_active).map((b) => b.name_en), required: true, half: true },
          { name: "from", label: "From location", type: "select", options: refs.data.locations.filter((l) => l.is_active).map((l) => l.name), required: true, half: true },
          { name: "ingredient", label: "Ingredient", type: "select", options: refs.data.ingredients.filter((i) => i.is_active).map((i) => i.name_en), required: true },
          { name: "qty", label: "Quantity", type: "number", min: 0.001, required: true, half: true },
          { name: "unit", label: "Unit", type: "select", options: refs.data.units.map((u) => u.code), half: true },
          { name: "note", label: "Note" },
        ]}
        onSubmit={(v) => {
          const i = refs.data.ingredients.find((x) => x.name_en === v.ingredient)!
          return save(() =>
            api("POST", "/branch-transfers", {
              body: {
                to_branch_id: branches.data.find((b) => b.name_en === v.to)!.id,
                from_location_id: refs.data.locations.find((l) => l.name === v.from)!.id,
                note: String(v.note ?? "") || undefined,
                lines: [{ ingredient_id: i.id, quantity: String(v.qty), uom_id: refs.data.units.find((u) => u.code === v.unit)?.id ?? i.stock_uom_id }],
              },
            })
          ).then(transfers.reload)
        }}
      />
      <RecordDialog
        open={!!receiveFor}
        onOpenChange={(o) => !o && setReceiveFor(null)}
        title={`Receive ${receiveFor?.transfer_no ?? ""}`}
        description="Quantities are in each ingredient's stock unit. A shortage needs a reason."
        fields={[
          { name: "location", label: "Into location", type: "select", options: refs.data.locations.filter((l) => l.is_active).map((l) => l.name), required: true },
          ...(receiveFor?.lines ?? []).flatMap((l) => [
            { name: `q_${l.id}`, label: `${ing(l.ingredient_id)?.name_en ?? "?"}: sent ${inv.qty(l.qty_dispatched)}`, type: "number" as const, min: 0, required: true, half: true },
            { name: `r_${l.id}`, label: "Reason if short", half: true },
          ]),
        ]}
        initial={Object.fromEntries((receiveFor?.lines ?? []).map((l) => [`q_${l.id}`, String(num(l.qty_dispatched))]))}
        onSubmit={(v) =>
          save(() =>
            api("POST", `/branch-transfers/${receiveFor!.id}/receive`, {
              body: {
                to_location_id: refs.data.locations.find((l) => l.name === v.location)!.id,
                lines: receiveFor!.lines.map((l) => ({ line_id: l.id, qty_received: String(v[`q_${l.id}`]), variance_reason: String(v[`r_${l.id}`] ?? "") || undefined })),
              },
            })
          ).then(transfers.reload)
        }
      />
      <RecordDialog
        open={newDevice}
        onOpenChange={setNewDevice}
        title="Register a device"
        description="The device token is shown once. Enter it on the device to allow PIN sign-in there."
        fields={[
          { name: "name", label: "Name", required: true, half: true, hint: "e.g. Front counter POS" },
          { name: "kind", label: "Type", type: "select", options: ["POS", "KDS", "PrintAgent", "Web"], required: true, half: true },
        ]}
        onSubmit={(v) =>
          save(() => api<{ device_token: string }>("POST", "/devices", { body: { name: v.name, kind: v.kind } })).then((d) => {
            setToken(d.device_token)
            devices.reload()
          })
        }
      />
      <RecordDialog
        open={!!token}
        onOpenChange={(o) => !o && setToken(null)}
        title="Device token"
        description="Copy it now; it can't be shown again."
        fields={[{ name: "token", label: "Token", disabled: true }]}
        initial={{ token: token ?? "" }}
        submitLabel="Copy and close"
        onSubmit={() => {
          void navigator.clipboard?.writeText(token ?? "").then(() => toast.success("Token copied"))
        }}
      />
    </Page>
  )
}
