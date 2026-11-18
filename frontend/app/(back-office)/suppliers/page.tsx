"use client"

import { useRouter } from "next/navigation"
import { Ban, Check, Eye } from "lucide-react"
import { CrudTable } from "@/components/rms/crud"
import { Page, PageHeader, StatusBadge } from "@/components/rms/kit"
import * as pur from "@/lib/api/purchasing"
import { can, useSession } from "@/lib/api/session"
import { act, save, useApi } from "@/lib/api/use-api"

export default function SuppliersPage() {
  const router = useRouter()
  const { me } = useSession()
  const manage = can(me, "suppliers.manage")
  const list = useApi(pur.suppliers, [], [])
  const rows = list.data.map((s) => ({ ...s, shared: s.branch_ids.length ? "This branch" : "All branches" }))

  return (
    <Page>
      <PageHeader title="Suppliers" description="Supplier records, contacts and payment terms. Purchase history is on each supplier's page." />
      <CrudTable
        noun="Supplier"
        rows={rows}
        canAdd={manage}
        canEdit={manage}
        onRowClick={(s) => router.push(`/suppliers/${s.id}`)}
        onSave={(v, e) =>
          save(() =>
            pur.saveSupplier(
              {
                ...(e ? {} : { name: v.name, currency: v.currency || "USD" }),
                contact_person: v.contact,
                phone: v.phone,
                email: String(v.email ?? "") || null,
                address: String(v.address ?? "") || null,
                tax_id: String(v.tin ?? "") || null,
                payment_terms: v.terms || "Net 30",
              },
              e?.id
            )
          ).then(list.reload)
        }
        filters={[{ key: "status", label: "Status", options: ["Active", "Inactive"] }]}
        columns={[
          { key: "name", header: "Supplier", render: (s) => <span className="font-medium">{s.name}</span> },
          { key: "contact_person", header: "Contact" },
          { key: "phone", header: "Phone" },
          { key: "payment_terms", header: "Terms" },
          { key: "currency", header: "Currency" },
          { key: "shared", header: "Used by" },
          { key: "status", header: "Status", render: (s) => <StatusBadge status={s.status} /> },
        ]}
        fields={[
          { name: "name", label: "Supplier name (can't change later)", required: true },
          { name: "contact", label: "Contact person", required: true, half: true },
          { name: "phone", label: "Phone", type: "tel", required: true, half: true },
          { name: "email", label: "Email", type: "email", half: true },
          { name: "tin", label: "Tax ID", half: true },
          { name: "address", label: "Address" },
          { name: "terms", label: "Payment terms", half: true, hint: "e.g. Net 30, COD" },
          { name: "currency", label: "Currency", type: "select", options: ["USD", "KHR"], half: true },
        ]}
        toForm={(s) => ({
          name: s.name,
          contact: s.contact_person,
          phone: s.phone,
          email: s.email ?? "",
          tin: s.tax_id ?? "",
          address: s.address ?? "",
          terms: s.payment_terms,
          currency: s.currency,
        })}
        extraActions={(s) => [
          { label: "Open", icon: Eye, onClick: () => router.push(`/suppliers/${s.id}`) },
          ...(manage
            ? [
                s.status === "Active"
                  ? {
                      label: "Deactivate",
                      icon: Ban,
                      destructive: true,
                      onClick: () => void act(() => pur.saveSupplier({ status: "Inactive" }, s.id), `${s.name} deactivated`, list.reload),
                    }
                  : { label: "Activate", icon: Check, onClick: () => void act(() => pur.saveSupplier({ status: "Active" }, s.id), `${s.name} activated`, list.reload) },
              ]
            : []),
        ]}
      />
    </Page>
  )
}
