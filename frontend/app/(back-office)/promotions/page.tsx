"use client"

import { Ban } from "lucide-react"
import { CrudTable, newId } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import {
  Page,
  PageHeader,
  PageTabs,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { usd } from "@/lib/rms/billing"

export default function PromotionsPage() {
  const [tab, setTab] = useTab("promotions")
  return (
    <Page>
      <PageHeader
        title="Discounts & promotions"
        description="Promotions apply automatically or by code. Manual discounts are checked against each role's limit."
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "promotions", label: "Promotions" },
          { value: "codes", label: "Codes" },
          { value: "reasons", label: "Discount reasons" },
          { value: "limits", label: "Limits by role" },
          { value: "loyalty", label: "Loyalty" },
          { value: "history", label: "Usage history" },
        ]}
      />
      {tab === "promotions" && (
        <CrudTable
          noun="Promotion"
          seed={[
            {
              id: "p1",
              name: "Happy Hour Beer",
              type: "Fixed price",
              scope: "Draft Beer",
              value: "$1.50",
              window: "Mon–Fri 15:00–18:00",
              branches: "Riverside",
              combinable: "No",
              status: "Active",
            },
            {
              id: "p2",
              name: "Lunch Combo",
              type: "Combo price",
              scope: "Lunch Set",
              value: "$6.50",
              window: "Daily 11:00–14:00",
              branches: "All",
              combinable: "No",
              status: "Active",
            },
            {
              id: "p3",
              name: "Buy 2 Get 1 Latte",
              type: "Buy-X-get-Y",
              scope: "Caffè Latte",
              value: "2 + 1",
              window: "Weekends",
              branches: "BKK1",
              combinable: "Yes",
              status: "Scheduled",
            },
            {
              id: "p4",
              name: "VIP 10%",
              type: "Percentage",
              scope: "Order · VIP customers",
              value: "10%",
              window: "All day",
              branches: "All",
              combinable: "No",
              status: "Active",
            },
            {
              id: "p5",
              name: "Pchum Ben Special",
              type: "Amount",
              scope: "Order over $30",
              value: "$5.00",
              window: "04/10–07/10/2026",
              branches: "All",
              combinable: "No",
              status: "Expired",
            },
          ]}
          filters={[
            {
              key: "status",
              label: "Status",
              options: ["Active", "Scheduled", "Expired", "Inactive"],
            },
            { key: "type", label: "Type" },
          ]}
          columns={[
            { key: "name", header: "Promotion" },
            { key: "type", header: "Type" },
            { key: "scope", header: "Scope" },
            { key: "value", header: "Value", align: "right" },
            { key: "window", header: "Validity" },
            { key: "branches", header: "Branches" },
            { key: "combinable", header: "Combinable" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            { name: "name", label: "Name", required: true },
            {
              name: "type",
              label: "Type",
              type: "select",
              options: [
                "Percentage",
                "Amount",
                "Fixed price",
                "Buy-X-get-Y",
                "Combo price",
              ],
              required: true,
              half: true,
            },
            { name: "value", label: "Value", required: true, half: true },
            {
              name: "scope",
              label: "Scope (items, order, segment)",
              required: true,
            },
            {
              name: "window",
              label: "Validity, days and times",
              required: true,
            },
            {
              name: "branches",
              label: "Branches",
              type: "select",
              options: ["All", "Riverside", "BKK1", "Siem Reap"],
              required: true,
              half: true,
            },
            {
              name: "combinable",
              label: "Combinable",
              type: "select",
              options: ["Yes", "No"],
              required: true,
              half: true,
            },
          ]}
          extraActions={(_, update) => [
            {
              label: "Deactivate",
              icon: Ban,
              destructive: true,
              onClick: () => update({ status: "Inactive" }),
            },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            type: String(v.type),
            scope: String(v.scope),
            value: String(v.value),
            window: String(v.window),
            branches: String(v.branches),
            combinable: String(v.combinable),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "codes" && (
        <CrudTable
          noun="Promotion code"
          seed={[
            {
              id: "c1",
              code: "WELCOME10",
              promo: "10% first order",
              use: "Single-use per customer",
              limit: 500,
              used: 212,
              expires: "31/12/2026",
              status: "Active",
            },
            {
              id: "c2",
              code: "RIVER5",
              promo: "$5 off over $30",
              use: "Multi-use",
              limit: 100,
              used: 100,
              expires: "30/11/2026",
              status: "Expired",
            },
          ]}
          columns={[
            {
              key: "code",
              header: "Code",
              render: (r) => (
                <span className="font-mono font-medium">{r.code}</span>
              ),
            },
            { key: "promo", header: "Benefit" },
            { key: "use", header: "Usage rule" },
            {
              key: "used",
              header: "Used",
              align: "right",
              render: (r) => `${r.used} / ${r.limit}`,
            },
            { key: "expires", header: "Expires" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            { name: "code", label: "Code", required: true, half: true },
            {
              name: "limit",
              label: "Usage limit",
              type: "number",
              min: 1,
              required: true,
              half: true,
            },
            { name: "promo", label: "Benefit", required: true },
            {
              name: "use",
              label: "Usage rule",
              type: "select",
              options: ["Single-use per customer", "Multi-use"],
              required: true,
              half: true,
            },
            {
              name: "expires",
              label: "Expires (DD/MM/YYYY)",
              required: true,
              half: true,
            },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            code: String(v.code).toUpperCase(),
            promo: String(v.promo),
            use: String(v.use),
            limit: Number(v.limit),
            used: e?.used ?? 0,
            expires: String(v.expires),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "reasons" && (
        <CrudTable
          noun="Discount reason"
          seed={[
            "Regular customer",
            "Service recovery",
            "Staff meal",
            "Complimentary",
            "Promotion not applied",
            "Manager decision",
          ].map((name, i) => ({
            id: `r${i}`,
            name,
            km: "—",
            kind: i === 2 ? "Staff meal" : i === 3 ? "Comp" : "Manual",
            status: "Active",
          }))}
          columns={[
            { key: "name", header: "Reason" },
            { key: "km", header: "Khmer" },
            { key: "kind", header: "Reporting type" },
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
              name: "kind",
              label: "Reporting type",
              type: "select",
              options: ["Manual", "Staff meal", "Comp"],
              required: true,
            },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            km: String(v.km),
            kind: String(v.kind),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "limits" && (
        <CrudTable
          noun="Limit"
          canAdd={false}
          seed={[
            ["Cashier", 10, 5, 25],
            ["Bartender", 10, 5, 25],
            ["Supervisor", 20, 20, 100],
            ["Branch Manager", 30, 50, 300],
            ["General Manager", 50, 200, 1000],
            ["Owner", 100, 9999, 9999],
          ].map(([role, pct, bill, day], i) => ({
            id: String(i),
            role: String(role),
            pct: Number(pct),
            bill: Number(bill),
            day: Number(day),
          }))}
          columns={[
            { key: "role", header: "Role" },
            {
              key: "pct",
              header: "Max %",
              align: "right",
              render: (r) => `${r.pct}%`,
            },
            {
              key: "bill",
              header: "Max per bill",
              align: "right",
              render: (r) => usd(r.bill),
            },
            {
              key: "day",
              header: "Max per day",
              align: "right",
              render: (r) => usd(r.day),
            },
          ]}
          fields={[
            {
              name: "pct",
              label: "Maximum %",
              type: "number",
              min: 0,
              max: 100,
              required: true,
            },
            {
              name: "bill",
              label: "Maximum per bill",
              type: "number",
              min: 0,
              required: true,
              half: true,
            },
            {
              name: "day",
              label: "Maximum per day",
              type: "number",
              min: 0,
              required: true,
              half: true,
            },
          ]}
          description="Changes need approval and are written to the audit log."
          toRow={(v, e) => ({
            ...e!,
            pct: Number(v.pct),
            bill: Number(v.bill),
            day: Number(v.day),
          })}
        />
      )}
      {tab === "loyalty" && (
        <CrudTable
          noun="Loyalty rule"
          seed={[
            {
              id: "l1",
              rule: "Earn",
              detail: "1 point per $1 net spend",
              segment: "All",
              status: "Active",
            },
            {
              id: "l2",
              rule: "Redeem",
              detail: "100 points = $1 discount",
              segment: "All",
              status: "Active",
            },
            {
              id: "l3",
              rule: "Bonus",
              detail: "Double points on birthdays",
              segment: "VIP",
              status: "Inactive",
            },
          ]}
          columns={[
            { key: "rule", header: "Rule" },
            { key: "detail", header: "Detail" },
            { key: "segment", header: "Segment" },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            {
              name: "rule",
              label: "Type",
              type: "select",
              options: ["Earn", "Redeem", "Bonus"],
              required: true,
              half: true,
            },
            {
              name: "segment",
              label: "Segment",
              type: "select",
              options: ["All", "Regular", "VIP", "Corporate"],
              required: true,
              half: true,
            },
            { name: "detail", label: "Detail", required: true },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            rule: String(v.rule),
            detail: String(v.detail),
            segment: String(v.segment),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "history" && (
        <DataTable
          rows={[
            {
              id: "1",
              time: "08/11 12:54",
              bill: "B-5512",
              kind: "Manual 20%",
              reason: "Service recovery",
              value: 4.2,
              user: "Lina Chhay",
              approver: "Dara Pich",
            },
            {
              id: "2",
              time: "08/11 12:11",
              bill: "B-5507",
              kind: "Happy Hour Beer",
              reason: "Promotion",
              value: 2,
              user: "System",
              approver: "—",
            },
            {
              id: "3",
              time: "08/11 11:42",
              bill: "B-5501",
              kind: "VIP 10%",
              reason: "Promotion",
              value: 3.15,
              user: "System",
              approver: "—",
            },
            {
              id: "4",
              time: "07/11 20:18",
              bill: "B-5478",
              kind: "Staff meal",
              reason: "Staff meal",
              value: 5,
              user: "Vuthy Sam",
              approver: "Sopheak Nou",
            },
          ]}
          exportName="discount-history"
          columns={[
            { key: "time", header: "Time" },
            { key: "bill", header: "Bill" },
            { key: "kind", header: "Discount" },
            { key: "reason", header: "Reason" },
            {
              key: "value",
              header: "Value",
              align: "right",
              render: (r) => usd(r.value),
            },
            { key: "user", header: "Applied by" },
            { key: "approver", header: "Approver" },
          ]}
        />
      )}
    </Page>
  )
}
