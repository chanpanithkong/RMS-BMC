// Illustrative demo data. Prices, rates and names are not real business values.
import type {
  Category,
  FloorTable,
  MenuItem,
  ModifierGroup,
  Notice,
  Order,
  OrderLine,
  Reservation,
  WaitParty,
  CashierSession,
  ItemStatus,
  Station,
} from "./types"

export const BUSINESS_DATE = "08/11/2026"

export const categories: Category[] = [
  {
    id: "rice",
    name: "Rice & Noodles",
    km: "បាយ និងមី",
    order: 1,
    active: true,
  },
  {
    id: "mains",
    name: "Khmer Mains",
    km: "ម្ហូបខ្មែរ",
    order: 2,
    active: true,
  },
  { id: "soups", name: "Soups", km: "ស៊ុប", order: 3, active: true },
  {
    id: "starters",
    name: "Salads & Starters",
    km: "សាឡាត់",
    order: 4,
    active: true,
  },
  { id: "desserts", name: "Desserts", km: "បង្អែម", order: 5, active: true },
  {
    id: "coffee",
    name: "Coffee & Tea",
    km: "កាហ្វេ និងតែ",
    order: 6,
    active: true,
  },
  { id: "drinks", name: "Soft Drinks", km: "ភេសជ្ជៈ", order: 7, active: true },
  { id: "bar", name: "Beer & Cocktails", km: "ស្រា", order: 8, active: true },
]

export const modifierGroups: ModifierGroup[] = [
  {
    id: "spice",
    name: "Spice level",
    km: "កម្រិតហឹរ",
    min: 1,
    max: 1,
    modifiers: [
      { id: "s0", name: "No chilli", delta: 0 },
      { id: "s1", name: "Mild", delta: 0 },
      { id: "s2", name: "Medium", delta: 0 },
      { id: "s3", name: "Hot", delta: 0 },
    ],
  },
  {
    id: "sugar",
    name: "Sugar level",
    km: "កម្រិតស្ករ",
    min: 1,
    max: 1,
    modifiers: [
      { id: "u0", name: "0%", delta: 0 },
      { id: "u50", name: "50%", delta: 0 },
      { id: "u100", name: "100%", delta: 0 },
    ],
  },
  {
    id: "milk",
    name: "Milk",
    km: "ទឹកដោះគោ",
    min: 0,
    max: 1,
    modifiers: [
      { id: "m1", name: "Oat milk", delta: 0.75 },
      { id: "m2", name: "Soy milk", delta: 0.5 },
    ],
  },
  {
    id: "extras",
    name: "Extra toppings",
    km: "បន្ថែម",
    min: 0,
    max: 3,
    modifiers: [
      { id: "e1", name: "Fried egg", delta: 0.75 },
      { id: "e2", name: "Extra chicken", delta: 1.5 },
      { id: "e3", name: "Extra rice", delta: 0.5 },
      { id: "e4", name: "Cashews", delta: 0.75 },
    ],
  },
  {
    id: "shot",
    name: "Coffee add-ons",
    km: "បន្ថែមកាហ្វេ",
    min: 0,
    max: 2,
    modifiers: [
      { id: "x1", name: "Extra shot", delta: 0.5 },
      { id: "x2", name: "Caramel syrup", delta: 0.5 },
    ],
  },
]

const item = (
  id: string,
  code: string,
  name: string,
  km: string,
  cat: string,
  station: Station,
  price: number,
  groups: string[] = [],
  extra: Partial<MenuItem> = {}
): MenuItem => ({
  id,
  code,
  name,
  km,
  cat,
  station,
  price,
  groups,
  type: ["coffee", "drinks", "bar"].includes(cat) ? "Beverage" : "Food",
  available: true,
  active: true,
  tax: "VAT Standard",
  desc: "",
  channels: ["POS", "Online"],
  ...extra,
})

