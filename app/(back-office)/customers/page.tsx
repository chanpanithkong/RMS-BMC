"use client"

import { useRouter } from "next/navigation"
import { Eye, Merge, UserX } from "lucide-react"
import { toast } from "sonner"
import { CrudTable, newId } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  MoneyText,
  Notice,
  Page,
  PageHeader,
  PageTabs,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import { customers } from "@/lib/rms/back-office"
import { useRms } from "@/lib/rms/store"

const maskPhone = (p: string) => p.replace(/\d(?=[\d ]{3})/g, "•")

export default function CustomersPage() {
  const router = useRouter()
  const { role } = useRms()
  const [tab, setTab] = useTab("customers")
  const masked = role === "AUDITOR"
  const dupes = customers.filter((c) =>
    customers.some((o) => o.id !== c.id && o.phone === c.phone)
  )
  return (
    <Page>
      <PageHeader
        title="Customers"
        description="Only customers who choose to be identified. Contact details are masked for roles without permission."
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "customers", label: "Customers", count: customers.length },
          { value: "credit", label: "Credit accounts" },
          {
            value: "duplicates",
            label: "Possible duplicates",
            count: dupes.length ? 1 : 0,
          },
        ]}
      />
      {tab === "customers" && (
        <CrudTable
          noun="Customer"
          seed={customers}
          searchPlaceholder="Phone, name or code…"
          onRowClick={(c) => router.push(`/customers/${c.id}`)}
          filters={[{ key: "segment", label: "Segment" }]}
          columns={[
            { key: "code", header: "Code" },
            {
              key: "name",
              header: "Name",
              render: (c) => <span className="font-medium">{c.name}</span>,
            },
            {
              key: "phone",
              header: "Phone",
              render: (c) => (masked ? maskPhone(c.phone) : c.phone),
            },
            {
              key: "segment",
              header: "Segment",
              render: (c) => (
                <StatusBadge
                  status={c.segment}
                  tone={c.segment === "VIP" ? "info" : "neutral"}
                />
              ),
            },
            { key: "visits", header: "Visits", align: "right" },
            {
              key: "spend",
              header: "Total spend",
              align: "right",
              render: (c) => <MoneyText value={c.spend} />,
            },
            { key: "last", header: "Last visit" },
            { key: "points", header: "Points", align: "right", hidden: true },
          ]}
          fields={[
            { name: "name", label: "Name", required: true, half: true },
            {
              name: "phone",
              label: "Phone",
              type: "tel",
              required: true,
              half: true,
              hint: "Starting with 0 or +855",
              validate: (v) =>
                v && !/^(\+855|0)[\d ]{7,12}$/.test(String(v))
                  ? "Enter a Cambodian number starting with 0 or +855"
                  : undefined,
            },
            { name: "email", label: "Email", type: "email", half: true },
            {
              name: "language",
              label: "Preferred language",
              type: "select",
              options: ["Khmer", "English"],
              half: true,
            },
            {
              name: "segment",
              label: "Classification",
              type: "select",
              options: ["Regular", "VIP", "Corporate"],
              half: true,
            },
            { name: "allergy", label: "Allergy notes", half: true },
            { name: "prefs", label: "Preferences", type: "textarea" },
            {
              name: "consent",
              label: "Consent to marketing messages",
              type: "switch",
            },
          ]}
          extraActions={(c) => [
            {
              label: "View profile",
              icon: Eye,
              onClick: () => router.push(`/customers/${c.id}`),
            },
            {
              label: "Anonymise",
              icon: UserX,
              destructive: true,
              onClick: () =>
                confirmAction({
                  title: `Anonymise ${c.name}?`,
                  effect:
                    "Personal details are removed permanently. Financial records stay under an anonymised reference.",
                  requireReason: true,
                  destructive: true,
                  confirmLabel: "Anonymise",
                  onConfirm: () => toast.success("Customer anonymised"),
                }),
            },
          ]}
          toRow={(v, e) => ({
            ...(e ?? {
              id: newId(),
              code: `C-${1000 + customers.length + 1}`,
              visits: 0,
              spend: 0,
              last: "—",
              points: 0,
              noShows: 0,
              credit: 0,
            }),
            name: String(v.name),
            phone: String(v.phone),
            email: String(v.email ?? ""),
            language: String(v.language || "Khmer"),
            segment: String(v.segment || "Regular"),
            allergy: String(v.allergy ?? ""),
            prefs: String(v.prefs ?? ""),
            consent: Boolean(v.consent),
          })}
        />
      )}
      {tab === "credit" && (
        <DataTable
          rows={[
            {
              id: "1",
              account: "Mekong Trading Co.",
              limit: 1500,
              balance: 500,
              terms: "Net 30",
              status: "Active",
            },
            {
              id: "2",
              account: "Riverside Hotel Group",
              limit: 3000,
              balance: 1420,
              terms: "Net 30",
              status: "Active",
            },
          ]}
          exportName="credit-accounts"
          columns={[
            { key: "account", header: "Account" },
            {
              key: "limit",
              header: "Credit limit",
              align: "right",
              render: (r) => usd(r.limit),
            },
            {
              key: "balance",
              header: "Balance",
              align: "right",
              render: (r) => usd(r.balance),
            },
            {
              key: "avail",
              header: "Available",
              align: "right",
              value: (r) => r.limit - r.balance,
              render: (r) => usd(r.limit - r.balance),
            },
            { key: "terms", header: "Terms" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
        />
      )}
      {tab === "duplicates" && (
        <>
          <Notice tone="warning">
            These records share a phone number. Merging keeps both histories and
            is audited.
          </Notice>
          <DataTable
            rows={dupes}
            exportName="duplicates"
            columns={[
              { key: "code", header: "Code" },
              { key: "name", header: "Name" },
              { key: "phone", header: "Phone" },
              { key: "visits", header: "Visits", align: "right" },
              {
                key: "spend",
                header: "Spend",
                align: "right",
                render: (c) => usd(c.spend),
              },
            ]}
            rowActions={(c) => [
              {
                label: "Merge into this record",
                icon: Merge,
                onClick: () =>
                  confirmAction({
                    title: `Keep ${c.name} and merge?`,
                    effect:
                      "The other record's orders move here and it is retired.",
                    confirmLabel: "Merge",
                    onConfirm: () => toast.success("Records merged"),
                  }),
              },
            ]}
          />
        </>
      )}
    </Page>
  )
}
