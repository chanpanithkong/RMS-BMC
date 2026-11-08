"use client"

import { useRouter } from "next/navigation"
import { Plus } from "lucide-react"
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
import { ingredients, recipes } from "@/lib/rms/back-office"
import { useRms } from "@/lib/rms/store"

const target = 35
const pct = (r: (typeof recipes)[number]) =>
  Math.round((r.cost / r.price) * 1000) / 10

export default function RecipesPage() {
  const router = useRouter()
  const { menu } = useRms()
  const [tab, setTab] = useTab("recipes")
  const mapped = new Set(
    recipes.filter((r) => r.status === "Active").map((r) => r.item)
  )
  const unmapped = menu
    .filter((m) => !mapped.has(m.name))
    .map((m) => ({
      id: m.id,
      item: m.name,
      code: m.code,
      sold: (m.name.length * 3) % 23,
      status: "Unmapped",
    }))
  const variance = ingredients.slice(0, 8).map((i, n) => {
    const theo = 10 + n * 3.5
    const actual = theo * (1 + ((n % 3) - 0.6) * 0.04)
    const waste = n % 2 ? 0.4 : 0.1
    const v = actual - theo - waste
    return {
      id: i.id,
      name: i.name,
      unit: i.unit,
      theo: +theo.toFixed(2),
      actual: +actual.toFixed(2),
      waste,
      variance: +v.toFixed(2),
      value: +(v * i.cost).toFixed(2),
    }
  })
  return (
    <Page>
      <PageHeader
        title="Recipes & food cost"
        description="Published recipe versions can't be edited. Create a new version to change quantities."
        actions={
          <LinkButton href="/recipes/new">
            <Plus />
            New recipe
          </LinkButton>
        }
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "recipes", label: "Recipes", count: recipes.length },
          { value: "cost", label: "Cost analysis" },
          {
            value: "unmapped",
            label: "Unmapped items",
            count: unmapped.length,
          },
          { value: "variance", label: "Theoretical vs actual" },
        ]}
      />
      {tab === "recipes" && (
        <DataTable
          rows={recipes}
          exportName="recipes"
          onRowClick={(r) => router.push(`/recipes/${r.id}`)}
          filters={[
            {
              key: "status",
              label: "Status",
              options: ["Draft", "Active", "Retired"],
            },
          ]}
          columns={[
            {
              key: "item",
              header: "Menu item",
              render: (r) => <span className="font-medium">{r.item}</span>,
            },
            { key: "variant", header: "Variant" },
            { key: "version", header: "Version" },
            {
              key: "cost",
              header: "Cost / portion",
              align: "right",
              render: (r) => usd(r.cost),
            },
            {
              key: "pct",
              header: "Food cost",
              align: "right",
              value: pct,
              render: (r) => `${pct(r)}%`,
            },
            { key: "updated", header: "Updated" },
            { key: "by", header: "By" },
            {
              key: "status",
              header: "Status",
              render: (r) => (
                <StatusBadge
                  status={r.status === "Active" ? "Published" : r.status}
                />
              ),
            },
          ]}
        />
      )}
      {tab === "cost" && (
        <>
          <Notice tone="info">
            Items over the {target}% target are flagged. Costs use current
            weighted average ingredient costs, calculated 08/11/2026.
          </Notice>
          <DataTable
            rows={recipes}
            exportName="cost-analysis"
            columns={[
              { key: "item", header: "Item" },
              {
                key: "price",
                header: "Price excl. tax",
                align: "right",
                render: (r) => usd(r.price),
              },
              {
                key: "cost",
                header: "Recipe cost",
                align: "right",
                render: (r) => usd(r.cost),
              },
              {
                key: "pct",
                header: "Food cost %",
                align: "right",
                value: pct,
                render: (r) => `${pct(r)}%`,
              },
              {
                key: "margin",
                header: "Gross margin",
                align: "right",
                value: (r) => r.price - r.cost,
                render: (r) => usd(r.price - r.cost),
              },
              {
                key: "flag",
                header: "Target",
                value: (r) => (pct(r) > target ? "Over target" : "On target"),
                render: (r) => (
                  <StatusBadge
                    status={pct(r) > target ? "Over target" : "On target"}
                    tone={pct(r) > target ? "danger" : "success"}
                  />
                ),
              },
            ]}
          />
        </>
      )}
      {tab === "unmapped" && (
        <>
          <Notice tone="warning">
            These items sell without an active recipe, so no ingredients are
            consumed for them.
          </Notice>
          <DataTable
            rows={unmapped}
            exportName="unmapped-items"
            onRowClick={() => router.push("/recipes/new")}
            columns={[
              { key: "code", header: "Code" },
              { key: "item", header: "Item" },
              { key: "sold", header: "Sold this week", align: "right" },
              {
                key: "status",
                header: "Status",
                render: (r) => <StatusBadge status={r.status} />,
              },
            ]}
          />
        </>
      )}
      {tab === "variance" && (
        <DataTable
          rows={variance}
          exportName="food-variance"
          columns={[
            { key: "name", header: "Ingredient" },
            {
              key: "theo",
              header: "Theoretical",
              align: "right",
              render: (r) => `${r.theo} ${r.unit}`,
            },
            {
              key: "actual",
              header: "Actual usage",
              align: "right",
              render: (r) => `${r.actual} ${r.unit}`,
            },
            {
              key: "waste",
              header: "Wastage",
              align: "right",
              render: (r) => `${r.waste} ${r.unit}`,
            },
            {
              key: "variance",
              header: "Unexplained",
              align: "right",
              render: (r) => `${r.variance} ${r.unit}`,
            },
            {
              key: "value",
              header: "Value",
              align: "right",
              render: (r) => usd(r.value),
            },
          ]}
        />
      )}
    </Page>
  )
}