export const menuItems: MenuItem[] = [
  item("fried-rice", "RN-01", "Fried Rice", "បាយឆា", "rice", "Hot", 5, [
    "spice",
    "extras",
  ]),
  item(
    "beef-noodle",
    "RN-02",
    "Beef Stir-fried Noodles",
    "មីឆាសាច់គោ",
    "rice",
    "Hot",
    5.5,
    ["spice", "extras"]
  ),
  item(
    "kuy-teav",
    "RN-03",
    "Kuy Teav Pork Noodle",
    "គុយទាវសាច់ជ្រូក",
    "rice",
    "Hot",
    4.5,
    ["extras"]
  ),
  item("num-banh", "RN-04", "Num Banh Chok", "នំបញ្ចុក", "rice", "Hot", 4),
  item(
    "pork-rice",
    "RN-05",
    "Grilled Pork & Broken Rice",
    "បាយសាច់ជ្រូក",
    "rice",
    "Hot",
    4.25,
    ["extras"]
  ),
  item("amok", "MN-01", "Fish Amok", "អាម៉ុកត្រី", "mains", "Hot", 8.5, [
    "spice",
  ]),
  item(
    "lok-lak",
    "MN-02",
    "Beef Lok Lak",
    "ឡុកឡាក់សាច់គោ",
    "mains",
    "Hot",
    9.5,
    ["extras"],
    {
      variants: [
        { name: "Regular", price: 9.5 },
        { name: "Large", price: 12.5 },
      ],
    }
  ),
  item(
    "kampot-crab",
    "MN-03",
    "Kampot Pepper Crab",
    "ក្តាមម្រេចកំពត",
    "mains",
    "Hot",
    14,
    ["spice"],
    { available: false }
  ),
  item(
    "ginger-chicken",
    "MN-04",
    "Ginger Chicken",
    "មាន់ឆាខ្ញី",
    "mains",
    "Hot",
    7.5,
    ["spice"]
  ),
  item("samlor-korko", "SP-01", "Samlor Korko", "សម្លកកូរ", "soups", "Hot", 7, [
    "spice",
  ]),
  item(
    "sour-soup",
    "SP-02",
    "Sour Fish Soup",
    "សម្លម្ជូរត្រី",
    "soups",
    "Hot",
    7.5
  ),
  item(
    "mango-salad",
    "ST-01",
    "Green Mango Salad",
    "ញាំស្វាយ",
    "starters",
    "Cold",
    5,
    ["spice"]
  ),
  item(
    "spring-rolls",
    "ST-02",
    "Fresh Spring Rolls",
    "ណែម",
    "starters",
    "Cold",
    4.5
  ),
  item(
    "beef-salad",
    "ST-03",
    "Beef Salad Pleah",
    "ភ្លាសាច់គោ",
    "starters",
    "Cold",
    6.5,
    ["spice"]
  ),
  item(
    "mango-rice",
    "DS-01",
    "Mango Sticky Rice",
    "បាយដំណើបស្វាយ",
    "desserts",
    "Dessert",
    4
  ),
  item(
    "pumpkin",
    "DS-02",
    "Pumpkin Custard",
    "សង់ខ្យាល្ពៅ",
    "desserts",
    "Dessert",
    3.5
  ),
  item(
    "iced-coffee",
    "CF-01",
    "Iced Coffee",
    "កាហ្វេទឹកកក",
    "coffee",
    "Beverage",
    2,
    ["sugar", "milk", "shot"],
    {
      variants: [
        { name: "Regular", price: 2 },
        { name: "Large", price: 2.75 },
      ],
    }
  ),
  item("latte", "CF-02", "Caffè Latte", "ឡាតេ", "coffee", "Beverage", 3, [
    "sugar",
    "milk",
    "shot",
  ]),
  item(
    "jasmine",
    "CF-03",
    "Jasmine Tea",
    "តែម្លិះ",
    "coffee",
    "Beverage",
    1.5,
    ["sugar"]
  ),
  item(
    "palm-juice",
    "DR-01",
    "Palm Juice",
    "ទឹកត្នោត",
    "drinks",
    "Beverage",
    2.5
  ),
  item(
    "lime-soda",
    "DR-02",
    "Lime Soda",
    "សូដាក្រូចឆ្មារ",
    "drinks",
    "Beverage",
    2.25,
    ["sugar"]
  ),
  item("water", "DR-03", "Bottled Water", "ទឹកសុទ្ធ", "drinks", "None", 1, [], {
    sku: "8850000000011",
  }),
  item("draft-beer", "BR-01", "Draft Beer", "ស្រាបៀរស្រស់", "bar", "Bar", 2.5),
  item("mojito", "BR-02", "Palm Sugar Mojito", "ម៉ូហ៊ីតូ", "bar", "Bar", 5.5),
]

