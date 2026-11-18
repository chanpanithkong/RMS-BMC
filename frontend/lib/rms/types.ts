export type Role =
  | "SYSADMIN"
  | "OWNER"
  | "GM"
  | "BRMGR"
  | "SUPV"
  | "CASHIER"
  | "WAITER"
  | "KMGR"
  | "COOK"
  | "BAR"
  | "INVOFF"
  | "PUROFF"
  | "ACCT"
  | "AUDITOR"

export type OrderType = "DINE_IN" | "TAKEAWAY" | "DELIVERY"
export type Channel = "POS" | "ONLINE" | "PLATFORM"
export type OrderStatus = "Draft" | "Open" | "Completed" | "Cancelled"
export type ItemStatus =
  | "Pending"
  | "Sent"
  | "In Preparation"
  | "Ready"
  | "Served"
  | "Collected"
  | "Cancelled"
export type VoidType = "Before preparation" | "After preparation" | "Comp"
export type Station = "Hot" | "Cold" | "Beverage" | "Dessert" | "Bar" | "None"
export type TableState =
  | "Available"
  | "Reserved"
  | "Seated"
  | "Ordering"
  | "Served"
  | "Awaiting Payment"
  | "Cleaning"
export type DeliveryStatus =
  | "Pending Assignment"
  | "Assigned"
  | "Out for Delivery"
  | "Delivered"
  | "Failed"
  | "Cancelled"

export interface Category {
  id: string
  name: string
  km: string
  order: number
  active: boolean
}
export interface Modifier {
  id: string
  name: string
  delta: number
  available?: boolean
}
export interface ModifierGroup {
  id: string
  name: string
  km: string
  min: number
  max: number
  modifiers: Modifier[]
}
export interface Variant {
  name: string
  price: number
}
export interface MenuItem {
  id: string
  code: string
  name: string
  km: string
  cat: string
  station: Station
  price: number
  type: "Food" | "Beverage" | "Other"
  variants?: Variant[]
  groups: string[]
  available: boolean
  active: boolean
  tax: string
  desc: string
  sku?: string
  channels: string[]
  /** API: variant name -> variant id ("Regular" for items without sizes). */
  variantIds?: Record<string, string>
}

export interface LineModifier {
  /** Modifier id (sent to the API). */
  id?: string
  name: string
  delta: number
}
export interface Discount {
  kind: "percent" | "amount"
  value: number
  reason: string
  approvedBy?: string
}
export interface OrderLine {
  id: string
  itemId: string
  name: string
  km: string
  variant?: string
  modifiers: LineModifier[]
  unitPrice: number
  qty: number
  note?: string
  allergy?: boolean
  seat?: number
  status: ItemStatus
  station: Station
  discount?: Discount
  voidType?: VoidType
  voidReason?: string
  /** API: id of the active item discount, so it can be removed. */
  discountId?: string
  /** API: optimistic-lock version for kitchen status changes. */
  version?: number
  sentAt?: number
  startedAt?: number
  readyAt?: number
  modified?: boolean
}
export interface Payment {
  id: string
  method: string
  currency: "USD" | "KHR"
  tendered: number
  rate?: number
  applied: number
  change: number
  changeCurrency: "USD" | "KHR"
  reference?: string
  session?: string
  splitIndex?: number
  state: "Confirmed" | "Pending" | "Failed" | "Voided"
  time: string
}
export interface BillSplit {
  label: string
  total: number
  /** API: the bill this split is paid against, and what is still owed on it. */
  billId?: string
  balance?: number
}
export interface TimelineEvent {
  at: number
  label: string
  user: string
  time?: string
}
export interface DeliveryInfo {
  phone: string
  address: string
  zone: string
  fee: number
  rider?: string
  status: DeliveryStatus
  platform?: string
  platformRef?: string
  commission?: number
}
export interface Order {
  id: string
  no: string
  type: OrderType
  channel: Channel
  table?: string
  pickup?: string
  guests: number
  server: string
  customer?: string
  lines: OrderLine[]
  discount?: Discount
  status: OrderStatus
  payments: Payment[]
  createdAt: number
  timeline: TimelineEvent[]
  held?: string
  version: number
  note?: string
  rush?: Station[]
  billPrinted?: boolean
  splits?: BillSplit[]
  delivery?: DeliveryInfo
  business: string
  receiptNo?: string
  onlineState?: "Received" | "Accepted" | "Rejected"
  /** API: totals calculated by the backend (authoritative, SRS C-02). */
  apiTotals?: {
    gross: number
    itemDiscounts: number
    orderDiscount: number
    subtotal: number
    service: number
    tax: number
    deliveryFee: number
    total: number
    paid: number
    balance: number
  }
  /** API: id of the active order-level discount. */
  discountId?: string
  /** API: table id, for transfers. */
  tableId?: string
}
export interface FloorTable {
  id: string
  code: string
  area: string
  capacity: number
  shape: "square" | "round" | "rect"
  x: number
  y: number
  state: TableState
  guests: number
  server?: string
  orderId?: string
  seatedAt?: number
  outOfService?: string
  group?: string
  upcoming?: string
  flagged?: boolean
}
export interface Reservation {
  id: string
  name: string
  phone: string
  party: number
  date: string
  start: number
  duration: number
  table?: string
  status:
    "Requested" | "Confirmed" | "Seated" | "Completed" | "Cancelled" | "No-show"
  notes?: string
}
export interface WaitParty {
  id: string
  name: string
  party: number
  phone: string
  added: string
  quoted: number
  status: "Waiting" | "Notified" | "Seated" | "Left"
}
export interface Notice {
  id: string
  title: string
  body: string
  kind: "Kitchen" | "Stock" | "Approval" | "Payment" | "System" | "Cash"
  at: string
  read: boolean
  href: string
  roles?: Role[]
}
export interface CashMovement {
  id: string
  kind: "Paid-out" | "Paid-in" | "Cash drop"
  currency: "USD" | "KHR"
  amount: number
  reason: string
  time: string
  approvedBy?: string
}
export interface CashierSession {
  id: string
  cashier: string
  branch: string
  terminal: string
  opened: string
  closed?: string
  floatUSD: number
  floatKHR: number
  salesUSD: number
  salesKHR: number
  refundsUSD: number
  status: "Open" | "Pending Approval" | "Closed" | "Force Closed"
  countedUSD?: number
  countedKHR?: number
  varianceUSD?: number
  varianceKHR?: number
  movements: CashMovement[]
  approver?: string
  /** API: this is the signed-in user's own session. */
  mine?: boolean
  varianceReason?: string
}
export type Row = Record<string, unknown> & { id: string }
