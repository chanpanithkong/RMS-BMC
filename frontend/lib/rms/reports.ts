// Report catalogue from SRS §11.3 with illustrative figures for the viewer.
import {
  expenses,
  ingredients,
  purchaseOrders,
  recipes,
  suppliers,
} from "./back-office"
import { categories, menuItems } from "./seed"
import type { Role } from "./types"

export type Fmt = "text" | "usd" | "num" | "pct"
export interface RCol {
  key: string
  header: string
  fmt: Fmt
}
export interface RData {
  kpis: [string, string][]
  columns: RCol[]
  rows: Record<string, string | number>[]
  chart?: {
    x: string
    y: string
    label: string
    type?: "bar" | "line"
    money?: boolean
  }
}
export interface ReportDef {
  id: string
  name: string
  purpose: string
  group: string
  roles: Role[]
  filters: string[]
  phase: number
  build: (k: number) => RData
}

const r2 = (n: number) => Math.round(n * 100) / 100
const usdK = (n: number) =>
  `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const t = (key: string, header: string): RCol => ({ key, header, fmt: "text" })
const u = (key: string, header: string): RCol => ({ key, header, fmt: "usd" })
const n = (key: string, header: string): RCol => ({ key, header, fmt: "num" })
const p = (key: string, header: string): RCol => ({ key, header, fmt: "pct" })
const wave = (i: number, base: number) =>
  base * (1 + 0.28 * Math.sin(i * 1.7) + (i % 7 >= 4 ? 0.35 : 0))
const FIN: Role[] = ["OWNER", "GM", "BRMGR", "ACCT", "AUDITOR"]
const days = Array.from(
  { length: 8 },
  (_, i) => `${String(i + 1).padStart(2, "0")}/11`
)
const methods = ["Cash USD", "Cash KHR", "KHQR", "Card", "Bank Transfer"]
const staff = ["Sokha Heng", "Dara Mean", "Lina Chhay", "Vuthy Sam"]

const dailyRows = (k: number) =>
  days.map((d, i) => {
    const g = r2(wave(i, 2300) * k)
    const disc = r2(g * 0.04)
    return {
      day: d,
      gross: g,
      discounts: disc,
      refunds: r2(g * 0.006),
      net: r2(g * 0.954),
      orders: Math.round(wave(i, 150)),
    }
  })
const dailyCols = [
  t("day", "Business day"),
  u("gross", "Gross"),
  u("discounts", "Discounts"),
  u("refunds", "Refunds"),
  u("net", "Net sales"),
  n("orders", "Orders"),
]
const sumOf = (rows: Record<string, string | number>[], key: string) =>
  rows.reduce((s, x) => s + Number(x[key]), 0)
const dailyKpis = (
  rows: Record<string, string | number>[]
): [string, string][] => [
  ["Gross", usdK(sumOf(rows, "gross"))],
  ["Discounts", usdK(sumOf(rows, "discounts"))],
  ["Refunds", usdK(sumOf(rows, "refunds"))],
  ["Net sales", usdK(sumOf(rows, "net"))],
  ["Orders", sumOf(rows, "orders").toLocaleString()],
]

function daily(k: number): RData {
  const rows = dailyRows(k)
  return {
    kpis: dailyKpis(rows),
    columns: dailyCols,
    rows,
    chart: {
      x: "day",
      y: "net",
      label: "Net sales",
      type: "line",
      money: true,
    },
  }
}
function single(k: number): RData {
  const rows = [
    ["Gross sales", 2318.4],
    ["Discounts", -98.2],
    ["Refunds", -12.4],
    ["Net sales", 2207.8],
    ["Service charges", 102.4],
    ["Taxes", 231],
    ["Delivery fees", 18.5],
    ["Total billed", 2559.7],
    ...methods.map((m, i) => [
      `Collected: ${m}`,
      [742.5, 312.3, 684.2, 196, 42][i],
    ]),
  ].map(([measure, value]) => ({
    measure,
    value: r2(Number(value) * k),
  })) as Record<string, string | number>[]
  return {
    kpis: [
      ["Net sales", usdK(2207.8 * k)],
      ["Orders", String(Math.round(151 * k))],
      ["AOV", usdK(14.62)],
      ["Open orders", "6"],
      ["Cash variances", usdK(-7)],
    ],
    columns: [t("measure", "Measure"), u("value", "Amount")],
    rows,
  }
}
const itemRows = (k: number) =>
  menuItems.slice(0, 16).map((m, i) => {
    const qty = Math.round(wave(i, 22) * k)
    const gross = r2(qty * m.price)
    return {
      item: m.name,
      qty,
      gross,
      discounts: r2(gross * 0.04),
      net: r2(gross * 0.96),
      avg: m.price,
      rank: i + 1,
    }
  })

export const reports: ReportDef[] = [
  {
    id: "RPT-01",
    name: "Daily sales report",
    purpose: "End-of-day trading summary",
    group: "Sales",
    roles: FIN,
    filters: ["Business day", "Branch"],
    phase: 1,
    build: single,
  },
  {
    id: "RPT-02",
    name: "Monthly sales report",
    purpose: "Month trend",
    group: "Sales",
    roles: FIN,
    filters: ["Month", "Branch"],
    phase: 1,
    build: daily,
  },
  {
    id: "RPT-03",
    name: "Sales by menu category",
    purpose: "Category mix",
    group: "Sales",
    roles: ["OWNER", "GM", "BRMGR", "ACCT"],
    filters: ["Period", "Time", "Branch", "Order type"],
    phase: 1,
    build: (k) => {
      const rows = categories.map((c, i) => {
        const g = r2(wave(i, 640) * k)
        return {
          category: c.name,
          qty: Math.round(g / 6),
          gross: g,
          discounts: r2(g * 0.04),
          net: r2(g * 0.96),
          share: r2(100 / 8 + Math.sin(i * 2) * 5),
        }
      })
      return {
        kpis: [
          ["Net sales", usdK(sumOf(rows, "net"))],
          ["Categories", "8"],
        ],
        columns: [
          t("category", "Category"),
          n("qty", "Quantity"),
          u("gross", "Gross"),
          u("discounts", "Discounts"),
          u("net", "Net sales"),
          p("share", "Share"),
        ],
        rows,
        chart: { x: "category", y: "net", label: "Net sales", money: true },
      }
    },
  },
  {
    id: "RPT-04",
    name: "Sales by menu item",
    purpose: "Item performance",
    group: "Sales",
    roles: ["OWNER", "GM", "BRMGR", "KMGR", "ACCT"],
    filters: ["Period", "Time", "Branch", "Category"],
    phase: 1,
    build: (k) => {
      const rows = itemRows(k)
      return {
        kpis: [
          ["Items sold", sumOf(rows, "qty").toLocaleString()],
          ["Net sales", usdK(sumOf(rows, "net"))],
        ],
        columns: [
          n("rank", "Rank"),
          t("item", "Item"),
          n("qty", "Quantity"),
          u("gross", "Gross"),
          u("discounts", "Discounts"),
          u("net", "Net sales"),
          u("avg", "Avg price"),
        ],
        rows,
        chart: { x: "item", y: "qty", label: "Quantity" },
      }
    },
  },
  {
    id: "RPT-05",
    name: "Sales by employee",
    purpose: "Staff performance",
    group: "Sales",
    roles: ["OWNER", "GM", "BRMGR"],
    filters: ["Period", "Branch", "Employee"],
    phase: 2,
    build: (k) => {
      const rows = staff.map((s, i) => {
        const net = r2(wave(i, 3000) * k)
        return {
          name: s,
          orders: Math.round(net / 14),
          covers: Math.round(net / 7),
          net,
          aov: 14.1 + i * 0.3,
          discounts: r2(net * 0.03),
          voids: i + 1,
        }
      })
      return {
        kpis: [
          ["Net sales", usdK(sumOf(rows, "net"))],
          ["Orders", sumOf(rows, "orders").toLocaleString()],
        ],
        columns: [
          t("name", "Employee"),
          n("orders", "Orders"),
          n("covers", "Covers"),
          u("net", "Net sales"),
          u("aov", "AOV"),
          u("discounts", "Discounts"),
          n("voids", "Voids"),
        ],
        rows,
        chart: { x: "name", y: "net", label: "Net sales", money: true },
      }
    },
  },
  {
    id: "RPT-06",
    name: "Sales by branch",
    purpose: "Branch comparison",
    group: "Sales",
    roles: ["OWNER", "GM"],
    filters: ["Period", "Branches"],
    phase: 3,
    build: (k) => {
      const rows = [
        ["Riverside", 2142, 151],
        ["BKK1", 1688, 124],
        ["Siem Reap", 1294, 88],
      ].map(([b, net, o]) => ({
        branch: b,
        net: r2(Number(net) * k),
        orders: Math.round(Number(o) * k),
        aov: r2(Number(net) / Number(o)),
      })) as Record<string, string | number>[]
      return {
        kpis: [
          ["Consolidated net", usdK(sumOf(rows, "net"))],
          ["Orders", sumOf(rows, "orders").toLocaleString()],
        ],
        columns: [
          t("branch", "Branch"),
          u("net", "Net sales"),
          n("orders", "Orders"),
          u("aov", "AOV"),
        ],
        rows,
        chart: { x: "branch", y: "net", label: "Net sales", money: true },
      }
    },
  },
  {
    id: "RPT-07",
    name: "Sales by payment method",
    purpose: "Collections",
    group: "Sales",
    roles: FIN,
    filters: ["Period", "Branch", "Method"],
    phase: 1,
    build: (k) => {
      const rows = methods.map((m, i) => {
        const pay = r2([742.5, 312.3, 684.2, 196, 42][i] * k)
        return {
          method: m,
          currency: i === 1 ? "KHR" : "USD",
          payments: pay,
          refunds: r2(pay * 0.01),
          net: r2(pay * 0.99),
        }
      })
      return {
        kpis: [
          ["Net collected", usdK(sumOf(rows, "net"))],
          ["Refunds", usdK(sumOf(rows, "refunds"))],
        ],
        columns: [
          t("method", "Method"),
          t("currency", "Currency"),
          u("payments", "Payments"),
          u("refunds", "Refunds"),
          u("net", "Net collected"),
        ],
        rows,
        chart: { x: "method", y: "net", label: "Net collected", money: true },
      }
    },
  },
  {
    id: "RPT-08",
    name: "Order volume and AOV",
    purpose: "Demand",
    group: "Sales",
    roles: ["OWNER", "GM", "BRMGR"],
    filters: ["Period", "Branch", "Order type"],
    phase: 2,
    build: (k) => {
      const rows = ["Dine-in", "Takeaway", "Delivery", "Online"].map(
        (x, i) => ({
          type: x,
          orders: Math.round([96, 34, 18, 15][i] * k),
          aov: [17.2, 9.8, 13.4, 11.9][i],
          cover: [8.6, 9.8, 13.4, 11.9][i],
        })
      )
      return {
        kpis: [
          ["Orders", sumOf(rows, "orders").toLocaleString()],
          ["AOV", "$14.62"],
        ],
        columns: [
          t("type", "Type"),
          n("orders", "Orders"),
          u("aov", "AOV"),
          u("cover", "Spend per cover"),
        ],
        rows,
        chart: { x: "type", y: "orders", label: "Orders" },
      }
    },
  },
  {
    id: "RPT-09",
    name: "Peak-hour analysis",
    purpose: "Staffing and prep planning",
    group: "Operations",
    roles: ["OWNER", "GM", "BRMGR", "KMGR"],
    filters: ["Period", "Branch"],
    phase: 2,
    build: () => {
      const rows = Array.from({ length: 12 }, (_, i) => ({
        hour: `${11 + i}:00`,
        orders: Math.round(6 + 22 * Math.abs(Math.sin((i + 1) / 2))),
        net: r2(90 + 260 * Math.abs(Math.sin((i + 1) / 2))),
        prep: r2(8 + 6 * Math.abs(Math.sin((i + 1) / 2))),
      }))
      return {
        kpis: [
          ["Busiest hour", "12:00"],
          ["Avg prep", "11.4 min"],
        ],
        columns: [
          t("hour", "Hour"),
          n("orders", "Orders"),
          u("net", "Net sales"),
          n("prep", "Prep (min)"),
        ],
        rows,
        chart: { x: "hour", y: "orders", label: "Orders" },
      }
    },
  },
  {
    id: "RPT-10",
    name: "Table turnover",
    purpose: "Seating efficiency",
    group: "Operations",
    roles: ["GM", "BRMGR", "SUPV"],
    filters: ["Period", "Branch", "Area"],
    phase: 2,
    build: () => {
      const rows = ["Indoor", "Terrace", "VIP", "Bar"].map((a, i) => ({
        area: a,
        seatings: [62, 28, 6, 19][i],
        covers: [188, 76, 42, 24][i],
        dining: [52, 61, 96, 38][i],
        turns: [5.6, 4.7, 3, 6.3][i],
      }))
      return {
        kpis: [
          ["Seatings", "115"],
          ["Avg dining", "58 min"],
        ],
        columns: [
          t("area", "Area"),
          n("seatings", "Seatings"),
          n("covers", "Covers"),
          n("dining", "Avg dining (min)"),
          n("turns", "Turns per table"),
        ],
        rows,
        chart: { x: "area", y: "turns", label: "Turns per table" },
      }
    },
  },
  {
    id: "RPT-11",
    name: "Cancelled and voided items",
    purpose: "Loss control",
    group: "Control",
    roles: FIN,
    filters: ["Period", "Branch", "Employee", "Reason"],
    phase: 1,
    build: () => {
      const rows = [
        [
          "Mango Sticky Rice",
          2,
          8,
          "Before preparation",
          "Customer changed mind",
          "Sokha Heng",
          "—",
          "No",
        ],
        [
          "Fish Amok",
          1,
          8.5,
          "After preparation",
          "Kitchen error",
          "Dara Mean",
          "Dara Pich",
          "Yes",
        ],
        [
          "Latte",
          1,
          3,
          "Before preparation",
          "Wrong item entered",
          "Lina Chhay",
          "—",
          "No",
        ],
      ].map(([item, qty, value, st, reason, req, app, waste]) => ({
        item,
        qty,
        value,
        st,
        reason,
        req,
        app,
        waste,
      })) as Record<string, string | number>[]
      return {
        kpis: [
          ["Voids", "4"],
          ["Value", "$19.50"],
          ["With waste", "1"],
        ],
        columns: [
          t("item", "Item"),
          n("qty", "Quantity"),
          u("value", "Value"),
          t("st", "Status at cancellation"),
          t("reason", "Reason"),
          t("req", "Requester"),
          t("app", "Approver"),
          t("waste", "Waste"),
        ],
        rows,
      }
    },
  },
  {
    id: "RPT-12",
    name: "Refund report",
    purpose: "Refund control",
    group: "Control",
    roles: FIN,
    filters: ["Period", "Branch", "Employee", "Method"],
    phase: 1,
    build: () => ({
      kpis: [
        ["Refunds", "3"],
        ["Total", "$39.90"],
      ],
      columns: [
        t("no", "Refund"),
        t("receipt", "Receipt"),
        u("amount", "Amount"),
        t("method", "Method"),
        t("reason", "Reason"),
        t("req", "Requester"),
        t("app", "Approver"),
      ],
      rows: [
        {
          no: "RF-0088",
          receipt: "R-2026-4402",
          amount: 12.4,
          method: "Cash USD",
          reason: "Wrong order",
          req: "Lina Chhay",
          app: "Pending",
        },
        {
          no: "RF-0087",
          receipt: "R-2026-4387",
          amount: 6.5,
          method: "KHQR",
          reason: "Quality issue",
          req: "Lina Chhay",
          app: "Dara Pich",
        },
        {
          no: "RF-0086",
          receipt: "R-2026-4371",
          amount: 21,
          method: "Card",
          reason: "Overcharged",
          req: "Chenda Roeun",
          app: "Rejected",
        },
      ],
    }),
  },
  {
    id: "RPT-13",
    name: "Discount and promotion report",
    purpose: "Discount control",
    group: "Control",
    roles: FIN,
    filters: ["Period", "Branch", "Employee", "Promotion"],
    phase: 1,
    build: (k) => {
      const rows = [
        "Manual 20%",
        "Happy Hour Beer",
        "VIP 10%",
        "Lunch Combo",
        "Staff meal",
      ].map((x, i) => ({
        type: x,
        reason:
          i === 0 ? "Service recovery" : i === 4 ? "Staff meal" : "Promotion",
        value: r2([4.2, 22, 31.5, 28, 12.5][i] * k),
        bills: Math.round([1, 11, 9, 14, 3][i] * k),
      }))
      return {
        kpis: [
          ["Total discounts", usdK(sumOf(rows, "value"))],
          ["Bills affected", String(sumOf(rows, "bills"))],
        ],
        columns: [
          t("type", "Discount"),
          t("reason", "Reason"),
          u("value", "Value"),
          n("bills", "Bills"),
        ],
        rows,
        chart: { x: "type", y: "value", label: "Value", money: true },
      }
    },
  },
  {
    id: "RPT-14",
    name: "Tax and service-charge summary",
    purpose: "Tax preparation support",
    group: "Finance",
    roles: ["OWNER", "ACCT", "AUDITOR"],
    filters: ["Period", "Branch"],
    phase: 1,
    build: (k) => ({
      kpis: [
        ["Tax", usdK(231 * k)],
        ["Service charge", usdK(102.4 * k)],
        ["Basis", "Tax on subtotal + service"],
      ],
      columns: [
        t("profile", "Profile"),
        t("type", "Order type"),
        p("rate", "Rate"),
        u("base", "Taxable base"),
        u("amount", "Amount"),
      ],
      rows: [
        {
          profile: "VAT Standard",
          type: "Dine-in",
          rate: 10,
          base: r2(1780 * k),
          amount: r2(178 * k),
        },
        {
          profile: "VAT Standard",
          type: "Takeaway",
          rate: 10,
          base: r2(530 * k),
          amount: r2(53 * k),
        },
        {
          profile: "Service charge",
          type: "Dine-in",
          rate: 5,
          base: r2(2048 * k),
          amount: r2(102.4 * k),
        },
      ],
    }),
  },
  {
    id: "RPT-15",
    name: "Kitchen preparation time",
    purpose: "Kitchen performance",
    group: "Operations",
    roles: ["GM", "BRMGR", "KMGR"],
    filters: ["Period", "Branch", "Station"],
    phase: 2,
    build: () => {
      const rows = ["Hot", "Cold", "Beverage", "Dessert", "Bar"].map(
        (s, i) => ({
          station: s,
          avg: [12.4, 6.1, 3.4, 5.2, 4.1][i],
          p90: [19.2, 9.8, 5.5, 8.1, 6.9][i],
          late: [7, 1, 0, 0, 1][i],
        })
      )
      return {
        kpis: [
          ["Overall avg", "8.2 min"],
          ["Late tickets", "9"],
        ],
        columns: [
          t("station", "Station"),
          n("avg", "Average (min)"),
          n("p90", "90th percentile (min)"),
          n("late", "Late tickets"),
        ],
        rows,
        chart: { x: "station", y: "avg", label: "Average minutes" },
      }
    },
  },
  {
    id: "RPT-16",
    name: "Ingredient consumption and variance",
    purpose: "Food cost control",
    group: "Inventory",
    roles: ["GM", "KMGR", "INVOFF", "ACCT"],
    filters: ["Period between counts", "Branch", "Category"],
    phase: 2,
    build: () => ({
      kpis: [["Unexplained variance", "$38.40"]],
      columns: [
        t("name", "Ingredient"),
        n("theo", "Theoretical"),
        n("actual", "Actual"),
        n("waste", "Wastage"),
        n("variance", "Variance"),
        u("value", "Value"),
      ],
      rows: ingredients.slice(0, 10).map((i, x) => {
        const theo = 10 + x * 3
        const actual = r2(theo * 1.03)
        return {
          name: i.name,
          theo,
          actual,
          waste: 0.3,
          variance: r2(actual - theo - 0.3),
          value: r2((actual - theo - 0.3) * i.cost),
        }
      }),
    }),
  },
  {
    id: "RPT-17",
    name: "Inventory valuation",
    purpose: "Stock value",
    group: "Inventory",
    roles: ["GM", "INVOFF", "ACCT", "AUDITOR"],
    filters: ["As-of date", "Branch", "Location"],
    phase: 1,
    build: () => {
      const rows = ingredients.map((i) => ({
        name: i.name,
        location: i.location,
        onHand: i.onHand,
        cost: i.cost,
        value: r2(Math.max(i.onHand, 0) * i.cost),
      }))
      return {
        kpis: [
          ["Valuation", usdK(sumOf(rows, "value"))],
          ["Ingredients", String(rows.length)],
        ],
        columns: [
          t("name", "Ingredient"),
          t("location", "Location"),
          n("onHand", "On hand"),
          u("cost", "Avg cost"),
          u("value", "Value"),
        ],
        rows,
        chart: { x: "name", y: "value", label: "Value", money: true },
      }
    },
  },
  {
    id: "RPT-18",
    name: "Low-stock report",
    purpose: "Replenishment",
    group: "Inventory",
    roles: ["INVOFF", "PUROFF", "KMGR"],
    filters: ["Branch", "Location", "Category"],
    phase: 1,
    build: () => {
      const rows = ingredients
        .filter((i) => i.onHand <= i.reorder)
        .map((i) => ({
          name: i.name,
          onHand: i.onHand,
          reorder: i.reorder,
          suggest: i.reorderQty,
          supplier: i.supplier,
        }))
      return {
        kpis: [["Low items", String(rows.length)]],
        columns: [
          t("name", "Ingredient"),
          n("onHand", "On hand"),
          n("reorder", "Reorder level"),
          n("suggest", "Suggested"),
          t("supplier", "Preferred supplier"),
        ],
        rows,
      }
    },
  },
  {
    id: "RPT-19",
    name: "Wastage report",
    purpose: "Waste reduction",
    group: "Inventory",
    roles: ["GM", "KMGR", "INVOFF", "ACCT"],
    filters: ["Period", "Branch", "Reason"],
    phase: 2,
    build: () => ({
      kpis: [["Wastage value", "$48.20"]],
      columns: [
        t("item", "Item"),
        t("reason", "Reason"),
        t("station", "Station"),
        t("user", "User"),
        u("value", "Value"),
      ],
      rows: [
        {
          item: "Mixed vegetables",
          reason: "Spoiled",
          station: "Cold",
          user: "Bunna Kim",
          value: 1.92,
        },
        {
          item: "Fish Amok",
          reason: "Prepared but cancelled",
          station: "Hot",
          user: "Ratha Seng",
          value: 3.05,
        },
        {
          item: "Coconut cream",
          reason: "Expired",
          station: "Hot",
          user: "Rotha Ly",
          value: 14.5,
        },
      ],
    }),
  },
  {
    id: "RPT-20",
    name: "Purchase report",
    purpose: "Spending",
    group: "Purchasing",
    roles: ["GM", "PUROFF", "ACCT"],
    filters: ["Period", "Branch", "Supplier"],
    phase: 2,
    build: () => {
      const rows = purchaseOrders.map((o) => ({
        po: o.id,
        supplier: o.supplier,
        value: o.total,
        status: o.status,
      }))
      return {
        kpis: [["PO value", usdK(sumOf(rows, "value"))]],
        columns: [
          t("po", "PO"),
          t("supplier", "Supplier"),
          u("value", "Value"),
          t("status", "Status"),
        ],
        rows,
      }
    },
  },
  {
    id: "RPT-21",
    name: "Supplier report",
    purpose: "Supplier performance and balances",
    group: "Purchasing",
    roles: ["PUROFF", "ACCT", "GM"],
    filters: ["Period", "Supplier"],
    phase: 2,
    build: () => {
      const rows = suppliers.map((s) => ({
        name: s.name,
        onTime: s.onTime,
        balance: s.balance,
        terms: s.terms,
      }))
      return {
        kpis: [["Total owed", usdK(sumOf(rows, "balance"))]],
        columns: [
          t("name", "Supplier"),
          p("onTime", "On time"),
          u("balance", "Balance"),
          t("terms", "Terms"),
        ],
        rows,
        chart: { x: "name", y: "balance", label: "Balance", money: true },
      }
    },
  },
  {
    id: "RPT-22",
    name: "Expense report",
    purpose: "Cost control",
    group: "Finance",
    roles: ["OWNER", "GM", "ACCT", "AUDITOR"],
    filters: ["Period", "Branch", "Category"],
    phase: 2,
    build: () => {
      const rows = expenses
        .filter((e) => e.currency === "USD")
        .map((e) => ({
          id: e.id,
          category: e.category,
          method: e.method || "—",
          status: e.status,
          amount: e.amount,
        }))
      return {
        kpis: [["Total", usdK(sumOf(rows, "amount"))]],
        columns: [
          t("id", "Expense"),
          t("category", "Category"),
          t("method", "Method"),
          t("status", "Status"),
          u("amount", "Amount"),
        ],
        rows,
      }
    },
  },
  {
    id: "RPT-23",
    name: "Food cost and gross margin",
    purpose: "Menu engineering",
    group: "Finance",
    roles: ["OWNER", "GM", "KMGR", "ACCT"],
    filters: ["Period", "Branch", "Category"],
    phase: 2,
    build: () => {
      const rows = recipes.map((x, i) => ({
        item: x.item,
        cost: x.cost,
        price: x.price,
        pct: r2((x.cost / x.price) * 100),
        margin: r2(x.price - x.cost),
        qty: 40 - i * 4,
      }))
      return {
        kpis: [["Avg food cost", "33.1%"]],
        columns: [
          t("item", "Item"),
          u("cost", "Recipe cost"),
          u("price", "Price"),
          p("pct", "Cost %"),
          u("margin", "Margin"),
          n("qty", "Sold"),
        ],
        rows,
        chart: { x: "item", y: "pct", label: "Food cost %" },
      }
    },
  },
  {
    id: "RPT-24",
    name: "Cashier shift report",
    purpose: "Cash accountability",
    group: "Finance",
    roles: [...FIN, "CASHIER"],
    filters: ["Period", "Branch", "Cashier"],
    phase: 1,
    build: () => ({
      kpis: [
        ["Sessions", "3"],
        ["Net variance", "−$7.00"],
      ],
      columns: [
        t("id", "Session"),
        t("cashier", "Cashier"),
        u("expected", "Expected USD"),
        u("counted", "Counted USD"),
        u("variance", "Variance"),
        t("approver", "Approver"),
      ],
      rows: [
        {
          id: "CS-0411",
          cashier: "Chenda Roeun",
          expected: 738.5,
          counted: 738.5,
          variance: 0,
          approver: "Dara Pich",
        },
        {
          id: "CS-0410",
          cashier: "Lina Chhay",
          expected: 553.75,
          counted: 546.75,
          variance: -7,
          approver: "Pending",
        },
      ],
    }),
  },
  {
    id: "RPT-25",
    name: "Customer purchase history",
    purpose: "Customer service",
    group: "Sales",
    roles: ["GM", "BRMGR"],
    filters: ["Customer", "Period"],
    phase: 2,
    build: () => ({
      kpis: [["Customers", "2"]],
      columns: [
        t("name", "Customer"),
        n("visits", "Visits"),
        u("spend", "Spend"),
        t("last", "Last visit"),
        t("phone", "Contact"),
      ],
      rows: [
        {
          name: "Chan Bopha",
          visits: 42,
          spend: 1284.5,
          last: "07/11/2026",
          phone: "•••• ••• 678",
        },
        {
          name: "Lim Dalin",
          visits: 31,
          spend: 980.6,
          last: "06/11/2026",
          phone: "•••• ••• 021",
        },
      ],
    }),
  },
  {
    id: "RPT-26",
    name: "Control exceptions",
    purpose: "Fraud and error detection",
    group: "Control",
    roles: ["OWNER", "GM", "AUDITOR"],
    filters: ["Period", "Branch"],
    phase: 2,
    build: () => ({
      kpis: [["Exceptions", "5"]],
      columns: [
        t("type", "Exception"),
        t("ref", "Reference"),
        t("user", "User"),
        t("time", "Time"),
      ],
      rows: [
        {
          type: "Forced session close",
          ref: "CS-0409",
          user: "Sopheak Nou",
          time: "07/11 00:30",
        },
        {
          type: "Receipt reprint",
          ref: "R-2026-4398",
          user: "Lina Chhay",
          time: "08/11 11:02",
        },
        {
          type: "Negative stock",
          ref: "Crab",
          user: "System",
          time: "07/11 22:15",
        },
        {
          type: "Unmapped item sold",
          ref: "Bottled Water",
          user: "System",
          time: "08/11 12:00",
        },
        {
          type: "Open orders at day end",
          ref: "2 orders",
          user: "Dara Pich",
          time: "07/11 23:50",
        },
      ],
    }),
  },
]