const sv = (m: number) => -m * 60

let lineSeq = 0
function ln(
  itemId: string,
  qty: number,
  status: ItemStatus,
  sentMin: number,
  extra: Partial<OrderLine> = {}
): OrderLine {
  const m = menuItems.find((i) => i.id === itemId)!
  lineSeq += 1
  return {
    id: `l${lineSeq}`,
    itemId,
    name: m.name,
    km: m.km,
    modifiers: [],
    unitPrice: m.price,
    qty,
    status,
    station: m.station,
    sentAt: status === "Pending" ? undefined : sv(sentMin),
    startedAt: ["In Preparation", "Ready", "Served", "Collected"].includes(
      status
    )
      ? sv(sentMin - 1)
      : undefined,
    readyAt: ["Ready", "Served", "Collected"].includes(status)
      ? sv(Math.max(sentMin - 6, 0))
      : undefined,
    ...extra,
  }
}

function ord(
  no: number,
  partial: Partial<Order> & Pick<Order, "type" | "lines">,
  ageMin: number
): Order {
  return {
    id: `o${no}`,
    no: `#${String(no).padStart(4, "0")}`,
    channel: "POS",
    guests: 2,
    server: "Sokha",
    status: "Open",
    payments: [],
    createdAt: sv(ageMin),
    business: BUSINESS_DATE,
    version: 1,
    timeline: [
      {
        at: sv(ageMin),
        label: "Order created",
        user: partial.server ?? "Sokha",
      },
      {
        at: sv(ageMin - 1),
        label: "Items sent to kitchen",
        user: partial.server ?? "Sokha",
      },
    ],
    ...partial,
  }
}

const paid = (
  id: string,
  applied: number,
  time: string,
  method = "Cash USD"
) => ({
  id,
  method,
  currency: "USD" as const,
  tendered: applied,
  applied,
  change: 0,
  changeCurrency: "USD" as const,
  state: "Confirmed" as const,
  time,
  session: "CS-0412",
})

