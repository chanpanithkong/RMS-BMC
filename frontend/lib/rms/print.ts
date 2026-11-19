/**
 * Paper bills and receipts (SRS §6.7, BR-049). The content comes from GET /bills/{id}/document; this lays it out
 * for an 80 mm receipt printer (it also prints cleanly on A4) and opens the browser's print dialog from a hidden
 * frame, so the current screen stays as it is. Pick the receipt printer in the dialog; browsers that are set up
 * for silent/kiosk printing print straight away.
 */
import { api } from "@/lib/api/client"
import { roundKhr } from "@/lib/rms/billing"

type Money = string | number
interface DocLine {
  name_en: string
  name_km: string | null
  variant: string | null
  modifiers: string[]
  note: string | null
  quantity: Money
  amount_gross: Money
  amount_discount: Money
  amount_net: Money
  parts: string[]
}
export interface BillDocument {
  kind: "Bill" | "Receipt"
  copy_label: string | null
  restaurant: { name_en: string; name_km: string | null; legal_name: string; tax_id: string | null }
  branch: { name_en: string; name_km: string | null; address: string | null; phone: string | null }
  order: { order_no: string; order_type: string; table: string | null; pickup_name: string | null; guests: number | null; server: string | null; opened_at: string | null }
  bill: { bill_no: string; split: string | null; business_date: string; status: string; printed_count: number }
  receipt: { receipt_no: string; issued_at: string | null } | null
  lines: DocLine[]
  charges: { type: string; name: string; rate: Money | null; amount: Money }[]
  totals: Record<"gross" | "discount" | "subtotal" | "service_charge" | "tax" | "delivery_fee" | "rounding" | "total" | "paid" | "refunded" | "balance", Money> & { currency: string }
  khr_rate: Money | null
  payments: { method: string; currency: string; tendered: Money; applied: Money; change: Money; change_currency: string; card_last4: string | null; reference: string | null; at: string | null }[]
  printed_at: string
  printed_by: string
}

const n = (v: Money | null | undefined) => Number(v ?? 0)
const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!)
const usd = (v: Money) => `$${n(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const riel = (v: number) => `៛${Math.round(v).toLocaleString("en-US")}`
const amt = (v: Money, cur: string) => (cur === "KHR" ? riel(n(v)) : usd(v))
const qty = (v: Money) => String(n(v)).replace(/\.0+$/, "")
const TYPE: Record<string, string> = { DineIn: "Dine-in", Takeaway: "Takeaway", Delivery: "Delivery" }

const row = (l: string, r: string, cls = "") => `<div class="row ${cls}"><span>${l}</span><span>${r}</span></div>`

/** One bill or receipt; several are joined with page breaks by documentsHtml. */
function billBody(d: BillDocument): string {
  const t = d.totals
  const title = d.kind === "Receipt" ? "RECEIPT" : "BILL"
  const where = d.order.table ? `Table ${esc(d.order.table)}` : d.order.pickup_name ? `For ${esc(d.order.pickup_name)}` : ""
  const lines = d.lines
    .map((l) => {
      const name = `${esc(l.name_en)}${l.variant ? ` (${esc(l.variant)})` : ""}`
      const extra = [...l.parts.map((p) => `• ${esc(p)}`), ...(l.modifiers.length ? [esc(l.modifiers.join(", "))] : []), ...(l.note ? [`“${esc(l.note)}”`] : [])]
      return `<div class="item">
        ${row(`${qty(l.quantity)} × ${name}`, usd(l.amount_gross))}
        ${l.name_km ? `<div class="km">${esc(l.name_km)}</div>` : ""}
        ${extra.map((e) => `<div class="sub">${e}</div>`).join("")}
        ${n(l.amount_discount) > 0 ? row("&nbsp;&nbsp;Discount", `−${usd(l.amount_discount)}`, "sub") : ""}
      </div>`
    })
    .join("")
  const lineDiscounts = d.lines.reduce((s, l) => s + n(l.amount_discount), 0)
  const orderDiscount = Math.max(0, n(t.discount) - lineDiscounts)
  const charges = d.charges.map((c) => row(`${esc(c.name)}${c.rate !== null && c.rate !== undefined ? ` ${+(n(c.rate) * 100).toFixed(2)}%` : ""}`, usd(c.amount))).join("")
  const rate = n(d.khr_rate)
  const due = d.kind === "Receipt" ? n(t.total) : n(t.balance)
  const pays = d.payments
    .map(
      (p) =>
        row(`${esc(p.method)}${p.card_last4 ? ` •••• ${esc(p.card_last4)}` : ""}`, amt(p.tendered, p.currency)) +
        (n(p.change) > 0 ? row("Change", amt(p.change, p.change_currency), "sub") : "")
    )
    .join("")
  return `<section class="doc">
  <div class="c">
    <div class="b lg">${esc(d.restaurant.name_en)}</div>
    ${d.restaurant.name_km ? `<div>${esc(d.restaurant.name_km)}</div>` : ""}
    <div>${esc(d.branch.name_en)}</div>
    ${d.branch.address ? `<div class="muted">${esc(d.branch.address)}</div>` : ""}
    ${d.branch.phone ? `<div class="muted">Tel ${esc(d.branch.phone)}</div>` : ""}
    ${d.restaurant.tax_id ? `<div class="muted">Tax ID ${esc(d.restaurant.tax_id)}</div>` : ""}
    <div class="b xl" style="margin-top:6px">${title}</div>
    ${d.copy_label ? `<div class="copy">${esc(d.copy_label)}</div>` : ""}
  </div>
  <hr>
  ${d.receipt ? row("Receipt", `<b>${esc(d.receipt.receipt_no)}</b>`) : ""}
  ${row("Bill", `${esc(d.bill.bill_no)}${d.bill.split ? ` (${esc(d.bill.split)})` : ""}`)}
  ${row("Order", `${esc(d.order.order_no)} · ${esc(TYPE[d.order.order_type] ?? d.order.order_type)}`)}
  ${where ? row(where, d.order.guests ? `${d.order.guests} guests` : "") : ""}
  ${d.order.server ? row("Served by", esc(d.order.server)) : ""}
  ${row("Date", esc(d.receipt?.issued_at ?? d.printed_at))}
  <hr>
  ${lines}
  <hr>
  ${row("Subtotal", usd(t.gross))}
  ${orderDiscount > 0 || lineDiscounts > 0 ? row("Discounts", `−${usd(t.discount)}`) : ""}
  ${charges}
  ${n(t.delivery_fee) > 0 ? row("Delivery", usd(t.delivery_fee)) : ""}
  ${n(t.rounding) !== 0 ? row("Rounding", usd(t.rounding)) : ""}
  ${row("TOTAL", usd(t.total), "total")}
  ${rate ? row("Total in riel", riel(roundKhr(n(t.total) * rate))) : ""}
  ${rate ? `<div class="sub" style="padding:0">Rate 1 USD = ${riel(rate)}</div>` : ""}
  ${
    d.kind === "Receipt"
      ? `<hr>${pays}${n(t.refunded) > 0 ? row("Refunded", `−${usd(t.refunded)}`) : ""}${row("Paid", usd(t.paid), "b")}`
      : `<hr>${n(t.paid) > 0 ? row("Paid so far", usd(t.paid)) : ""}${row("Amount due", usd(due), "b")}${rate ? row("", riel(roundKhr(due * rate))) : ""}`
  }
  <hr>
  <div class="c">
    <div class="b">${d.kind === "Receipt" ? "Thank you! · អរគុណ!" : "Please pay at the counter or ask your server."}</div>
    <div class="sub" style="padding:0">Printed ${esc(d.printed_at)} by ${esc(d.printed_by)}</div>
  </div>
