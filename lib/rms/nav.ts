import {
  Armchair,
  BadgePercent,
  Bell,
  BookOpenText,
  Building2,
  CalendarClock,
  ChartColumn,
  ChefHat,
  ClipboardList,
  HandCoins,
  LayoutDashboard,
  Monitor,
  Package,
  ReceiptText,
  ScrollText,
  Settings,
  ShoppingCart,
  Truck,
  UserCog,
  Users,
  UtensilsCrossed,
  Wallet,
  Contact,
  Store,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { Role } from "./types"

export interface NavItem {
  key: string
  href: string
  icon: LucideIcon
  en: string
  km: string
  roles: Role[]
  fullscreen?: boolean
}
export interface NavGroup {
  en: string
  km: string
  items: NavItem[]
}

const ALL: Role[] = [
  "SYSADMIN",
  "OWNER",
  "GM",
  "BRMGR",
  "SUPV",
  "CASHIER",
  "WAITER",
  "KMGR",
  "COOK",
  "BAR",
  "INVOFF",
  "PUROFF",
  "ACCT",
  "AUDITOR",
]

// Role access derived from the SRS §4.3 role–permission matrix.
export const navGroups: NavGroup[] = [
  {
    en: "Service",
    km: "សេវាកម្ម",
    items: [
      {
        key: "dashboard",
        href: "/",
        icon: LayoutDashboard,
        en: "Dashboard",
        km: "ផ្ទាំងគ្រប់គ្រង",
        roles: [
          "SYSADMIN",
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "CASHIER",
          "KMGR",
          "INVOFF",
          "PUROFF",
          "ACCT",
          "AUDITOR",
        ],
      },
      {
        key: "pos",
        href: "/pos",
        icon: Monitor,
        en: "POS",
        km: "ការលក់",
        roles: ["GM", "BRMGR", "SUPV", "CASHIER", "WAITER", "BAR"],
        fullscreen: true,
      },
      {
        key: "orders",
        href: "/orders",
        icon: ClipboardList,
        en: "Orders",
        km: "ការបញ្ជាទិញ",
        roles: [
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "CASHIER",
          "WAITER",
          "KMGR",
          "BAR",
          "ACCT",
          "AUDITOR",
        ],
      },
      {
        key: "kitchen",
        href: "/kitchen",
        icon: ChefHat,
        en: "Kitchen",
        km: "ផ្ទះបាយ",
        roles: [
          "SYSADMIN",
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "CASHIER",
          "WAITER",
          "KMGR",
          "COOK",
          "BAR",
          "AUDITOR",
        ],
      },
      {
        key: "tables",
        href: "/tables",
        icon: Armchair,
        en: "Tables",
        km: "តុ",
        roles: [
          "SYSADMIN",
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "CASHIER",
          "WAITER",
          "AUDITOR",
        ],
      },
      {
        key: "reservations",
        href: "/reservations",
        icon: CalendarClock,
        en: "Reservations",
        km: "ការកក់",
        roles: ["OWNER", "GM", "BRMGR", "SUPV", "CASHIER", "WAITER", "AUDITOR"],
      },
      {
        key: "delivery",
        href: "/delivery",
        icon: Truck,
        en: "Takeaway & Delivery",
        km: "យកទៅ និងដឹកជញ្ជូន",
        roles: ["OWNER", "GM", "BRMGR", "SUPV", "CASHIER", "ACCT", "AUDITOR"],
      },
    ],
  },
  {
    en: "Menu & customers",
    km: "ម៉ឺនុយ និងអតិថិជន",
    items: [
      {
        key: "menu",
        href: "/menu",
        icon: UtensilsCrossed,
        en: "Menu",
        km: "ម៉ឺនុយ",
        roles: [
          "SYSADMIN",
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "CASHIER",
          "WAITER",
          "KMGR",
          "COOK",
          "BAR",
          "ACCT",
          "AUDITOR",
        ],
      },
      {
        key: "promotions",
        href: "/promotions",
        icon: BadgePercent,
        en: "Promotions",
        km: "ការបញ្ចុះតម្លៃ",
        roles: ["OWNER", "GM", "BRMGR", "SUPV", "CASHIER", "ACCT", "AUDITOR"],
      },
      {
        key: "customers",
        href: "/customers",
        icon: Contact,
        en: "Customers",
        km: "អតិថិជន",
        roles: [
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "CASHIER",
          "WAITER",
          "ACCT",
          "AUDITOR",
        ],
      },
    ],
  },
  {
    en: "Back of house",
    km: "ផ្នែកខាងក្រោយ",
    items: [
      {
        key: "inventory",
        href: "/inventory",
        icon: Package,
        en: "Inventory",
        km: "ស្តុក",
        roles: [
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "KMGR",
          "COOK",
          "BAR",
          "INVOFF",
          "PUROFF",
          "ACCT",
          "AUDITOR",
        ],
      },
      {
        key: "recipes",
        href: "/recipes",
        icon: BookOpenText,
        en: "Recipes & Food Cost",
        km: "រូបមន្ត និងថ្លៃដើម",
        roles: [
          "OWNER",
          "GM",
          "BRMGR",
          "KMGR",
          "COOK",
          "BAR",
          "INVOFF",
          "ACCT",
          "AUDITOR",
        ],
      },
      {
        key: "purchasing",
        href: "/purchasing",
        icon: ShoppingCart,
        en: "Purchasing",
        km: "ការទិញ",
        roles: [
          "OWNER",
          "GM",
          "BRMGR",
          "KMGR",
          "INVOFF",
          "PUROFF",
          "ACCT",
          "AUDITOR",
        ],
      },
      {
        key: "suppliers",
        href: "/suppliers",
        icon: Store,
        en: "Suppliers",
        km: "អ្នកផ្គត់ផ្គង់",
        roles: [
          "OWNER",
          "GM",
          "BRMGR",
          "KMGR",
          "INVOFF",
          "PUROFF",
          "ACCT",
          "AUDITOR",
        ],
      },
      {
        key: "expenses",
        href: "/expenses",
        icon: HandCoins,
        en: "Expenses",
        km: "ចំណាយ",
        roles: ["OWNER", "GM", "BRMGR", "SUPV", "PUROFF", "ACCT", "AUDITOR"],
      },
    ],
  },
  {
    en: "People & cash",
    km: "បុគ្គលិក និងសាច់ប្រាក់",
    items: [
      {
        key: "employees",
        href: "/employees",
        icon: Users,
        en: "Employees",
        km: "បុគ្គលិក",
        roles: ALL,
      },
      {
        key: "shifts",
        href: "/shifts",
        icon: Wallet,
        en: "Shifts & Cashiers",
        km: "វេន និងអ្នកគិតលុយ",
        roles: [
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "CASHIER",
          "BAR",
          "ACCT",
          "AUDITOR",
        ],
      },
      {
        key: "billing",
        href: "/billing",
        icon: ReceiptText,
        en: "Bills & Payments",
        km: "វិក្កយបត្រ និងការទូទាត់",
        roles: [
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "CASHIER",
          "BAR",
          "ACCT",
          "AUDITOR",
        ],
      },
    ],
  },
  {
    en: "Insight & admin",
    km: "របាយការណ៍ និងការគ្រប់គ្រង",
    items: [
      {
        key: "reports",
        href: "/reports",
        icon: ChartColumn,
        en: "Reports",
        km: "របាយការណ៍",
        roles: [
          "SYSADMIN",
          "OWNER",
          "GM",
          "BRMGR",
          "SUPV",
          "CASHIER",
          "KMGR",
          "INVOFF",
          "PUROFF",
          "ACCT",
          "AUDITOR",
        ],
      },
      {
        key: "notifications",
        href: "/notifications",
        icon: Bell,
        en: "Notifications",
        km: "ការជូនដំណឹង",
        roles: ALL,
      },
      {
        key: "users",
        href: "/users",
        icon: UserCog,
        en: "User Management",
        km: "គ្រប់គ្រងអ្នកប្រើ",
        roles: ["SYSADMIN", "OWNER", "GM", "BRMGR", "AUDITOR"],
      },
      {
        key: "audit",
        href: "/audit",
        icon: ScrollText,
        en: "Audit Trail",
        km: "កំណត់ត្រាសវនកម្ម",
        roles: ["SYSADMIN", "OWNER", "GM", "BRMGR", "ACCT", "AUDITOR"],
      },
      {
        key: "branches",
        href: "/branches",
        icon: Building2,
        en: "Branches",
        km: "សាខា",
        roles: ["SYSADMIN", "OWNER", "GM", "BRMGR", "ACCT", "AUDITOR"],
      },
      {
        key: "settings",
        href: "/settings",
        icon: Settings,
        en: "Settings",
        km: "ការកំណត់",
        roles: ["SYSADMIN", "OWNER", "GM", "BRMGR", "KMGR", "ACCT", "AUDITOR"],
      },
    ],
  },
]

export const allNav = navGroups.flatMap((g) => g.items)

export function navForPath(rawPath: string) {
  const path = rawPath.startsWith("/kds") ? "/kitchen" : rawPath
  return [...allNav]
    .filter((n) =>
      n.href === "/"
        ? path === "/"
        : path === n.href || path.startsWith(n.href + "/")
    )
    .sort((a, b) => b.href.length - a.href.length)[0]
}

export const roleLabels: Record<Role, string> = {
  SYSADMIN: "System Administrator",
  OWNER: "Restaurant Owner",
  GM: "General Manager",
  BRMGR: "Branch Manager",
  SUPV: "Supervisor",
  CASHIER: "Cashier",
  WAITER: "Waiter",
  KMGR: "Kitchen Manager",
  COOK: "Chef / Cook",
  BAR: "Bartender",
  INVOFF: "Inventory Officer",
  PUROFF: "Purchasing Officer",
  ACCT: "Accountant",
  AUDITOR: "Auditor",
}

export const financialRoles: Role[] = [
  "OWNER",
  "GM",
  "BRMGR",
  "ACCT",
  "AUDITOR",
]
export const approverRoles: Role[] = ["OWNER", "GM", "BRMGR", "SUPV"]