export const seedOrders: Order[] = [
  ord(
    101,
    {
      type: "DINE_IN",
      table: "A1",
      guests: 4,
      server: "Sokha",
      lines: [
        ln("amok", 2, "In Preparation", 8, {
          modifiers: [{ name: "Medium", delta: 0 }],
        }),
        ln("lok-lak", 1, "Sent", 8, {
          variant: "Large",
          unitPrice: 12.5,
          modifiers: [{ name: "Fried egg", delta: 0.75 }],
        }),
        ln("mango-salad", 1, "Ready", 8, {
          modifiers: [{ name: "Mild", delta: 0 }],
          note: "ALLERGY: peanuts",
          allergy: true,
        }),
        ln("iced-coffee", 2, "Served", 9, {
          modifiers: [{ name: "50%", delta: 0 }],
        }),
      ],
    },
    12
  ),
  ord(
    102,
    {
      type: "DINE_IN",
      table: "A3",
      guests: 2,
      server: "Dara",
      lines: [
        ln("kuy-teav", 2, "Served", 26),
        ln("palm-juice", 2, "Served", 27),
      ],
      billPrinted: true,
    },
    34
  ),
  ord(
    103,
    {
      type: "DINE_IN",
      table: "B2",
      guests: 6,
      server: "Dara",
      lines: [
        ln("fried-rice", 3, "In Preparation", 23, {
          modifiers: [{ name: "Hot", delta: 0 }],
        }),
        ln("samlor-korko", 2, "Sent", 23, {
          modifiers: [{ name: "Medium", delta: 0 }],
          note: "Less fish sauce",
        }),
        ln("spring-rolls", 2, "Ready", 23),
        ln("draft-beer", 4, "Served", 24),
      ],
    },
    28
  ),
  ord(
    104,
    {
      type: "TAKEAWAY",
      pickup: "Vanna",
      guests: 1,
      server: "Lina",
      lines: [
        ln("beef-noodle", 1, "In Preparation", 12, {
          modifiers: [{ name: "No chilli", delta: 0 }],
        }),
        ln("latte", 1, "Ready", 12, { modifiers: [{ name: "0%", delta: 0 }] }),
      ],
      payments: [paid("p1", 9.35, "12:41")],
    },
    13
  ),
  ord(
    105,
    {
      type: "TAKEAWAY",
      pickup: "Rath",
      guests: 1,
      server: "Lina",
      lines: [
        ln("pork-rice", 2, "Ready", 16),
        ln("lime-soda", 2, "Ready", 16, {
          modifiers: [{ name: "50%", delta: 0 }],
        }),
      ],
      payments: [paid("p2", 14.3, "12:35")],
    },
    17
  ),
  ord(
    106,
    {
      type: "DELIVERY",
      channel: "PLATFORM",
      guests: 1,
      server: "Lina",
      customer: "Chan Bopha",
      lines: [
        ln("ginger-chicken", 1, "Sent", 3, {
          modifiers: [{ name: "Mild", delta: 0 }],
        }),
        ln("mango-rice", 1, "Sent", 3),
      ],
      delivery: {
        phone: "012 345 678",
        address: "St 240, Daun Penh",
        zone: "Zone A",
        fee: 1,
        status: "Pending Assignment",
        platform: "Food Platform A",
        platformRef: "FP-88213",
        commission: 2.1,
      },
    },
    4
  ),
  ord(
    107,
    {
      type: "DELIVERY",
      guests: 1,
      server: "Lina",
      customer: "Meas Pisey",
      lines: [
        ln("lok-lak", 1, "Ready", 22, { unitPrice: 9.5, variant: "Regular" }),
        ln("jasmine", 1, "Ready", 22, {
          modifiers: [{ name: "0%", delta: 0 }],
        }),
      ],
      delivery: {
        phone: "097 222 118",
        address: "St 63, BKK1, near market",
        zone: "Zone B",
        fee: 1.5,
        rider: "Kosal",
        status: "Assigned",
      },
    },
    26
  ),
  ord(
    108,
    {
      type: "DINE_IN",
      table: "C1",
      guests: 2,
      server: "Sokha",
      lines: [
        ln("mojito", 2, "In Preparation", 5),
        ln("beef-salad", 1, "Sent", 5, {
          modifiers: [{ name: "Medium", delta: 0 }],
        }),
        ln("mango-rice", 2, "Cancelled", 5, {
          voidType: "Before preparation",
          voidReason: "Customer changed mind",
        }),
      ],
    },
    6
  ),
  ord(
    109,
    {
      type: "TAKEAWAY",
      channel: "ONLINE",
      pickup: "Nimol",
      guests: 1,
      server: "Online",
      onlineState: "Received",
      lines: [
        ln("fried-rice", 1, "Pending", 0, {
          modifiers: [{ name: "Medium", delta: 0 }],
        }),
        ln("iced-coffee", 1, "Pending", 0, {
          modifiers: [{ name: "50%", delta: 0 }],
        }),
      ],
      timeline: [
        { at: sv(1), label: "Online order received", user: "Customer" },
      ],
    },
    1
  ),
  ...["Sokha", "Dara", "Lina", "Sokha", "Dara", "Lina", "Sokha", "Dara"].map(
    (server, i) => {
      const no = 90 + i
      const type = i % 3 === 2 ? "TAKEAWAY" : "DINE_IN"
      const items = [
        ["amok", "palm-juice"],
        ["lok-lak", "draft-beer"],
        ["fried-rice", "latte"],
        ["kuy-teav", "jasmine"],
        ["ginger-chicken", "lime-soda"],
        ["beef-noodle", "water"],
        ["samlor-korko", "mojito"],
        ["pork-rice", "iced-coffee"],
      ][i]
      const lines = items.map((id) =>
        ln(
          id,
          1 + (i % 2),
          type === "DINE_IN" ? "Served" : "Collected",
          120 + i * 18
        )
      )
      const gross = lines.reduce((s, l) => s + l.unitPrice * l.qty, 0)
      const total =
        type === "DINE_IN"
          ? Math.round(gross * 1.05 * 1.1 * 100) / 100
          : Math.round(gross * 1.1 * 100) / 100
      const cancelled = i === 5
      return ord(
        no,
        {
          type,
          server,
          guests: 2 + (i % 3),
          table:
            type === "DINE_IN"
              ? ["A2", "B1", "", "C2", "B3", "", "A4", "C3"][i]
              : undefined,
          pickup: type === "TAKEAWAY" ? "Walk-in" : undefined,
          status: cancelled ? "Cancelled" : "Completed",
          payments: cancelled
            ? []
            : [
                paid(
                  `h${i}`,
                  total,
                  `${11 + (i % 2)}:${10 + i * 5}`,
                  i % 2 ? "KHQR" : "Cash USD"
                ),
              ],
          receiptNo: cancelled ? undefined : `R-2026-${String(4410 + i)}`,
          lines: cancelled
            ? lines.map((l) => ({
                ...l,
                status: "Cancelled" as const,
                voidType: "Before preparation" as const,
              }))
            : lines,
        },
        130 + i * 18
      )
    }
  ),
]

