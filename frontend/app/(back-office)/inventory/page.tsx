"use client"

import { useRouter } from "next/navigation"
import {
  AlertTriangle,
  ClipboardPlus,
  Clock3,
  DollarSign,
  Minus,
  PackageX,
  Plus,
  Scale,
  ShieldCheck,
  Undo2,
} from "lucide-react"
import * as React from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  CrudTable,
  RecordDialog,
  newId,
  type Field,
} from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction, requestApproval } from "@/components/rms/dialog-host"
import {
  LinkButton,
  Page,
  PageHeader,
  PageTabs,
  Panel,
  Stat,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import { ingredients, movements } from "@/lib/rms/back-office"

const stock = (i: (typeof ingredients)[number]) =>
  i.onHand < 0 ? "Negative" : i.onHand <= i.reorder ? "Low" : "In Stock"
const units = ["kg", "g", "L", "ml", "piece"]
const locations = ["Dry store", "Chiller", "Freezer", "Bar"]
const wasteReasons = [
  "Spoiled",
  "Burnt",
  "Dropped",
  "Expired",
  "Prepared but cancelled",
]

export default function InventoryPage() {
  const router = useRouter()
  const [tab, setTab] = useTab("overview")
  const [form, setForm] = React.useState<null | "issue" | "adjust">(null)
  const low = ingredients.filter((i) => i.onHand <= i.reorder)
  const value = ingredients.reduce(
    (s, i) => s + Math.max(i.onHand, 0) * i.cost,
    0
  )
  const expiring = ingredients.filter((i) => i.expiry)
  const moveFields: Field[] = [
    {
      name: "ingredient",
      label: "Ingredient",
      type: "select",
      options: ingredients.map((i) => i.name),
      required: true,
    },
    {
      name: "qty",
      label: "Quantity",
      type: "number",
      required: true,
      min: 0.001,
      half: true,
    },
    {
      name: "unit",
      label: "Unit",
      type: "select",
      options: units,
      required: true,
      half: true,
    },
    {
      name: "reason",
      label: "Reason",
      type: "select",
      options: [
        "Staff meal",
        "Cleaning use",
        "Correction",
        "Breakage",
        "Other",
      ],
      required: true,
    },
  ]
  return (
    <Page>
      <PageHeader
        title="Inventory"
        description="Stock changes only through recorded transactions, so on-hand quantities can't be edited directly."
        actions={
          <>
            <Button variant="outline" onClick={() => setForm("issue")}>
              <Minus />
              Issue stock
            </Button>
            <Button variant="outline" onClick={() => setForm("adjust")}>
              <Scale />
              Adjustment
            </Button>
            <LinkButton href="/inventory/counts/CNT-032">
              <ClipboardPlus />
              Start count
            </LinkButton>
          </>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "overview", label: "Overview" },
          { value: "ingredients", label: "Ingredients" },
          { value: "balances", label: "Balances" },
          { value: "movements", label: "Movements" },
          { value: "counts", label: "Counts" },
          { value: "wastage", label: "Wastage" },
          { value: "transfers", label: "Transfers" },
          { value: "locations", label: "Locations" },
        ]}
      />
      {tab === "overview" && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <Stat
              label="Stock value"
              value={usd(value)}
              icon={DollarSign}
              href="/reports/RPT-17"
              hint="At weighted average cost"
            />
            <Stat
              label="Low stock"
              value={low.length}
              icon={AlertTriangle}
              tone="warning"
              href="/inventory?tab=balances"
            />
            <Stat
              label="Expiring soon"
              value={2}
              icon={Clock3}
              tone="warning"
              href="/inventory?tab=balances"
              hint="Within 3 days"
            />
            <Stat
              label="Negative stock"
              value={ingredients.filter((i) => i.onHand < 0).length}
              icon={PackageX}
              tone="danger"
              href="/inventory?tab=movements"
            />
            <Stat
              label="Pending approvals"
              value={1}
              icon={ShieldCheck}
              href="/inventory?tab=counts"
            />
          </section>
          <Panel
            title="Low-stock items"
            description="At or below reorder level"
          >
            <DataTable
              rows={low}
              exportName="low-stock"
              pageSize={8}
              columns={[
                {
                  key: "name",
                  header: "Ingredient",
                  render: (i) => <span className="font-medium">{i.name}</span>,
                },
                { key: "location", header: "Location" },
                {
                  key: "onHand",
                  header: "On hand",
                  align: "right",
                  render: (i) => `${i.onHand} ${i.unit}`,
                },
                {
                  key: "reorder",
                  header: "Reorder level",
                  align: "right",
                  render: (i) => `${i.reorder} ${i.unit}`,
                },
                {
                  key: "reorderQty",
                  header: "Suggested",
                  align: "right",
                  render: (i) => `${i.reorderQty} ${i.unit}`,
                },
                { key: "supplier", header: "Preferred supplier" },
                {
                  key: "state",
                  header: "State",
                  value: stock,
                  render: (i) => <StatusBadge status={stock(i)} />,
                },
              ]}
              rowActions={(i) => [
                {
                  label: "Create purchase request",
                  icon: Plus,
                  onClick: () => {
                    toast.success(
                      `Purchase request created for ${i.reorderQty} ${i.unit} ${i.name}`
                    )
                    router.push("/purchasing?tab=requests")
                  },
                },
              ]}
            />
          </Panel>
        </>
      )}
      {tab === "ingredients" && (
        <CrudTable
          noun="Ingredient"
          seed={ingredients}
          filters={[
            { key: "cat", label: "Category" },
            { key: "location", label: "Location", options: locations },
          ]}
          columns={[
            { key: "code", header: "Code" },
            { key: "name", header: "English" },
            { key: "km", header: "Khmer" },
            { key: "cat", header: "Category" },
            { key: "unit", header: "Stock unit" },
            { key: "location", header: "Location" },
            { key: "reorder", header: "Reorder level", align: "right" },
            {
              key: "track",
              header: "Tracking",
              value: (i) => (i.batch ? "Batch & expiry" : "Quantity"),
            },
          ]}
          fields={[
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", required: true, half: true },
            { name: "code", label: "Code", required: true, half: true },
            {
              name: "cat",
              label: "Category",
              type: "select",
              options: [
                "Dry goods",
                "Meat",
                "Seafood",
                "Produce",
                "Dairy & cream",
                "Beverage",
                "Spices",
              ],
              required: true,
              half: true,
            },
            {
              name: "unit",
              label: "Stock unit",
              type: "select",
              options: units,
              required: true,
              half: true,
            },
            {
              name: "location",
              label: "Storage location",
              type: "select",
              options: locations,
              required: true,
              half: true,
            },
            {
              name: "reorder",
              label: "Reorder level",
              type: "number",
              min: 0,
              required: true,
              half: true,
            },
            {
              name: "reorderQty",
              label: "Reorder quantity",
              type: "number",
              min: 0,
              required: true,
              half: true,
            },
            {
              name: "batch",
              label: "Track batches and expiry",
              type: "switch",
            },
          ]}
          toRow={(v, e) => ({
            ...(e ?? {
              id: newId(),
              onHand: 0,
              cost: 0,
              expiry: "",
              supplier: "",
            }),
            code: String(v.code),
            name: String(v.name),
            km: String(v.km),
            cat: String(v.cat),
            unit: String(v.unit),
            location: String(v.location),
            reorder: Number(v.reorder),
            reorderQty: Number(v.reorderQty),
            batch: Boolean(v.batch),
          })}
        />
      )}
      {tab === "balances" && (
        <DataTable
          rows={ingredients}
          exportName="stock-balances"
          pageSize={12}
          filters={[
            { key: "location", label: "Location", options: locations },
            {
              key: "state",
              label: "State",
              options: ["In Stock", "Low", "Negative"],
              value: stock,
            },
          ]}
          columns={[
            {
              key: "name",
              header: "Ingredient",
              render: (i) => <span className="font-medium">{i.name}</span>,
            },
            { key: "location", header: "Location" },
            {
              key: "onHand",
              header: "On hand",
              align: "right",
              render: (i) => `${i.onHand} ${i.unit}`,
            },
            {
              key: "cost",
              header: "Avg cost",
              align: "right",
              render: (i) => usd(i.cost),
            },
            {
              key: "value",
              header: "Value",
              align: "right",
              value: (i) => Math.max(i.onHand, 0) * i.cost,
              render: (i) => usd(Math.max(i.onHand, 0) * i.cost),
            },
            {
              key: "expiry",
              header: "Next expiry",
              render: (i) => i.expiry || "—",
            },
            {
              key: "state",
              header: "State",
              value: stock,
              render: (i) => (
                <StatusBadge
                  status={
                    expiring.includes(i) && ["i3", "i4"].includes(i.id)
                      ? "Expiring"
                      : stock(i)
                  }
                />
              ),
            },
          ]}
        />
      )}
      {tab === "movements" && (
        <DataTable
          rows={movements}
          exportName="stock-movements"
          pageSize={14}
          filters={[
            { key: "ingredient", label: "Ingredient" },
            { key: "type", label: "Type" },
          ]}
          columns={[
            { key: "time", header: "Time" },
            { key: "ingredient", header: "Ingredient" },
            {
              key: "type",
              header: "Type",
              render: (m) => <code className="text-xs">{m.type}</code>,
            },
            {
              key: "qty",
              header: "Qty",
              align: "right",
              render: (m) => (
                <span className={m.qty < 0 ? "text-danger" : "text-success"}>
                  {m.qty > 0 && "+"}
                  {m.qty} {m.unit}
                </span>
              ),
            },
            { key: "location", header: "Location" },
            {
              key: "unitCost",
              header: "Unit cost",
              align: "right",
              render: (m) => usd(m.unitCost),
            },
            { key: "balance", header: "Balance", align: "right" },
            { key: "user", header: "User" },
            { key: "ref", header: "Source" },
          ]}
          rowActions={(m) => [
            {
              label: "Post reversal",
              icon: Undo2,
              destructive: true,
              hidden: () =>
                m.type === "REVERSAL" || m.type === "SALE_CONSUMPTION",
              onClick: () =>
                confirmAction({
                  title: "Reverse this transaction?",
                  effect:
                    "The original stays in history. A referencing entry with the opposite sign is posted.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Post reversal",
                  onConfirm: () => toast.success("Reversal posted"),
                }),
            },
          ]}
        />
      )}
      {tab === "counts" && (
        <DataTable
          rows={[
            {
              id: "CNT-032",
              date: "08/11/2026",
              scope: "Chiller · full",
              items: 6,
              variance: "—",
              status: "Counting",
              by: "Rotha Ly",
            },
            {
              id: "CNT-031",
              date: "07/11/2026",
              scope: "Chiller · eggs",
              items: 1,
              variance: "−$0.56",
              status: "Posted",
              by: "Rotha Ly",
            },
            {
              id: "CNT-030",
              date: "01/11/2026",
              scope: "Dry store · full",
              items: 18,
              variance: "−$14.20",
              status: "Pending Approval",
              by: "Rotha Ly",
            },
          ]}
          exportName="stock-counts"
          onRowClick={(r) =>
            r.status === "Counting" && router.push(`/inventory/counts/${r.id}`)
          }
          columns={[
            { key: "id", header: "Count" },
            { key: "date", header: "Date" },
            { key: "scope", header: "Scope" },
            { key: "items", header: "Items", align: "right" },
            { key: "variance", header: "Variance", align: "right" },
            { key: "by", header: "Counted by" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          rowActions={(r) => [
            {
              label: "Approve variance",
              icon: ShieldCheck,
              hidden: () => r.status !== "Pending Approval",
              onClick: () =>
                requestApproval({
                  action: `Post count ${r.id}`,
                  amount: r.variance,
                  onApproved: () => toast.success("Variance posted to stock"),
                }),
            },
          ]}
        />
      )}
      {tab === "wastage" && (
        <CrudTable
          noun="Wastage record"
          addLabel="Record wastage"
          canEdit={false}
          seed={[
            {
              id: "WST-118",
              date: "08/11/2026",
              item: "Mixed vegetables",
              qty: "1.2 kg",
              reason: "Spoiled",
              station: "Cold",
              value: 1.92,
              user: "Bunna Kim",
            },
            {
              id: "WST-117",
              date: "07/11/2026",
              item: "Fish Amok (prepared)",
              qty: "1 portion",
              reason: "Prepared but cancelled",
              station: "Hot",
              value: 3.05,
              user: "Ratha Seng",
            },
          ]}
          columns={[
            { key: "id", header: "Record" },
            { key: "date", header: "Date" },
            { key: "item", header: "Item" },
            { key: "qty", header: "Quantity", align: "right" },
            { key: "reason", header: "Reason" },
            { key: "station", header: "Station" },
            {
              key: "value",
              header: "Value",
              align: "right",
              render: (r) => usd(r.value),
            },
            { key: "user", header: "Recorded by" },
          ]}
          fields={[
            { name: "item", label: "Ingredient or menu item", required: true },
            {
              name: "qty",
              label: "Quantity and unit",
              required: true,
              half: true,
            },
            {
              name: "reason",
              label: "Reason",
              type: "select",
              options: wasteReasons,
              required: true,
              half: true,
            },
            {
              name: "station",
              label: "Station",
              type: "select",
              options: ["Hot", "Cold", "Beverage", "Dessert", "Bar"],
              required: true,
            },
          ]}
          toRow={(v) => ({
            id: `WST-${119 + Math.floor(Math.random() * 800)}`,
            date: "08/11/2026",
            item: String(v.item),
            qty: String(v.qty),
            reason: String(v.reason),
            station: String(v.station),
            value: 0,
            user: "Dara Pich",
          })}
        />
      )}
      {tab === "transfers" && (
        <CrudTable
          noun="Transfer"
          canEdit={false}
          seed={[
            {
              id: "TRF-054",
              date: "08/11/2026",
              from: "Dry store",
              to: "Bar",
              items: "Coffee beans 2 kg",
              status: "Received",
            },
            {
              id: "TRF-053",
              date: "07/11/2026",
              from: "Riverside",
              to: "BKK1",
              items: "Coconut cream 12 L",
              status: "In Transit",
            },
            {
              id: "TRF-052",
              date: "06/11/2026",
              from: "BKK1",
              to: "Riverside",
              items: "Jasmine rice 25 kg",
              status: "Difference",
            },
          ]}
          columns={[
            { key: "id", header: "Transfer" },
            { key: "date", header: "Date" },
            { key: "from", header: "From" },
            { key: "to", header: "To" },
            { key: "items", header: "Items" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            {
              name: "from",
              label: "From",
              type: "select",
              options: [...locations, "Riverside", "BKK1"],
              required: true,
              half: true,
            },
            {
              name: "to",
              label: "To",
              type: "select",
              options: [...locations, "Riverside", "BKK1"],
              required: true,
              half: true,
              validate: (v, a) =>
                v && v === a.from
                  ? "Destination must differ from source"
                  : undefined,
            },
            {
              name: "items",
              label: "Items and quantities",
              required: true,
              type: "textarea",
            },
          ]}
          toRow={(v) => ({
            id: `TRF-${55 + Math.floor(Math.random() * 900)}`,
            date: "08/11/2026",
            from: String(v.from),
            to: String(v.to),
            items: String(v.items),
            status: "In Transit",
          })}
        />
      )}
      {tab === "locations" && (
        <CrudTable
          noun="Location"
          seed={locations.map((name, i) => ({
            id: `l${i}`,
            name,
            branch: "Riverside",
            items: ingredients.filter((g) => g.location === name).length,
            status: "Active",
          }))}
          columns={[
            { key: "name", header: "Location" },
            { key: "branch", header: "Branch" },
            { key: "items", header: "Ingredients", align: "right" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            { name: "name", label: "Name", required: true },
            {
              name: "branch",
              label: "Branch",
              type: "select",
              options: ["Riverside", "BKK1", "Siem Reap"],
              required: true,
            },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            branch: String(v.branch),
            items: e?.items ?? 0,
            status: e?.status ?? "Active",
          })}
        />
      )}
      <RecordDialog
        open={!!form}
        onOpenChange={(o) => !o && setForm(null)}
        title={form === "issue" ? "Issue stock" : "Manual adjustment"}
        description={
          form === "adjust"
            ? "Adjustments above the value threshold go for approval before posting."
            : "Issues that would make stock negative are rejected."
        }
        fields={moveFields}
        submitLabel="Post"
        onSubmit={() =>
          toast.success(
            form === "issue" ? "Issue posted" : "Adjustment sent for approval"
          )
        }
      />
    </Page>
  )
}