</section>`
}

const STYLE = `
  @page { size: 80mm auto; margin: 3mm; }
  * { box-sizing: border-box; }
  body { margin: 0 auto; width: 74mm; max-width: 100%; color: #000; background: #fff;
         font: 12px/1.35 "Segoe UI", "Khmer UI", "Noto Sans Khmer", "Khmer OS", system-ui, sans-serif; }
  .doc + .doc { break-before: page; }
  .c { text-align: center; } .b { font-weight: 700; } .muted { color: #333; } .lg { font-size: 15px; } .xl { font-size: 18px; }
  .row { display: flex; justify-content: space-between; gap: 8px; } .row span:last-child { white-space: nowrap; font-variant-numeric: tabular-nums; }
  .item { margin: 4px 0; } .sub, .km { font-size: 11px; padding-left: 12px; color: #333; }
  hr { border: 0; border-top: 1px dashed #000; margin: 6px 0; }
  .copy { border: 2px solid #000; padding: 2px; margin: 4px 0; font-weight: 700; letter-spacing: 2px; }
  .total { font-size: 16px; font-weight: 700; margin-top: 2px; }`

export function documentsHtml(docs: BillDocument[]): string {
  const first = docs[0]
  const title = first ? `${first.kind} ${first.receipt?.receipt_no ?? first.bill.bill_no}` : "Print"
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>${STYLE}</style></head><body>${docs.map(billBody).join("")}</body></html>`
}

/** Opens the print dialog for the HTML without leaving the page. */
export function printHtml(html: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const frame = document.createElement("iframe")
    frame.setAttribute("aria-hidden", "true")
    frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden"
    document.body.appendChild(frame)
    const win = frame.contentWindow
    if (!win) {
      frame.remove()
      return reject(new Error("The browser blocked printing."))
    }
    const cleanup = () => setTimeout(() => frame.remove(), 1000)
    win.addEventListener("afterprint", cleanup, { once: true })
    win.document.open()
    win.document.write(html)
    win.document.close()
    // Let fonts and layout settle before printing
    const go = () => {
      try {
        win.focus()
        win.print()
        resolve()
      } catch (e) {
        reject(e)
      } finally {
        setTimeout(() => frame.isConnected && frame.remove(), 60_000)
      }
    }
    if (win.document.fonts?.ready) void win.document.fonts.ready.then(() => setTimeout(go, 50))
    else setTimeout(go, 200)
  })
}

export const billDocument = (billId: string) => api<BillDocument>("GET", `/bills/${billId}/document`)

export async function printBillDocuments(billIds: string[]) {
  if (!billIds.length) throw new Error("There is nothing to print yet.")
  const docs = await Promise.all(billIds.map(billDocument))
  await printHtml(documentsHtml(docs))
  return docs
}

/**
 * Receipts of an order (one per paid bill when the bill was split). With `copy`, each reprint is recorded first so
 * the paper says COPY n (BR-049); the first print after payment is the original.
 */
export async function printOrderReceipts(orderId: string, copy = false) {
  const bills = await api<{ id: string; receipt_no: string | null; status: string }[]>("GET", `/orders/${orderId}/bills`)
  const paid = bills.filter((b) => b.receipt_no)
  if (!paid.length) throw new Error("This order has no receipt yet. Take the payment first.")
  if (copy) for (const b of paid) await api("POST", `/bills/${b.id}/receipt/reprint`)
  return printBillDocuments(paid.map((b) => b.id))
}
