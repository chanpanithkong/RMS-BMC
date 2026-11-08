"use client"

import { Check, CircleDollarSign, Undo2, X } from "lucide-react"
import { toast } from "sonner"
import { ChartCard } from "@/components/rms/chart-card"
import { CrudTable, newId } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction, requestApproval } from "@/components/rms/dialog-host"
import {
  Page,
  PageHeader,
  PageTabs,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { khr, usd } from "@/lib/rms/billing"
import { expenses } from "@/lib/rms/back-office"

const categories = [
  "Rent",
  "Electricity",
  "Water",
  "Internet",
  "Salaries",
  "Cleaning supplies",
  "Equipment repairs",
  "Delivery costs",
  "Platform commissions",
]
const money = (r: { amount: number; currency: string }) =>
  r.currency === "USD" ? usd(r.amount) : khr(r.amount)
const summary = categories
  .map((category) => ({
    category,
    total: expenses
      .filter(
        (e) =>
          e.category === category &&
          e.status !== "Rejected" &&
          e.currency === "USD"
      )
      .reduce((s, e) => s + e.amount, 0),
  }))
  .filter((c) => c.total > 0)

export default function ExpensesPage() {
  const [tab, setTab] = useTab("all")
  const pending = expenses.filter((e) => e.status === "Submitted")
  const baseCols = [
    { key: "id", header: "Expense" },
    { key: "date", header: "Date" },
    { key: "category", header: "Category" },
    { key: "description", header: "Description" },
    { key: "payee", header: "Payee" },
    { key: "amount", header: "Amount", align: "right" as const, render: money },
    { key: "by", header: "Submitted by", hidden: true },
    { key: "method", header: "Paid by", hidden: true },
    {
      key: "status",
      header: "Status",
      render: (r: (typeof expenses)[number]) => (
        <StatusBadge status={r.status} />
      ),
    },
  ]
  return (
    <Page>
      <PageHeader
        title="Expenses"
        description="Operating expenses and their supporting documents. This is not a full accounting ledger."
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "all", label: "All expenses" },
          { value: "approvals", label: "Approvals", count: pending.length },
          { value: "summary", label: "Summary" },
          { value: "categories", label: "Categories" },
          { value: "recurring", label: "Recurring" },
        ]}
      />
      {(tab === "all" || tab === "approvals") && (
        <CrudTable
          key={tab}
          noun="Expense"
          seed={tab === "all" ? expenses : pending}
          columns={baseCols}
          canAdd={tab === "all"}
          filters={[
            {
              key: "status",
              label: "Status",
              options: [
                "Draft",
                "Submitted",
                "Approved",
                "Rejected",
                "Paid",
                "Reversed",
              ],
            },
            { key: "category", label: "Category", options: categories },
          ]}
          fields={[
            {
              name: "category",
              label: "Category",
              type: "select",
              options: categories,
              required: true,
              half: true,
            },
            {
              name: "date",
              label: "Expense date",
              type: "date",
              required: true,
              half: true,
              validate: (v) =>
                v && String(v) > "2026-11-08"
                  ? "Expense date can't be in the future"
                  : undefined,
            },
            { name: "description", label: "Description", required: true },
            {
              name: "amount",
              label: "Amount",
              type: "number",
              required: true,
              min: 0.01,
              half: true,
            },
            {
              name: "currency",
              label: "Currency",
              type: "select",
              options: ["USD", "KHR"],
              required: true,
              half: true,
            },
            { name: "payee", label: "Payee", required: true },
            {
              name: "attachment",
              label: "Attachment (PDF, JPG or PNG, up to 10 MB)",
              type: "file",
            },
          ]}
          toRow={(v, e) => ({
            ...(e ?? {
              id: `EX-${newId().slice(1, 5).toUpperCase()}`,
              by: "Dara Pich",
              method: "",
              status: "Submitted",
            }),
            date: String(v.date),
            category: String(v.category),
            description: String(v.description),
            amount: Number(v.amount),
            currency: String(v.currency),
            payee: String(v.payee),
            attachment: String(v.attachment ?? ""),
          })}
          extraActions={(r, update) => [
            {
              label: "Approve",
              icon: Check,
              hidden: () => r.status !== "Submitted",
              onClick: () =>
                requestApproval({
                  action: `Approve ${r.id}`,
                  amount: money(r),
                  onApproved: (by) => {
                    update({ status: "Approved" })
                    toast.success(`Approved by ${by}`)
                  },
                }),
            },
            {
              label: "Reject",
              icon: X,
              destructive: true,
              hidden: () => r.status !== "Submitted",
              onClick: () =>
                confirmAction({
                  title: `Reject ${r.id}?`,
                  effect: "Rejected expenses can't be paid.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Reject",
                  onConfirm: () => update({ status: "Rejected" }),
                }),
            },
            {
              label: "Record payment",
              icon: CircleDollarSign,
              hidden: () => r.status !== "Approved",
              onClick: () => {
                update({ status: "Paid", method: "Bank Transfer" })
                toast.success("Payment recorded")
              },
            },
            {
              label: "Reverse",
              icon: Undo2,
              destructive: true,
              hidden: () => r.status !== "Paid",
              onClick: () =>
                confirmAction({
                  title: `Reverse ${r.id}?`,
                  effect:
                    "The original record stays. A manager must approve the reversal.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Request reversal",
                  onConfirm: () =>
                    requestApproval({
                      action: `Reverse ${r.id}`,
                      amount: money(r),
                      onApproved: () => update({ status: "Reversed" }),
                    }),
                }),
            },
          ]}
        />
      )}
      {tab === "summary" && (
        <ChartCard
          title="Expenses by category"
          description="USD expenses this month, excluding rejected"
          horizontal
          height={280}
          data={summary}
          xKey="category"
          series={[{ key: "total", label: "Total" }]}
          format={(v) => `$${v.toLocaleString()}`}
        />
      )}
      {tab === "categories" && (
        <CrudTable
          noun="Expense category"
          seed={categories.map((name, i) => ({
            id: `c${i}`,
            name,
            km: "—",
            attachment: i < 2 ? "Required" : "Optional",
            status: "Active",
          }))}
          columns={[
            { key: "name", header: "English" },
            { key: "km", header: "Khmer" },
            { key: "attachment", header: "Attachment" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            { name: "name", label: "English", required: true, half: true },
            { name: "km", label: "Khmer", required: true, half: true },
            {
              name: "attachment",
              label: "Attachment",
              type: "select",
              options: ["Required", "Optional"],
              required: true,
            },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            km: String(v.km),
            attachment: String(v.attachment),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "recurring" && (
        <>
          <DataTable
            rows={[
              {
                id: "1",
                name: "Monthly rent",
                category: "Rent",
                amount: 2400,
                currency: "USD",
                every: "1st of month",
                next: "01/12/2026",
              },
              {
                id: "2",
                name: "Fibre internet",
                category: "Internet",
                amount: 45,
                currency: "USD",
                every: "4th of month",
                next: "04/12/2026",
              },
            ]}
            exportName="recurring-expenses"
            columns={[
              { key: "name", header: "Template" },
              { key: "category", header: "Category" },
              {
                key: "amount",
                header: "Amount",
                align: "right",
                render: money,
              },
              { key: "every", header: "Schedule" },
              { key: "next", header: "Next draft" },
            ]}
          />
        </>
      )}
    </Page>
  )
}
