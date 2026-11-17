"use client"

import * as React from "react"
import { Check, MapPin, MonitorPlay, Pause, Play, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { CrudTable, newId } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  LinkButton,
  MoneyText,
  Notice,
  Page,
  PageHeader,
  PageTabs,
  Panel,
  SimpleSelect,
  Stat,
  StatusBadge,
  opts,
  useTab,
} from "@/components/rms/kit"
import { calcBill, kitchenStatus, paymentStatus, usd } from "@/lib/rms/billing"
import { minLabel, rms, useClock, useRms } from "@/lib/rms/store"
import type { DeliveryStatus, Order } from "@/lib/rms/types"

const riders = ["Kosal", "Mengly", "Sambath"]
const columns: DeliveryStatus[] = [
  "Pending Assignment",
  "Assigned",
  "Out for Delivery",
  "Delivered",
]

function DeliveryCard({ o }: { o: Order }) {
  const at = useClock()
  const d = o.delivery!
  const [rider, setRider] = React.useState(d.rider ?? "")
  return (
    <li className="rounded-lg border bg-card p-3 text-sm">
      <div className="flex items-center justify-between">
        <span className="font-semibold">{o.no}</span>
        <span className="tabular text-xs text-muted-foreground">
          {minLabel(at - o.createdAt)}
        </span>
      </div>
      <p className="mt-1 flex items-start gap-1 text-xs text-muted-foreground">
        <MapPin className="mt-0.5 size-3 shrink-0" />
        {d.address} · {d.zone}
      </p>
      {d.platform && (
        <p className="text-xs text-muted-foreground">
          {d.platform} · {d.platformRef}
        </p>
      )}
      <div className="mt-1.5 flex items-center justify-between">
        <StatusBadge
          status={kitchenStatus(o)}
          tone={kitchenStatus(o) === "Ready" ? "success" : "info"}
        />
        <MoneyText value={calcBill(o).total} className="font-medium" />
      </div>
      {d.status === "Pending Assignment" && (
        <div className="mt-2 flex gap-1.5">
          <SimpleSelect
            aria-label="Rider"
            value={rider}
            onChange={setRider}
            options={opts(...riders)}
            placeholder="Rider…"
          />
          <Button
            disabled={!rider}
            onClick={() => rms.setDelivery(o.id, "Assigned", rider)}
          >
            Assign
          </Button>
        </div>
      )}
      {d.status === "Assigned" && (
        <Button
          className="mt-2 w-full"
          variant="outline"
          onClick={() => rms.setDelivery(o.id, "Out for Delivery")}
        >
          Out for delivery · {d.rider}
        </Button>
      )}
      {d.status === "Out for Delivery" && (
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          <Button
            onClick={() => {
              rms.setDelivery(o.id, "Delivered")
              rms.serveAll(o.id)
            }}
          >
            Delivered
          </Button>
          <Button
            variant="destructive"
            onClick={() =>
              confirmAction({
                title: "Delivery failed",
                effect:
                  "The order returns to the branch. Refund and wastage follow your policy.",
                reasons: ["Customer unreachable", "Wrong address", "Refused"],
                destructive: true,
                onConfirm: () => rms.setDelivery(o.id, "Failed"),
              })
            }
          >
            Failed
          </Button>
        </div>
      )}
    </li>
  )
}