const tbl = (
  id: string,
  area: string,
  capacity: number,
  shape: FloorTable["shape"],
  x: number,
  y: number,
  extra: Partial<FloorTable> = {}
): FloorTable => ({
  id,
  code: id,
  area,
  capacity,
  shape,
  x,
  y,
  state: "Available",
  guests: 0,
  ...extra,
})

export const seedTables: FloorTable[] = [
  tbl("A1", "Indoor", 4, "square", 8, 10, {
    state: "Ordering",
    guests: 4,
    server: "Sokha",
    orderId: "o101",
    seatedAt: sv(14),
  }),
  tbl("A2", "Indoor", 2, "round", 30, 10),
  tbl("A3", "Indoor", 2, "round", 52, 10, {
    state: "Awaiting Payment",
    guests: 2,
    server: "Dara",
    orderId: "o102",
    seatedAt: sv(38),
  }),
  tbl("A4", "Indoor", 4, "square", 74, 10, {
    state: "Reserved",
    upcoming: "Sophea · 13:30 · 4 pax",
  }),
  tbl("B1", "Indoor", 4, "square", 8, 42, { state: "Cleaning" }),
  tbl("B2", "Indoor", 8, "rect", 32, 42, {
    state: "Ordering",
    guests: 6,
    server: "Dara",
    orderId: "o103",
    seatedAt: sv(30),
  }),
  tbl("B3", "Indoor", 4, "square", 74, 42, {
    state: "Seated",
    guests: 3,
    server: "Sokha",
    seatedAt: sv(2),
  }),
  tbl("C1", "Indoor", 2, "round", 8, 74, {
    state: "Ordering",
    guests: 2,
    server: "Sokha",
    orderId: "o108",
    seatedAt: sv(8),
  }),
  tbl("C2", "Indoor", 2, "round", 30, 74),
  tbl("C3", "Indoor", 4, "square", 52, 74, { outOfService: "Broken chair" }),
  tbl("C4", "Indoor", 2, "round", 74, 74, {
    state: "Served",
    guests: 2,
    server: "Dara",
    seatedAt: sv(44),
  }),
  tbl("T1", "Terrace", 4, "square", 10, 15),
  tbl("T2", "Terrace", 4, "square", 40, 15, {
    state: "Seated",
    guests: 2,
    server: "Lina",
    seatedAt: sv(5),
  }),
  tbl("T3", "Terrace", 6, "rect", 68, 15),
  tbl("T4", "Terrace", 2, "round", 10, 60),
  tbl("T5", "Terrace", 2, "round", 40, 60, { flagged: true, orderId: "o999" }),
  tbl("V1", "VIP", 10, "rect", 20, 25, {
    state: "Reserved",
    upcoming: "Corporate lunch · 13:00 · 10 pax",
  }),
  tbl("V2", "VIP", 8, "rect", 60, 25),
  tbl("BR1", "Bar", 2, "round", 15, 30, {
    state: "Ordering",
    guests: 1,
    server: "Vuthy",
    seatedAt: sv(20),
  }),
  tbl("BR2", "Bar", 2, "round", 45, 30),
  tbl("BR3", "Bar", 2, "round", 75, 30),
]

