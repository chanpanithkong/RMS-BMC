"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { Plus } from "lucide-react"
import { DataTable } from "@/components/rms/data-table"
import { LinkButton, Notice, Page, PageHeader, PageTabs, StatusBadge, useTab } from "@/components/rms/kit"
import * as rcp from "@/lib/api/recipes"
import { num, useApi } from "@/lib/api/use-api"
import { usd } from "@/lib/rms/billing"

export default function RecipesPage() {
  const router = useRouter()
  const [tab, setTab] = useTab("recipes")
  const recipes = useApi(rcp.listRecipeRows, [], [])
  const unmapped = useApi(
    async () =>
      (await rcp.unmapped()).map((u) => ({
        id: u.variant_id,
        item: u.item,
        variant: u.variant === "Regular" ? "—" : u.variant,
        sold: num(u.quantity_sold),
        recipeId: u.recipe_id,
        status: u.recipe_id ? "Draft only" : "No recipe",
      })),
    [],
    []
  )
  const costed = recipes.data.filter((r) => r.price !== null)
  const target = costed.find((r) => r.target !== null)?.target ?? null

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
          { value: "recipes", label: "Recipes", count: recipes.data.length },
          { value: "cost", label: "Cost analysis" },
          { value: "unmapped", label: "Unmapped items", count: unmapped.data.length },
          { value: "variance", label: "Theoretical vs actual" },
        ]}
      />
      {tab === "recipes" && (
        <DataTable
          rows={recipes.data}
          exportName="recipes"
          emptyTitle={recipes.loading ? "Loading…" : "No recipes yet"}
          onRowClick={(r) => router.push(`/recipes/${r.id}`)}
          filters={[{ key: "status", label: "Status", options: ["Draft", "Published", "Scheduled", "Retired"] }]}
          columns={[
            { key: "name", header: "Recipe", render: (r) => <span className="font-medium">{r.name}</span> },
            { key: "version", header: "Version" },
            {
              key: "cost",
              header: "Cost / portion",
              align: "right",
              render: (r) => (r.status === "Draft" && !r.cost ? "—" : usd(r.cost)),
            },
            {
              key: "pct",
              header: "Food cost",
              align: "right",
              value: (r) => r.pct ?? -1,
              render: (r) => (r.pct === null ? "—" : `${r.pct}%`),
            },
            { key: "updated", header: "Published" },
            { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
          ]}
        />
      )}
      {tab === "cost" && (
        <>
          <Notice tone="info">
            {target !== null ? `Items over the ${target}% target are flagged. ` : ""}Costs use current weighted average
            ingredient costs and the price excluding tax, calculated by the server just now.
          </Notice>
          <DataTable
            rows={costed}
            exportName="cost-analysis"
            emptyTitle="No published recipes with a selling price"
            columns={[
              { key: "name", header: "Item" },
              { key: "price", header: "Price excl. tax", align: "right", render: (r) => usd(r.price ?? 0) },
              { key: "cost", header: "Recipe cost", align: "right", render: (r) => usd(r.cost) },
              { key: "pct", header: "Food cost %", align: "right", render: (r) => `${r.pct}%` },
              { key: "margin", header: "Gross margin", align: "right", render: (r) => usd(r.margin ?? 0) },
              {
                key: "flag",
                header: "Target",
                value: (r) => (r.incomplete ? "Missing costs" : r.above ? "Over target" : "On target"),
                render: (r) => (
                  <StatusBadge
                    status={r.incomplete ? "Missing costs" : r.above ? "Over target" : "On target"}
                    tone={r.incomplete ? "warning" : r.above ? "danger" : "success"}
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
            These items sold in the last 30 days without a recipe in effect, so no ingredients were consumed for them.
          </Notice>
          <DataTable
            rows={unmapped.data}
            exportName="unmapped-items"
            emptyTitle="Every item sold has a recipe"
            onRowClick={(r) => router.push(r.recipeId ? `/recipes/${r.recipeId}` : `/recipes/new?variant=${r.id}`)}
            columns={[
              { key: "item", header: "Item" },
              { key: "variant", header: "Variant" },
              { key: "sold", header: "Sold (30 days)", align: "right" },
              { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
            ]}
          />
        </>
      )}
      {tab === "variance" && (
        <Notice tone="info">
          Theoretical against actual usage is in the report{" "}
          <Link className="underline" href="/reports/RPT-16">
            Ingredient consumption and variance
          </Link>
          .
        </Notice>
      )}
    </Page>
  )
}