export default function DeliveryPage() {
  const { orders, onlinePaused } = useRms()
  const at = useClock()
  const [tab, setTab] = useTab("takeaway")
  const takeaway = orders.filter(
    (o) =>
      (o.type === "TAKEAWAY" &&
        o.status === "Open" &&
        o.channel !== "ONLINE") ||
      (o.type === "TAKEAWAY" &&
        o.onlineState === "Accepted" &&
        o.status === "Open")
  )
  const deliveries = orders.filter(
    (o) => o.type === "DELIVERY" && o.status !== "Cancelled"
  )
  const online = orders.filter(
    (o) => o.channel === "ONLINE" && o.onlineState === "Received"
  )
  const platforms = orders
    .filter((o) => o.delivery?.platform)
    .map((o) => ({
      id: o.id,
      order: o.no,
      platform: o.delivery!.platform!,
      ref: o.delivery!.platformRef!,
      gross: calcBill(o).total,
      commission: o.delivery!.commission ?? 0,
      status: "Pending",
    }))
  return (
    <Page>
      <PageHeader
        title="Takeaway & delivery"
        description="Pickup queue, rider assignment, online orders and platform settlements."
        actions={
          <>
            <LinkButton href="/ready-board" variant="outline">
              <MonitorPlay />
              Ready board
            </LinkButton>
            <Button
              variant={onlinePaused ? "default" : "outline"}
              onClick={() => {
                rms.toggleOnlinePaused()
                toast.success(
                  onlinePaused
                    ? "Online ordering resumed"
                    : "Online ordering paused"
                )
              }}
            >
              {onlinePaused ? <Play /> : <Pause />}
              {onlinePaused ? "Resume online orders" : "Pause online orders"}
            </Button>
          </>
        }
      />
      {onlinePaused && (
        <Notice tone="warning">
          Online ordering is paused for this branch. Customers can browse but
          can&apos;t order.
        </Notice>
      )}
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "takeaway", label: "Takeaway", count: takeaway.length },
          {
            value: "delivery",
            label: "Delivery board",
            count: deliveries.filter((d) => d.delivery?.status !== "Delivered")
              .length,
          },
          { value: "online", label: "Online orders", count: online.length },
          { value: "platforms", label: "Platforms" },
          { value: "zones", label: "Delivery zones" },
          { value: "performance", label: "Performance" },
        ]}
      />
      {tab === "takeaway" && (
        <DataTable
          rows={takeaway}
          exportName="takeaway"
          emptyTitle="No takeaway orders waiting"
          columns={[
            { key: "no", header: "Order" },
            { key: "pickup", header: "Pickup name" },
            {
              key: "age",
              header: "Age",
              align: "right",
              value: (o) => at - o.createdAt,
              render: (o) => minLabel(at - o.createdAt),
            },
            {
              key: "kitchen",
              header: "Kitchen",
              value: kitchenStatus,
              render: (o) => (
                <StatusBadge
                  status={kitchenStatus(o)}
                  tone={kitchenStatus(o) === "Ready" ? "success" : "info"}
                />
              ),
            },
            {
              key: "payment",
              header: "Payment",
              value: paymentStatus,
              render: (o) => <StatusBadge status={paymentStatus(o)} />,
            },
            {
              key: "total",
              header: "Total",
              align: "right",
              value: (o) => calcBill(o).total,
              render: (o) => usd(calcBill(o).total),
            },
          ]}
          rowActions={(o) => [
            {
              label: "Mark collected",
              icon: Check,
              hidden: () => !o.lines.some((l) => l.status === "Ready"),
              onClick: () => {
                rms.serveAll(o.id)
                toast.success(`${o.no} collected`)
              },
            },
          ]}
        />
      )}
      {tab === "delivery" && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {columns.map((c) => {
            const list = deliveries.filter((o) => o.delivery!.status === c)
            return (
              <section key={c} className="rounded-xl bg-muted/50 p-2">
                <h2 className="flex justify-between p-1 text-sm font-medium">
                  {c}
                  <span className="tabular text-muted-foreground">
                    {list.length}
                  </span>
                </h2>
                <ul className="grid gap-2">
                  {list.map((o) => (
                    <DeliveryCard key={o.id} o={o} />
                  ))}
                  {list.length === 0 && (
                    <li className="p-4 text-center text-xs text-muted-foreground">
                      None
                    </li>
                  )}
                </ul>
              </section>
            )
          })}
        </div>
      )}
      {tab === "online" &&
        (online.length === 0 ? (
          <Notice tone="info">
            No online orders are waiting. Customers order from{" "}
            <a className="underline" href="/online">
              the public menu
            </a>
            .
          </Notice>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {online.map((o) => (
              <Panel
                key={o.id}
                title={`${o.no} · ${o.pickup}`}
                description={`${o.type === "TAKEAWAY" ? "Pickup" : "Delivery"} · ${usd(calcBill(o).total)}`}
              >
                <ul className="text-sm">
                  {o.lines.map((l) => (
                    <li key={l.id}>
                      {l.qty} × {l.name}
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex gap-2">
                  <Button
                    onClick={() => {
                      rms.acceptOnline(o.id)
                      toast.success("Accepted and sent to kitchen")
                    }}
                  >
                    <Check />
                    Accept
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() =>
                      confirmAction({
                        title: `Reject ${o.no}?`,
                        effect:
                          "The customer is notified and any online payment is refunded.",
                        reasons: [
                          "Too busy",
                          "Item unavailable",
                          "Outside delivery area",
                        ],
                        destructive: true,
                        confirmLabel: "Reject order",
                        onConfirm: (r) => rms.rejectOnline(o.id, r),
                      })
                    }
                  >
                    <X />
                    Reject
                  </Button>
                </div>
              </Panel>
            ))}
          </div>
        ))}
      {tab === "platforms" && (
        <>
          <section className="grid gap-3 sm:grid-cols-3">
            <Stat label="Platform orders" value={platforms.length} />
            <Stat
              label="Commissions"
              value={usd(platforms.reduce((s, p) => s + p.commission, 0))}
              hint="An expense-type cost, not a sales discount"
            />
            <Stat label="Settlement differences" value={0} />
          </section>
          <DataTable
            rows={platforms}
            exportName="platform-orders"
            columns={[
              { key: "order", header: "Order" },
              { key: "platform", header: "Platform" },
              { key: "ref", header: "Platform ref" },
              {
                key: "gross",
                header: "Gross",
                align: "right",
                render: (r) => usd(r.gross),
              },
              {
                key: "commission",
                header: "Commission",
                align: "right",
                render: (r) => usd(r.commission),
              },
              {
                key: "status",
                header: "Settlement",
                render: (r) => <StatusBadge status={r.status} />,
              },
            ]}
          />
        </>
      )}
      {tab === "zones" && (
        <CrudTable
          noun="Delivery zone"
          seed={[
            {
              id: "z1",
              name: "Zone A",
              area: "Daun Penh, 7 Makara",
              fee: 1,
              freeOver: 25,
              status: "Active",
            },
            {
              id: "z2",
              name: "Zone B",
              area: "BKK1, Toul Tompoung",
              fee: 1.5,
              freeOver: 30,
              status: "Active",
            },
            {
              id: "z3",
              name: "Zone C",
              area: "Sen Sok, Russey Keo",
              fee: 2.5,
              freeOver: 40,
              status: "Active",
            },
          ]}
          columns={[
            { key: "name", header: "Zone" },
            { key: "area", header: "Coverage" },
            {
              key: "fee",
              header: "Fee",
              align: "right",
              render: (r) => usd(r.fee),
            },
            {
              key: "freeOver",
              header: "Free over",
              align: "right",
              render: (r) => usd(r.freeOver),
            },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.status} />,
            },
          ]}
          fields={[
            { name: "name", label: "Zone name", required: true, half: true },
            {
              name: "fee",
              label: "Fee (USD)",
              type: "number",
              required: true,
              min: 0,
              half: true,
            },
            { name: "area", label: "Coverage", required: true },
            {
              name: "freeOver",
              label: "Free delivery over (USD)",
              type: "number",
              min: 0,
            },
          ]}
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            area: String(v.area),
            fee: Number(v.fee),
            freeOver: Number(v.freeOver || 0),
            status: e?.status ?? "Active",
          })}
        />
      )}
      {tab === "performance" && (
        <DataTable
          rows={[
            {
              id: "1",
              rider: "Kosal",
              orders: 38,
              prep: 14.2,
              delivery: 22.5,
              late: 3,
              failed: 1,
            },
            {
              id: "2",
              rider: "Mengly",
              orders: 31,
              prep: 13.8,
              delivery: 25.1,
              late: 5,
              failed: 0,
            },
            {
              id: "3",
              rider: "Sambath",
              orders: 22,
              prep: 15.1,
              delivery: 19.4,
              late: 1,
              failed: 0,
            },
          ]}
          exportName="delivery-performance"
          columns={[
            { key: "rider", header: "Rider" },
            { key: "orders", header: "Orders", align: "right" },
            { key: "prep", header: "Avg prep (min)", align: "right" },
            { key: "delivery", header: "Avg delivery (min)", align: "right" },
            { key: "late", header: "Late", align: "right" },
            { key: "failed", header: "Failed", align: "right" },
          ]}
        />
      )}
    </Page>
  )
}
