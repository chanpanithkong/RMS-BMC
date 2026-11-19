"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { AlertTriangle, Check, ClipboardPlus, Clock3, DollarSign, Minus, PackageX, Plus, Scale, ShieldCheck, Trash2, Undo2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { CrudTable, RecordDialog, type Field } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { Page, PageHeader, PageTabs, Panel, Stat, StatusBadge, useTab } from "@/components/rms/kit"
import * as inv from "@/lib/api/inventory"
import { listItems } from "@/lib/api/menu"
import { can, useSession } from "@/lib/api/session"
import { act, num, save, useApi, when } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

const STATUS: Record<string, string> = { PendingApproval: "Pending Approval" }
const TXN_LABEL: Record<string, string> = {
  OPENING: "Opening",
  RECEIPT: "Receipt",
  GOODS_RECEIPT: "Goods receipt",
  ISSUE: "Issue",
  ADJUSTMENT: "Adjustment",
  WASTE: "Wastage",
  SALE_CONSUMPTION: "Sale",
  COUNT_ADJUSTMENT: "Count",
  TRANSFER_IN: "Transfer in",
  TRANSFER_OUT: "Transfer out",
  REVERSAL: "Reversal",
}

/** Everything the inventory screen reads, in one round of requests. */
async function loadAll() {
  const [units, locations, ingredients, balances, expiring] = await Promise.all([
    inv.units(),
    inv.locations(),
    inv.ingredients(),
    inv.balances(),
    inv.expiring().catch(() => []),
  ])
  return { units, locations, ingredients, balances, expiring }
}
const empty = { units: [], locations: [], ingredients: [], balances: [], expiring: [] } as Awaited<ReturnType<typeof loadAll>>

