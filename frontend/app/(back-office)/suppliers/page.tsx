"use client"

import { useRouter } from "next/navigation"
import { Eye } from "lucide-react"
import { CrudTable, newId } from "@/components/rms/crud"
import { Page, PageHeader, StatusBadge } from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"
import { suppliers } from "@/lib/rms/back-office"

export default function SuppliersPage() {
  const router = useRouter()
  return (
    <Page>
      <PageHeader
        title="Suppliers"
        description="Contacts, payment terms, balances and delivery performance."
      />
      <CrudTable
        noun="Supplier"
        seed={suppliers}
        onRowClick={(s) => router.push(`/suppliers/${s.id}`)}
        filters={[
          { key: "status", label: "Status", options: ["Active", "Inactive"] },
          { key: "terms", label: "Terms" },
        ]}
        columns={[
          {
            key: "name",
            header: "Supplier",
            render: (s) => <span className="font-medium">{s.name}</span>,
          },
          { key: "contact", header: "Contact" },
          { key: "phone", header: "Phone" },
          { key: "terms", header: "Terms" },
          { key: "currency", header: "Currency" },
          {
            key: "balance",
            header: "Balance",
            align: "right",
            render: (s) => usd(s.balance),
          },
          {
            key: "onTime",
            header: "On time",
            align: "right",
            render: (s) => `${s.onTime}%`,
          },
          {
            key: "status",
            header: "Status",
            render: (s) => <StatusBadge status={s.status} />,
          },
        ]}
        fields={[
          { name: "name", label: "Supplier name", required: true },
          {
            name: "contact",
            label: "Contact person",
            required: true,
            half: true,
          },
          {
            name: "phone",
            label: "Phone",
            type: "tel",
            required: true,
            half: true,
          },
          { name: "email", label: "Email", type: "email", half: true },
          { name: "tin", label: "Tax ID (if provided)", half: true },
          { name: "address", label: "Address", required: true },
          {
            name: "terms",
            label: "Payment terms",
            type: "select",
            options: ["COD", "Net 7", "Net 14", "Net 30"],
            required: true,
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
        ]}
        extraActions={(s) => [
          {
            label: "View profile",
            icon: Eye,
            onClick: () => router.push(`/suppliers/${s.id}`),
          },
        ]}
        toRow={(v, e) => ({
          ...(e ?? { id: newId(), balance: 0, status: "Active", onTime: 100 }),
          name: String(v.name),
          contact: String(v.contact),
          phone: String(v.phone),
          email: String(v.email ?? ""),
          tin: String(v.tin ?? ""),
          address: String(v.address),
          terms: String(v.terms),
          currency: String(v.currency),
        })}
      />
    </Page>
  )
}
