"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { Ban, Check, CircleDollarSign, Eye, Merge } from "lucide-react"
import { toast } from "sonner"
import { CrudTable, RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { Notice, Page, PageHeader, PageTabs, StatusBadge, useTab } from "@/components/rms/kit"
import { ApiError } from "@/lib/api/client"
import * as cus from "@/lib/api/customers"
import { can, useSession } from "@/lib/api/session"
import { act, num, save, useApi } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

const LANG: Record<string, string> = { km: "Khmer", en: "English" }

export default function CustomersPage() {
  const router = useRouter()
  const { me } = useSession()
  const manage = can(me, "customers.manage")
  const [tab, setTab] = useTab("customers")
  const list = useApi(() => cus.list(), [], [])
  const accts = useApi(() => (can(me, "credit.view") ? cus.accounts() : Promise.resolve([])), [me?.id], [])
  const [settleFor, setSettleFor] = React.useState<cus.CreditAccount | null>(null)
  const [openAcct, setOpenAcct] = React.useState(false)

  const rows = list.data.filter((c) => !c.anonymised).map((c) => ({ ...c, lang: LANG[c.preferred_language] ?? c.preferred_language }))
  // Possible duplicates: the same phone number on more than one record (needs unmasked contact details).
  const byPhone = new Map<string, typeof rows>()
  for (const c of rows) if (c.phone && !c.contact_masked) byPhone.set(c.phone, [...(byPhone.get(c.phone) ?? []), c])
  const dupes = [...byPhone.values()].filter((g) => g.length > 1).flatMap((g) => g.map((c) => ({ ...c, group: c.phone!, others: g.filter((x) => x.id !== c.id) })))

  return (
    <Page>
      <PageHeader title="Customers" description="Customer profiles, preferences and allergies, loyalty points and credit accounts." />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "customers", label: "Customers", count: rows.length },
          { value: "credit", label: "Credit accounts", count: accts.data.length },
          { value: "duplicates", label: "Possible duplicates", count: dupes.length || undefined },
        ]}
      />
      {tab === "customers" && (
        <>
          {rows.some((c) => c.contact_masked) && <Notice tone="info">Phone numbers and emails are partly hidden for your role.</Notice>}
          <CrudTable
            noun="Customer"
            rows={rows}
            canAdd={manage}
            canEdit={manage}
            onRowClick={(c) => router.push(`/customers/${c.id}`)}
            searchPlaceholder="Name, code or phone…"
            onSave={async (v, e) => {
              const body = {
                name: v.name,
                phone: String(v.phone ?? "") || null,
                email: String(v.email ?? "") || null,
                preferred_language: v.lang === "English" ? "en" : "km",
                classification: v.classification || "Regular",
                preferences: String(v.preferences ?? "") || null,
                allergy_notes: String(v.allergy ?? "") || null,
                consent_marketing: Boolean(v.consent),
              }
              if (e) return save(() => cus.update(e.id, body)).then(list.reload)
              try {
                await cus.create(body)
              } catch (err) {
                // The backend warns about a likely duplicate; let the user decide (FR-CUST-004).
                if (err instanceof ApiError && err.code === "POSSIBLE_DUPLICATE") {
                  const ok = window.confirm(`${err.message} Create a separate record anyway?`)
                  if (!ok) throw new Error("Not created. Use the existing customer instead.")
                  await save(() => cus.create(body, true))
                } else return save(() => Promise.reject(err))
              }
              list.reload()
            }}
            filters={[{ key: "classification", label: "Type", options: ["Regular", "VIP", "Corporate"] }]}
            columns={[
              { key: "code", header: "Code" },
              { key: "name", header: "Name", render: (c) => <span className="font-medium">{c.name}</span> },
              { key: "phone", header: "Phone", render: (c) => c.phone ?? "—" },
              { key: "classification", header: "Type", render: (c) => <StatusBadge status={c.classification} tone="neutral" /> },
              { key: "loyalty_points", header: "Points", align: "right" },
              { key: "allergy_notes", header: "Allergies", render: (c) => (c.allergy_notes ? <span className="text-danger">{c.allergy_notes}</span> : "—") },
              { key: "no_show_count", header: "No-shows", align: "right" },
            ]}
            fields={[
              { name: "name", label: "Name", required: true },
              { name: "phone", label: "Phone", type: "tel", half: true },
              { name: "email", label: "Email", type: "email", half: true },
              { name: "lang", label: "Language", type: "select", options: ["Khmer", "English"], half: true },
              { name: "classification", label: "Type", type: "select", options: ["Regular", "VIP", "Corporate"], half: true },
              { name: "preferences", label: "Preferences" },
              { name: "allergy", label: "Allergies", hint: "Shown on the POS when the customer is attached" },
              { name: "consent", label: "Agrees to marketing messages", type: "switch" },
            ]}
            toForm={(c) => ({
              name: c.name,
              phone: c.contact_masked ? "" : (c.phone ?? ""),
              email: c.contact_masked ? "" : (c.email ?? ""),
              lang: c.lang,
              classification: c.classification,
              preferences: c.preferences ?? "",
              allergy: c.allergy_notes ?? "",
              consent: c.consent_marketing,
            })}
            extraActions={(c) => [{ label: "Open", icon: Eye, onClick: () => router.push(`/customers/${c.id}`) }]}
          />
        </>
      )}
      {tab === "credit" && (
        <DataTable
          rows={accts.data.map((a) => ({ ...a, limit: num(a.credit_limit), bal: num(a.balance), avail: num(a.available), over: num(a.overdue) }))}
          exportName="credit-accounts"
          emptyTitle="No credit accounts"
          toolbar={
            can(me, "credit.manage") && (
              <button className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground" onClick={() => setOpenAcct(true)}>
                Open account
              </button>
            )
          }
          columns={[
            { key: "account_no", header: "Account" },
            { key: "customer_name", header: "Customer" },
            { key: "company_name", header: "Company", render: (a) => a.company_name ?? "—" },
            { key: "limit", header: "Limit", align: "right", render: (a) => usd(a.limit) },
            { key: "bal", header: "Balance", align: "right", render: (a) => usd(a.bal) },
            { key: "avail", header: "Available", align: "right", render: (a) => usd(a.avail) },
            { key: "over", header: "Overdue", align: "right", render: (a) => <span className={a.over > 0 ? "text-danger" : ""}>{usd(a.over)}</span> },
            { key: "terms_days", header: "Terms", render: (a) => `${a.terms_days} days` },
            { key: "status", header: "Status", render: (a) => <StatusBadge status={a.status} /> },
          ]}
          rowActions={(a) => [
            { label: "Record payment", icon: CircleDollarSign, hidden: () => !can(me, "credit.settle") || num(a.balance) <= 0, onClick: () => setSettleFor(a) },
            a.status === "Active"
              ? {
                  label: "Suspend",
                  icon: Ban,
                  destructive: true,
                  hidden: () => !can(me, "credit.manage"),
                  onClick: () => void act(() => cus.updateAccount(a.id, { status: "Suspended" }), `${a.account_no} suspended`, accts.reload),
                }
              : {
                  label: "Reactivate",
                  icon: Check,
                  hidden: () => !can(me, "credit.manage") || a.status === "Closed",
                  onClick: () => void act(() => cus.updateAccount(a.id, { status: "Active" }), `${a.account_no} reactivated`, accts.reload),
                },
          ]}
        />
      )}
      {tab === "duplicates" && (
        <>
          <Notice tone="warning">These records share a phone number. Merging moves the other record&apos;s orders and points here and retires it. It is audited.</Notice>
          <DataTable
            rows={dupes}
            exportName="duplicates"
            emptyTitle="No possible duplicates"
            columns={[
              { key: "group", header: "Phone" },
              { key: "code", header: "Code" },
              { key: "name", header: "Name" },
              { key: "loyalty_points", header: "Points", align: "right" },
            ]}
            rowActions={(c) => [
              {
                label: "Keep this record and merge the others",
                icon: Merge,
                hidden: () => !manage,
                onClick: () =>
                  confirmAction({
                    title: `Keep ${c.name} (${c.code})?`,
                    effect: `${c.others.map((o) => `${o.name} (${o.code})`).join(", ")} will be merged into it.`,
                    confirmLabel: "Merge",
                    onConfirm: () =>
                      void act(
                        async () => {
                          for (const o of c.others) await cus.merge(c.id, o.id)
                        },
                        "Records merged",
                        list.reload
                      ),
                  }),
              },
            ]}
          />
        </>
      )}
      <RecordDialog
        open={!!settleFor}
        onOpenChange={(o) => !o && setSettleFor(null)}
        title={`Payment on ${settleFor?.account_no ?? ""}`}
        description={settleFor ? `${settleFor.customer_name}: balance ${usd(num(settleFor.balance))}. The oldest charges are settled first.` : undefined}
        fields={[
          { name: "amount", label: "Amount (USD)", type: "number", min: 0.01, required: true, half: true },
          { name: "method", label: "Method", type: "select", options: ["CASH_USD", "BANK_TRANSFER", "KHQR", "CARD"], required: true, half: true },
          { name: "ref", label: "Reference" },
        ]}
        initial={{ method: "BANK_TRANSFER" }}
        onSubmit={(v) =>
          save(() => cus.settle(settleFor!.id, { amount: String(v.amount), method: String(v.method), reference: String(v.ref ?? "") || undefined })).then(() => {
            toast.success("Payment recorded")
            accts.reload()
          })
        }
      />
      <RecordDialog
        open={openAcct}
        onOpenChange={setOpenAcct}
        title="Open credit account"
        description="Charges are due after the payment terms. Over the limit or when overdue, a manager must approve each charge."
        fields={[
          { name: "customer", label: "Customer", type: "select", options: rows.map((c) => `${c.name} (${c.code})`), required: true },
          { name: "company", label: "Company name", half: true },
          { name: "contact", label: "Billing contact", half: true },
          { name: "limit", label: "Credit limit (USD)", type: "number", min: 0, required: true, half: true },
          { name: "terms", label: "Payment terms (days)", type: "number", min: 0, half: true, hint: "Empty = default from settings" },
          { name: "notes", label: "Notes" },
        ]}
        onSubmit={(v) => {
          const c = rows.find((x) => `${x.name} (${x.code})` === v.customer)!
          return save(() =>
            cus.openAccount({
              customer_id: c.id,
              company_name: String(v.company ?? "") || undefined,
              billing_contact: String(v.contact ?? "") || undefined,
              credit_limit: String(v.limit),
              terms_days: v.terms ? Number(v.terms) : undefined,
              notes: String(v.notes ?? "") || undefined,
            })
          ).then(accts.reload)
        }}
      />
    </Page>
  )
}