export default function InventoryPage() {
  const router = useRouter()
  const { me } = useSession()
  const manage = can(me, "inventory.manage")
  const approve = can(me, "inventory.approve")
  const [tab, setTab] = useTab("overview")
  const [form, setForm] = React.useState<null | "Issue" | "Adjustment" | "Wastage" | "menuWaste" | "transfer" | "count">(null)
  const { data, reload } = useApi(loadAll, [], empty)
  const docs = useApi(() => inv.documents(), [], [])
  const counts = useApi(inv.counts, [], [])
  const moves = useApi(inv.movements, [tab === "movements"], [])
  const xfers = useApi(inv.transfers, [tab === "transfers"], [])
  // The menu is only needed for menu-item wastage, and only readable with menu.view.
  const canMenu = can(me, "menu.view")
  const menu = useApi(() => (form === "menuWaste" && canMenu ? listItems() : Promise.resolve([])), [form === "menuWaste", canMenu], [])
  const reloadAll = () => {
    reload()
    docs.reload()
    counts.reload()
    moves.reload()
    xfers.reload()
  }

  const unitById = Object.fromEntries(data.units.map((u) => [u.id, u]))
  const ingById = Object.fromEntries(data.ingredients.map((i) => [i.id, i]))
  const locById = Object.fromEntries(data.locations.map((l) => [l.id, l.name]))
  const locationId = (name: unknown) => data.locations.find((l) => l.name === name)?.id ?? null // "Not set (first location by name)" → null
  const balanceRows = data.balances.map((b) => ({
    ...b,
    id: `${b.location_id}:${b.ingredient_id}`,
    qty: num(b.quantity),
    cost: num(b.avg_cost),
    val: num(b.value),
    state: num(b.quantity) < 0 ? "Negative" : b.low ? "Low" : "In Stock",
    reorderQty: num(ingById[b.ingredient_id]?.reorder_qty),
  }))
  const low = balanceRows.filter((b) => b.state !== "In Stock")
  const stockValue = balanceRows.reduce((s, b) => s + Math.max(b.val, 0), 0)
  const pendingDocs = docs.data.filter((d) => d.status === "PendingApproval")
  const pendingCounts = counts.data.filter((c) => c.status === "Submitted")

  const ingOpts = data.ingredients.filter((i) => i.is_active).map((i) => i.name_en)
  const locOpts = data.locations.filter((l) => l.is_active).map((l) => l.name)
  const unitOpts = data.units.map((u) => u.code)
  const ingByName = (n: unknown) => data.ingredients.find((i) => i.name_en === n)
  const locByName = (n: unknown) => data.locations.find((l) => l.name === n)
  const unitByCode = (c: unknown, ing?: inv.Ingredient) => data.units.find((u) => u.code === c)?.id ?? ing?.stock_uom_id ?? ""
  const lineFields: Field[] = [
    { name: "ingredient", label: "Ingredient", type: "select", options: ingOpts, required: true },
    { name: "location", label: "Location", type: "select", options: locOpts, required: true, half: true },
    { name: "qty", label: "Quantity", type: "number", required: true, half: true, hint: "For an adjustment, a negative number removes stock" },
    { name: "unit", label: "Unit", type: "select", options: unitOpts, half: true, hint: "Default: the stock unit" },
    { name: "reason", label: "Reason", required: true, half: true },
  ]

  return (
    <Page>
      <PageHeader
        title="Inventory"
        description="Stock changes only through recorded transactions, so on-hand quantities can't be edited directly."
        actions={
          manage && (
            <>
              <Button variant="outline" onClick={() => setForm("Issue")}>
                <Minus />
                Issue stock
              </Button>
              <Button variant="outline" onClick={() => setForm("Adjustment")}>
                <Scale />
                Adjustment
              </Button>
              <Button onClick={() => setForm("count")}>
                <ClipboardPlus />
                Start count
              </Button>
            </>
          )
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "overview", label: "Overview" },
          { value: "ingredients", label: "Ingredients", count: data.ingredients.length },
          { value: "balances", label: "Balances" },
          { value: "movements", label: "Movements" },
          { value: "documents", label: "Adjustments & wastage", count: pendingDocs.length || undefined },
          { value: "counts", label: "Counts", count: pendingCounts.length || undefined },
          { value: "transfers", label: "Transfers" },
          { value: "locations", label: "Locations" },
        ]}
      />
      {tab === "overview" && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <Stat label="Stock value" value={usd(stockValue)} icon={DollarSign} href="/reports/RPT-17" hint="At weighted average cost" />
            <Stat label="Low stock" value={low.filter((b) => b.state === "Low").length} icon={AlertTriangle} tone="warning" href="/inventory?tab=balances" />
            <Stat label="Expiring soon" value={data.expiring.length} icon={Clock3} tone="warning" href="/inventory?tab=balances" hint="Batches within the warning period" />
            <Stat label="Negative stock" value={low.filter((b) => b.state === "Negative").length} icon={PackageX} tone="danger" href="/inventory?tab=balances" />
            <Stat
              label="Pending approvals"
              value={pendingDocs.length + pendingCounts.length}
              icon={ShieldCheck}
              href={pendingCounts.length ? "/inventory?tab=counts" : "/inventory?tab=documents"}
            />
          </section>
          <Panel
            title="Low-stock items"
            description="At or below reorder level"
            actions={
              low.length > 0 && (
                <Button
                  variant="outline"
                  onClick={() =>
                    void act(async () => {
                      const r = await inv.requestsFromLowStock()
                      router.push(`/purchasing?tab=requests&highlight=${r.id}`)
                    }, "Purchase request created for every low-stock item")
                  }
                >
                  <Plus />
                  Request all
                </Button>
              )
            }
          >
            <DataTable
              rows={low}
              exportName="low-stock"
              pageSize={8}
              emptyTitle="Nothing is low"
              columns={[
                { key: "ingredient_name_en", header: "Ingredient", render: (i) => <span className="font-medium">{i.ingredient_name_en}</span> },
                { key: "location_name", header: "Location" },
                { key: "qty", header: "On hand", align: "right", render: (i) => inv.qty(i.qty, i.unit) },
                { key: "reorder_level", header: "Reorder level", align: "right", render: (i) => inv.qty(i.reorder_level, i.unit) },
                { key: "reorderQty", header: "Suggested", align: "right", render: (i) => inv.qty(i.reorderQty, i.unit) },
                { key: "state", header: "State", render: (i) => <StatusBadge status={i.state} /> },
              ]}
            />
          </Panel>
          {data.expiring.length > 0 && (
            <Panel title="Expiring batches">
              <DataTable
                rows={data.expiring.map((e, n) => ({ ...e, id: `${e.batch_no}-${n}` }))}
                exportName="expiring"
                columns={[
                  { key: "ingredient", header: "Ingredient" },
                  { key: "batch_no", header: "Batch" },
                  { key: "location", header: "Location" },
                  { key: "expiry_date", header: "Expires" },
                  { key: "expired", header: "State", render: (e) => <StatusBadge status={e.expired ? "Expired" : "Expiring"} /> },
                ]}
              />
            </Panel>
          )}
        </>
      )}
      {tab === "ingredients" && (
        <CrudTable
          noun="Ingredient"
          canAdd={manage}
          canEdit={manage}
          rows={data.ingredients.map((i) => ({
            ...i,
            unit: unitById[i.stock_uom_id]?.code ?? "",
            reorder: num(i.reorder_level),
            reorderQty: num(i.reorder_qty),
            tracking: i.track_batch || i.track_expiry ? "Batch & expiry" : "Quantity",
            usedFrom: i.default_location_id ? (locById[i.default_location_id] ?? "Other branch") : "",
          }))}
          onSave={(v, e) =>
            save(() =>
              inv.saveIngredient(
                e
                  ? {
                      name_en: v.name,
                      name_km: v.km || null,
                      category: v.category,
                      reorder_level: String(v.reorder || 0),
                      reorder_qty: String(v.reorderQty || 0),
                      // A default at another branch isn't listed here; keep it unless a location is chosen
                      ...(e.usedFrom === "Other branch" && !locationId(v.location) ? {} : { default_location_id: locationId(v.location) }),
                    }
                  : {
                      code: v.code,
                      name_en: v.name,
                      name_km: v.km || null,
                      category: v.category,
                      stock_uom_id: unitByCode(v.unit),
                      reorder_level: String(v.reorder || 0),
                      reorder_qty: String(v.reorderQty || 0),
                      track_batch: Boolean(v.batch),
                      track_expiry: Boolean(v.batch),
                      default_location_id: locationId(v.location),
                    },
                e?.id
              )
            ).then(reload)
          }
          filters={[{ key: "category", label: "Category" }]}
          columns={[
            { key: "code", header: "Code" },
            { key: "name_en", header: "English" },
            { key: "name_km", header: "Khmer", render: (i) => i.name_km ?? "" },
            { key: "category", header: "Category" },
            { key: "unit", header: "Stock unit" },
            { key: "reorder", header: "Reorder level", align: "right" },
            { key: "reorderQty", header: "Reorder qty", align: "right" },
            { key: "tracking", header: "Tracking" },
            { key: "usedFrom", header: "Used from", render: (i) => i.usedFrom || <span className="text-muted-foreground">Not set</span> },
          ]}
          fields={[
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", half: true },
            { name: "code", label: "Code (can't change later)", required: true, half: true },
            { name: "category", label: "Category", required: true, half: true },
            { name: "unit", label: "Stock unit (can't change later)", type: "select", options: unitOpts, required: true, half: true },
            { name: "reorder", label: "Reorder level", type: "number", min: 0, required: true, half: true },
            { name: "reorderQty", label: "Reorder quantity", type: "number", min: 0, required: true, half: true },
            { name: "batch", label: "Track batches and expiry", type: "switch", half: true },
            {
              name: "location",
              label: "Sales use stock from",
              type: "select",
              options: ["Not set (first location by name)", ...data.locations.filter((l) => l.is_active).map((l) => l.name)],
              hint: "When an item is sent to the kitchen, its recipe takes this ingredient from here.",
            },
          ]}
          toForm={(i) => ({
            name: i.name_en,
            km: i.name_km ?? "",
            code: i.code,
            category: i.category,
            unit: i.unit,
            reorder: String(i.reorder),
            reorderQty: String(i.reorderQty),
            batch: i.track_batch,
            location: i.usedFrom && i.usedFrom !== "Other branch" ? i.usedFrom : "Not set (first location by name)",
          })}
        />
      )}
      {tab === "balances" && (
        <DataTable
          rows={balanceRows}
          exportName="stock-balances"
          pageSize={12}
          filters={[
            { key: "location_name", label: "Location", options: locOpts },
            { key: "state", label: "State", options: ["In Stock", "Low", "Negative"] },
          ]}
          columns={[
            { key: "ingredient_name_en", header: "Ingredient", render: (i) => <span className="font-medium">{i.ingredient_name_en}</span> },
            { key: "location_name", header: "Location" },
            { key: "qty", header: "On hand", align: "right", render: (i) => inv.qty(i.qty, i.unit) },
            { key: "cost", header: "Avg cost", align: "right", render: (i) => usd(i.cost) },
            { key: "val", header: "Value", align: "right", render: (i) => usd(i.val) },
            { key: "state", header: "State", render: (i) => <StatusBadge status={i.state} /> },
          ]}
        />
      )}
      {tab === "movements" && (
        <DataTable
          rows={moves.data.map((m) => ({
            ...m,
            time: when(m.posted_at),
            ingredient: ingById[m.ingredient_id]?.name_en ?? "",
            unit: unitById[ingById[m.ingredient_id]?.stock_uom_id ?? ""]?.code ?? "",
            location: locById[m.location_id] ?? "",
            type: TXN_LABEL[m.txn_type] ?? m.txn_type,
            q: num(m.quantity),
          }))}
          exportName="stock-movements"
          pageSize={14}
          emptyTitle={moves.loading ? "Loading…" : "No stock movements"}
          filters={[{ key: "ingredient", label: "Ingredient" }, { key: "type", label: "Type" }]}
          columns={[
            { key: "time", header: "Time" },
            { key: "ingredient", header: "Ingredient" },
            { key: "type", header: "Type" },
            {
              key: "q",
              header: "Qty",
              align: "right",
              render: (m) => (
                <span className={m.q < 0 ? "text-danger" : "text-success"}>
                  {m.q > 0 && "+"}
                  {inv.qty(m.q, m.unit)}
                </span>
              ),
            },
            { key: "location", header: "Location" },
            { key: "unit_cost", header: "Unit cost", align: "right", render: (m) => usd(num(m.unit_cost)) },
            { key: "balance_after", header: "Balance", align: "right", render: (m) => inv.qty(m.balance_after) },
            { key: "reason", header: "Reason", render: (m) => m.reason ?? "—" },
          ]}
          rowActions={(m) => [
            {
              label: "Post reversal",
              icon: Undo2,
              destructive: true,
              hidden: () => !manage || m.txn_type === "REVERSAL" || m.txn_type === "SALE_CONSUMPTION" || !!m.reverses_txn_id,
              onClick: () =>
                confirmAction({
                  title: "Reverse this transaction?",
                  effect: "The original stays in history. A referencing entry with the opposite sign is posted.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Post reversal",
                  onConfirm: (reason) => void act(() => inv.reverseTxn(m.id, reason), "Reversal posted", reloadAll),
                }),
            },
          ]}
        />
      )}
      {tab === "documents" && (
        <DataTable
          rows={docs.data.map((d) => ({
            ...d,
            date: when(d.created_at),
            location: locById[d.location_id] ?? "",
            items: d.lines.map((l) => `${ingById[l.ingredient_id]?.name_en ?? "?"} ${inv.qty(l.quantity, unitById[l.uom_id]?.code)}`).join(", "),
            value: num(d.total_value),
            state: STATUS[d.status] ?? d.status,
          }))}
          exportName="stock-documents"
          emptyTitle="No stock documents"
          toolbar={
            manage && (
              <>
                <Button variant="outline" onClick={() => setForm("Wastage")}>
                  <Trash2 />
                  Ingredient wastage
                </Button>
                <Button variant="outline" disabled={!canMenu} onClick={() => setForm("menuWaste")}>
                  <Trash2 />
                  Menu item wastage
                </Button>
              </>
            )
          }
          filters={[
            { key: "doc_type", label: "Type", options: ["Issue", "Adjustment", "Wastage", "Receipt", "Opening"] },
            { key: "state", label: "Status", options: ["Draft", "Pending Approval", "Posted", "Rejected"] },
          ]}
          columns={[
            { key: "doc_no", header: "Document" },
            { key: "date", header: "Date" },
            { key: "doc_type", header: "Type" },
            { key: "location", header: "Location" },
            { key: "items", header: "Items" },
            { key: "reason", header: "Reason", render: (d) => d.reason ?? "—" },
            { key: "value", header: "Value", align: "right", render: (d) => usd(d.value) },
            { key: "state", header: "Status", render: (d) => <StatusBadge status={d.state} /> },
          ]}
          rowActions={(d) => [
            {
              label: "Approve and post",
              icon: Check,
              hidden: () => !approve || d.status !== "PendingApproval",
              onClick: () => void act(() => inv.decideDocument(d.id, true), `${d.doc_no} posted`, reloadAll),
            },
            {
              label: "Reject",
              icon: X,
              destructive: true,
              hidden: () => !approve || d.status !== "PendingApproval",
              onClick: () => void act(() => inv.decideDocument(d.id, false), `${d.doc_no} rejected`, reloadAll),
            },
          ]}
        />
      )}
      {tab === "counts" && (
        <DataTable
          rows={counts.data.map((c) => ({
            ...c,
            date: when(c.created_at),
            location: locById[c.location_id] ?? "",
            items: c.lines.length,
            variance: c.lines.reduce((s, l) => s + num(l.variance_value), 0),
            state: c.status === "Submitted" ? "Pending Approval" : c.status === "Draft" ? "Counting" : c.status,
          }))}
          exportName="stock-counts"
          emptyTitle="No counts yet"
          onRowClick={(r) => router.push(`/inventory/counts/${r.id}`)}
          columns={[
            { key: "count_no", header: "Count" },
            { key: "date", header: "Started" },
            { key: "location", header: "Location" },
            { key: "progress", header: "Counted", align: "right" },
            { key: "variance", header: "Variance", align: "right", render: (r) => (r.status === "Draft" ? "—" : usd(r.variance)) },
            { key: "state", header: "Status", render: (r) => <StatusBadge status={r.state} /> },
          ]}
        />
      )}
      {tab === "transfers" && (
        <DataTable
          rows={xfers.data.map((t) => ({
            ...t,
            date: when(t.created_at),
            from: locById[t.from_location_id] ?? "",
            to: locById[t.to_location_id] ?? "",
            items: t.lines.map((l) => `${ingById[l.ingredient_id]?.name_en ?? "?"} ${inv.qty(l.quantity, unitById[l.uom_id]?.code)}`).join(", "),
          }))}
          exportName="transfers"
          emptyTitle="No transfers"
          toolbar={manage && <Button onClick={() => setForm("transfer")}>New transfer</Button>}
          columns={[
            { key: "transfer_no", header: "Transfer" },
            { key: "date", header: "Date" },
            { key: "from", header: "From" },
            { key: "to", header: "To" },
            { key: "items", header: "Items" },
            { key: "status", header: "Status", render: (t) => <StatusBadge status={t.status} /> },
          ]}
        />
      )}
      {tab === "locations" && (
        <DataTable
          rows={data.locations.map((l) => ({
            ...l,
            items: balanceRows.filter((b) => b.location_id === l.id).length,
            status: l.is_active ? "Active" : "Inactive",
          }))}
          exportName="locations"
          columns={[
            { key: "name", header: "Location" },
            { key: "items", header: "Ingredients held", align: "right" },
            { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
          ]}
        />
      )}

      <RecordDialog
        open={form === "Issue" || form === "Adjustment" || form === "Wastage"}
        onOpenChange={(o) => !o && setForm(null)}
        title={form === "Issue" ? "Issue stock" : form === "Wastage" ? "Record ingredient wastage" : "Manual adjustment"}
        description={
          form === "Issue"
            ? "Issues that would make stock negative are rejected."
            : "Above your value threshold it waits for a manager's approval before posting."
        }
        fields={lineFields}
        submitLabel="Post"
        onSubmit={(v) => {
          const ing = ingByName(v.ingredient)
          const kind = form as string
          return save(async () => {
            const d = await inv.postDocument({
              doc_type: kind,
              location_id: locByName(v.location)!.id,
              reason: String(v.reason),
              lines: [{ ingredient_id: ing!.id, quantity: kind === "Adjustment" ? String(v.qty) : String(Math.abs(Number(v.qty))), uom_id: unitByCode(v.unit, ing) }],
            })
            return d
          }).then((d) => {
            if (d.status === "PendingApproval") setTimeout(() => setTab("documents"), 0)
            reloadAll()
          })
        }}
      />
      <RecordDialog
        open={form === "menuWaste"}
        onOpenChange={(o) => !o && setForm(null)}
        title="Record menu item wastage"
        description="Prepared items are converted to ingredients by the recipe in effect."
        fields={[
          {
            name: "variant",
            label: "Menu item",
            type: "select",
            required: true,
            options: menu.data.flatMap((m) => m.raw.variants.filter((x) => x.is_active).map((x) => (x.name_en === "Regular" ? m.name : `${m.name} (${x.name_en})`))),
          },
          { name: "qty", label: "Portions", type: "number", min: 1, required: true, half: true },
          { name: "reason", label: "Reason", required: true, half: true },
        ]}
        onSubmit={(v) => {
          const variant = menu.data
            .flatMap((m) => m.raw.variants.map((x) => ({ id: x.id, label: x.name_en === "Regular" ? m.name : `${m.name} (${x.name_en})` })))
            .find((x) => x.label === v.variant)
          return save(() => inv.menuWastage(variant!.id, Number(v.qty), String(v.reason))).then(reloadAll)
        }}
      />
      <RecordDialog
        open={form === "transfer"}
        onOpenChange={(o) => !o && setForm(null)}
        title="Transfer between locations"
        fields={[
          { name: "from", label: "From", type: "select", options: locOpts, required: true, half: true },
          { name: "to", label: "To", type: "select", options: locOpts, required: true, half: true, validate: (v, a) => (v && v === a.from ? "Destination must differ from source" : undefined) },
          { name: "ingredient", label: "Ingredient", type: "select", options: ingOpts, required: true },
          { name: "qty", label: "Quantity", type: "number", min: 0.001, required: true, half: true },
          { name: "unit", label: "Unit", type: "select", options: unitOpts, half: true },
        ]}
        onSubmit={(v) => {
          const ing = ingByName(v.ingredient)
          return save(() =>
            inv.transfer({
              from_location_id: locByName(v.from)!.id,
              to_location_id: locByName(v.to)!.id,
              lines: [{ ingredient_id: ing!.id, quantity: String(v.qty), uom_id: unitByCode(v.unit, ing) }],
            })
          ).then(reloadAll)
        }}
      />
      <RecordDialog
        open={form === "count"}
        onOpenChange={(o) => !o && setForm(null)}
        title="Start a stock count"
        description="Every ingredient held at the location goes on the sheet. System quantities stay hidden until you submit."
        fields={[{ name: "location", label: "Location", type: "select", options: locOpts, required: true }]}
        submitLabel="Start count"
        onSubmit={(v) => save(() => inv.startCount(locByName(v.location)!.id)).then((c) => router.push(`/inventory/counts/${c.id}`))}
      />
    </Page>
  )
}