export const seedReservations: Reservation[] = [
  {
    id: "r1",
    name: "Sophea Keo",
    phone: "012 880 441",
    party: 4,
    date: BUSINESS_DATE,
    start: 13.5,
    duration: 1.5,
    table: "A4",
    status: "Confirmed",
    notes: "Birthday — dessert plate",
  },
  {
    id: "r2",
    name: "Corporate lunch",
    phone: "023 444 120",
    party: 10,
    date: BUSINESS_DATE,
    start: 13,
    duration: 2,
    table: "V1",
    status: "Confirmed",
    notes: "Set menu",
  },
  {
    id: "r3",
    name: "Rithy Lim",
    phone: "096 112 339",
    party: 2,
    date: BUSINESS_DATE,
    start: 18,
    duration: 1.5,
    table: "A2",
    status: "Confirmed",
  },
  {
    id: "r4",
    name: "Mony Tep",
    phone: "011 730 225",
    party: 6,
    date: BUSINESS_DATE,
    start: 19,
    duration: 2,
    table: "T3",
    status: "Confirmed",
    notes: "Outdoor preferred",
  },
  {
    id: "r5",
    name: "Dany Heng",
    phone: "078 901 556",
    party: 2,
    date: BUSINESS_DATE,
    start: 19.5,
    duration: 1.5,
    table: "C2",
    status: "Requested",
  },
  {
    id: "r6",
    name: "Bopha Ouk",
    phone: "085 667 012",
    party: 4,
    date: BUSINESS_DATE,
    start: 12,
    duration: 1.5,
    table: "T1",
    status: "No-show",
  },
  {
    id: "r7",
    name: "Vicheka So",
    phone: "012 554 980",
    party: 8,
    date: BUSINESS_DATE,
    start: 18.5,
    duration: 2,
    table: "V2",
    status: "Confirmed",
    notes: "2 high chairs",
  },
]

export const seedWaitlist: WaitParty[] = [
  {
    id: "w1",
    name: "Kimly",
    party: 3,
    phone: "012 111 907",
    added: "12:48",
    quoted: 15,
    status: "Waiting",
  },
  {
    id: "w2",
    name: "Sarath",
    party: 2,
    phone: "097 345 112",
    added: "12:52",
    quoted: 10,
    status: "Notified",
  },
  {
    id: "w3",
    name: "Thida",
    party: 5,
    phone: "015 220 873",
    added: "12:55",
    quoted: 25,
    status: "Waiting",
  },
]

