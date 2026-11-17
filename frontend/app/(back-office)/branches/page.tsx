"use client"

import { BarChart3 } from "lucide-react"
import { CrudTable, newId } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import {
  LinkButton,
  Notice,
  Page,
  PageHeader,
  PageTabs,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"

export default function BranchesPage() {
  const [tab, setTab] = useTab("branches")
  return (
    <Page>
      <PageHeader
        title="Branches"
        description="Optional multi-branch management. Operational records always belong to one branch."
        actions={
          <LinkButton href="/?tab=branches" variant="outline">
            <BarChart3 />
            Branch comparison
          </LinkButton>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "branches", label: "Branches" },
          { value: "prices", label: "Branch prices" },
          { value: "transfers", label: "Stock transfers" },
          { value: "overrides", label: "Setting overrides" },
        ]}
      />
      {tab === "branches" && (
        <CrudTable
          noun="Branch"
          seed={[
            {
              id: "b1",
              code: "RVS",
              name: "Riverside",
              km: "មាត់ទន្លេ",
              address: "Sisowath Quay, Phnom Penh",
              phone: "023 100 100",
              hours: "07:00–23:00",
              tz: "Asia/Phnom_Penh",
              status: "Active",
            },
            {
              id: "b2",
              code: "BK1",
              name: "BKK1",
              km: "បឹងកេងកង១",
              address: "St 278, Phnom Penh",
              phone: "023 100 200",
              hours: "07:00–22:00",
              tz: "Asia/Phnom_Penh",
              status: "Active",
            },
            {
              id: "b3",
              code: "SRP",
              name: "Siem Reap",
              km: "សៀមរាប",
              address: "Pub Street area, Siem Reap",
              phone: "063 100 300",
              hours: "10:00–23:00",
              tz: "Asia/Phnom_Penh",
              status: "Active",
            },
          ]}
          columns={[
            { key: "code", header: "Code" },
            {
              key: "name",
              header: "Name",
              render: (b) => <span className="font-medium">{b.name}</span>,
            },
            { key: "km", header: "Khmer" },
            { key: "address", header: "Address" },
            { key: "phone", header: "Phone" },
            { key: "hours", header: "Hours" },
            {
              key: "status",
              header: "Status",
              render: (b) => <StatusBadge status={b.status} />,
            },
          ]}
          fields={[
            { name: "code", label: "Code", required: true, half: true },
            {
              name: "phone",
              label: "Phone",
              type: "tel",
              required: true,
              half: true,
            },
            { name: "name", label: "English name", required: true, half: true },
            { name: "km", label: "Khmer name", required: true, half: true },
            { name: "address", label: "Address", required: true },
            {
              name: "hours",
              label: "Opening hours",
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
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            code: String(v.code),
            name: String(v.name),
            km: String(v.km),
            address: String(v.address),
            phone: String(v.phone),
            hours: String(v.hours),
            tz: String(v.tz),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "prices" && (
        <DataTable
          rows={[
            {
              id: "1",
              item: "Fish Amok",
              base: 8.5,
              riverside: 8.5,
              bkk1: 9,
              siem: 10,
            },
            {
              id: "2",
              item: "Beef Lok Lak",
              base: 9.5,
              riverside: 9.5,
              bkk1: 9.5,
              siem: 11,
            },
            {
              id: "3",
              item: "Iced Coffee",
              base: 2,
              riverside: 2,
              bkk1: 2.25,
              siem: 2.5,
            },
          ]}
          exportName="branch-prices"
          columns={[
            { key: "item", header: "Item" },
            {
              key: "base",
              header: "Restaurant",
              align: "right",
              render: (r) => usd(r.base),
            },
            {
              key: "riverside",
              header: "Riverside",
              align: "right",
              render: (r) => usd(r.riverside),
            },
            {
              key: "bkk1",
              header: "BKK1",
              align: "right",
              render: (r) => usd(r.bkk1),
            },
            {
              key: "siem",
              header: "Siem Reap",
              align: "right",
              render: (r) => usd(r.siem),
            },
          ]}
        />
      )}
      {tab === "transfers" && (
        <>
          <Notice tone="info">
            Inter-branch transfers go through dispatch, in transit and receipt.
            Differences need approval.
          </Notice>
          <DataTable
            rows={[
              {
                id: "TRF-053",
                from: "Riverside",
                to: "BKK1",
                items: "Coconut cream 12 L",
                dispatched: "12 L",
                received: "—",
                status: "In Transit",
              },
              {
                id: "TRF-052",
                from: "BKK1",
                to: "Riverside",
                items: "Jasmine rice",
                dispatched: "25 kg",
                received: "24.5 kg",
                status: "Difference",
              },
            ]}
            exportName="inter-branch-transfers"
            columns={[
              { key: "id", header: "Transfer" },
              { key: "from", header: "From" },
              { key: "to", header: "To" },
              { key: "items", header: "Items" },
              { key: "dispatched", header: "Dispatched", align: "right" },
              { key: "received", header: "Received", align: "right" },
              {
                key: "status",
                header: "Status",
                render: (r) => <StatusBadge status={r.status} />,
              },
            ]}
          />
        </>
      )}
      {tab === "overrides" && (
        <DataTable
          rows={[
            {
              id: "1",
              branch: "BKK1",
              setting: "Receipt header",
              value: "RMS Demo · BKK1",
              by: "Sopheak Nou",
            },
            {
              id: "2",
              branch: "Siem Reap",
              setting: "Service charge",
              value: "Illustrative 8%",
              by: "Dara Pich",
            },
          ]}
          exportName="branch-overrides"
          columns={[
            { key: "branch", header: "Branch" },
            { key: "setting", header: "Setting" },
            { key: "value", header: "Override" },
            { key: "by", header: "Changed by" },
          ]}
        />
      )}
    </Page>
  )
}