export const seedNotices: Notice[] = [
  {
    id: "n1",
    title: "Ticket delayed",
    body: "Order #0103 at Hot station is over 20 minutes.",
    kind: "Kitchen",
    at: "12:54",
    read: false,
    href: "/kds",
  },
  {
    id: "n2",
    title: "Low stock: Jasmine rice",
    body: "On hand 8.0 kg, reorder level 15.0 kg.",
    kind: "Stock",
    at: "12:30",
    read: false,
    href: "/inventory",
  },
  {
    id: "n3",
    title: "Refund awaiting approval",
    body: "Receipt R-2026-4402, $12.40, requested by Lina.",
    kind: "Approval",
    at: "12:22",
    read: false,
    href: "/billing?tab=refunds",
  },
  {
    id: "n4",
    title: "Expiring soon: Coconut cream",
    body: "Batch CC-1108 expires in 2 days.",
    kind: "Stock",
    at: "09:00",
    read: false,
    href: "/inventory?tab=balances",
  },
  {
    id: "n5",
    title: "PO-1043 awaiting approval",
    body: "Total $640.00, within your limit.",
    kind: "Approval",
    at: "11:15",
    read: true,
    href: "/purchasing?tab=orders",
  },
  {
    id: "n6",
    title: "Printer offline",
    body: "Kitchen printer 2 (Cold) is not responding. Jobs are queued.",
    kind: "System",
    at: "11:02",
    read: true,
    href: "/settings?tab=stations",
  },
  {
    id: "n7",
    title: "Payment pending",
    body: "KHQR payment on #0097 has not been confirmed.",
    kind: "Payment",
    at: "10:48",
    read: true,
    href: "/billing?tab=payments",
  },
  {
    id: "n8",
    title: "Session still open",
    body: "Chenda's cashier session from yesterday is still open.",
    kind: "Cash",
    at: "08:05",
    read: true,
    href: "/shifts?tab=history",
  },
]

export const seedSessions: CashierSession[] = [
  {
    id: "CS-0412",
    cashier: "Lina Chhay",
    branch: "Riverside",
    terminal: "POS-1",
    opened: "08/11/2026 08:02",
    floatUSD: 50,
    floatKHR: 100000,
    salesUSD: 420,
    salesKHR: 312300,
    refundsUSD: 10,
    status: "Open",
    movements: [
      {
        id: "m1",
        kind: "Paid-out",
        currency: "USD",
        amount: 15,
        reason: "Ice delivery",
        time: "10:12",
        approvedBy: "Dara Pich",
      },
    ],
  },
  {
    id: "CS-0411",
    cashier: "Chenda Roeun",
    branch: "Riverside",
    terminal: "POS-2",
    opened: "07/11/2026 16:00",
    closed: "07/11/2026 23:12",
    floatUSD: 50,
    floatKHR: 100000,
    salesUSD: 688.5,
    salesKHR: 512000,
    refundsUSD: 0,
    status: "Closed",
    countedUSD: 738.5,
    countedKHR: 611900,
    varianceUSD: 0,
    varianceKHR: -100,
    movements: [],
    approver: "Dara Pich",
  },
  {
    id: "CS-0410",
    cashier: "Lina Chhay",
    branch: "Riverside",
    terminal: "POS-1",
    opened: "07/11/2026 08:00",
    closed: "07/11/2026 16:04",
    floatUSD: 50,
    floatKHR: 100000,
    salesUSD: 512.25,
    salesKHR: 288000,
    refundsUSD: 8.5,
    status: "Pending Approval",
    countedUSD: 546.75,
    countedKHR: 388000,
    varianceUSD: -7,
    varianceKHR: 0,
    movements: [],
  },
  {
    id: "CS-0409",
    cashier: "Vuthy Sam",
    branch: "Riverside",
    terminal: "BAR-1",
    opened: "06/11/2026 17:00",
    closed: "07/11/2026 00:30",
    floatUSD: 30,
    floatKHR: 50000,
    salesUSD: 301,
    salesKHR: 96000,
    refundsUSD: 0,
    status: "Force Closed",
    movements: [],
    approver: "Sopheak Nou",
  },
]
