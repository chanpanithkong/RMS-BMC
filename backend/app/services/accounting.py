"""Accounting export: one balanced journal per branch and business day, as a Xero manual-journal CSV (owner's choice).

Sign convention (Xero manual journals): debits positive, credits negative; every journal sums to zero.
Xero manual journals can't post to bank, receivable, payable or other system accounts, so money in and out goes to
clearing accounts that the accountant settles in Xero (bank reconciliation, bills).

Per day:
* Sales from finalised bills (as RPT-01): sales (by menu category when mapped) Cr, discounts Dr, service charge Cr,
  tax payable Cr, delivery fees Cr.
* Payments by method Dr (clearing accounts), KHR cash rounding Cr, and the difference between what was billed and
  what was applied to bills Dr/Cr "unpaid and prepaid bills clearing".
* Refunds Dr, paid out of the refund method's clearing account.
* Cash over/short from closed cashier sessions (KHR converted at the current rate).
* Delivery-platform commissions Dr, reducing the platform receivable.
* Stock: cost of sales, wastage, count and manual adjustments, issues, receipts (against goods received not invoiced),
  returns, opening stock and inter-branch transfers, each against inventory at weighted average cost.
* Expenses (approved or paid, by expense date) against expenses payable; their payments; supplier invoices against
  goods received not invoiced and supplier payments against the supplier clearing account.
"""
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict
from app.models import (Bill, BillLine, CashierSession, Expense, ExpenseCategory, InventoryTransaction, Order, OrderItem, Payment, PlatformOrder, Refund,
                        SupplierInvoice, SupplierPayment)
from app.services.platform import audit, get_setting
from app.utils.money import ZERO, q
from app.utils.timeutil import business_date_for

# Placeholder chart (labelled as such). The accountant replaces the codes in settings before the first export.
DEFAULT_ACCOUNTS = {
    "sales": ("4000", "Food and beverage sales"), "discounts": ("4900", "Discounts given"), "refunds": ("4910", "Sales refunds"),
    "service_charge": ("4100", "Service charge income"), "delivery_fees": ("4200", "Delivery fee income"), "rounding": ("4950", "Cash rounding"),
    "tax_payable": ("2200", "Tax payable"), "unpaid_bills": ("1150", "Unpaid and prepaid bills clearing"), "cash_over_short": ("6950", "Cash over and short"),
    "platform_commission": ("6400", "Delivery platform commissions"), "cogs": ("5000", "Cost of goods sold"), "wastage": ("5100", "Wastage"),
    "stock_adjustments": ("5200", "Stock adjustments and count variances"), "stock_issues": ("5300", "Stock issued for use"), "inventory": ("1300", "Inventory"),
    "grni": ("2150", "Goods received not invoiced"), "opening_stock": ("3900", "Opening stock clearing"), "inter_branch": ("1390", "Inter-branch stock in transit"),
    "ap_clearing": ("2160", "Supplier invoices clearing"), "expenses_default": ("6000", "Operating expenses"), "expenses_payable": ("2170", "Expenses payable clearing"),
    "suspense": ("9999", "Suspense (export difference)"),
}
DEFAULT_METHODS = {
    "CASH_USD": ("1010", "Cash clearing"), "CASH_KHR": ("1010", "Cash clearing"), "CASH_DRAWER": ("1010", "Cash clearing"), "CASH": ("1010", "Cash clearing"),
    "KHQR": ("1020", "KHQR clearing"), "BANK_TRANSFER": ("1030", "Bank transfer clearing"), "CHEQUE": ("1030", "Bank transfer clearing"),
    "OTHER": ("1030", "Bank transfer clearing"), "CARD": ("1040", "Card clearing"), "ONLINE": ("1050", "Online payments clearing"),
    "PLATFORM": ("1160", "Delivery platform receivable"), "ON_ACCOUNT": ("1170", "Customer credit accounts receivable"),
}
INVENTORY_COUNTER = {"SALE_CONSUMPTION": "cogs", "SALE_REVERSAL": "cogs", "WASTE": "wastage", "COUNT_ADJUSTMENT": "stock_adjustments", "ADJUSTMENT": "stock_adjustments",
                     "REVERSAL": "stock_adjustments", "ISSUE": "stock_issues", "RECEIPT": "grni", "RETURN_TO_SUPPLIER": "grni", "OPENING": "opening_stock"}
XERO_MAX_LINES = 300


def settings(ctx: Ctx) -> dict:
    return get_setting(ctx.db, "accounting", ctx.branch_id)


def mapping(ctx: Ctx) -> dict:
    s = settings(ctx)
    acc = {k: {"code": (s.get("accounts") or {}).get(k, v[0]), "name": v[1], "placeholder": k not in (s.get("accounts") or {})} for k, v in DEFAULT_ACCOUNTS.items()}
    meth = {k: {"code": (s.get("method_accounts") or {}).get(k, v[0]), "name": v[1], "placeholder": k not in (s.get("method_accounts") or {})} for k, v in DEFAULT_METHODS.items()}
    return {"accounts": acc, "method_accounts": meth, "category_accounts": s.get("category_accounts") or {},
            "expense_category_accounts": s.get("expense_category_accounts") or {}, "tax_rate_name": s.get("tax_rate_name"), "date_format": s.get("date_format"),
            "tracking_name": s.get("tracking_name"), "mapping_confirmed": bool(s.get("mapping_confirmed"))}


class _Journal:
    def __init__(self, m: dict):
        self.m = m
        self.lines: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)

    def add(self, key: str, amount: Decimal, description: str, method: str | None = None, code: str | None = None) -> None:
        if not amount:
            return
        if code is None:
            code = self.m["method_accounts"].get(method, self.m["method_accounts"]["OTHER"])["code"] if method else self.m["accounts"][key]["code"]
        self.lines[(code, description)] += amount

    def out(self) -> list[dict]:
        return [{"account_code": c, "description": d, "amount": q(a)} for (c, d), a in sorted(self.lines.items()) if q(a) != 0]


def _bdate(ctx: Ctx, ts: datetime | None) -> date | None:
    return business_date_for(ts, ctx.branch.timezone, ctx.branch.day_end_time) if ts else None


def build(ctx: Ctx, start: date, end: date) -> list[dict]:
    if (end - start).days > 92:
        raise BusinessRuleError("RANGE_TOO_LONG", "Export at most 3 months at a time.")
    m = mapping(ctx)
    s = settings(ctx)
    db, b = ctx.db, ctx.branch_id
    days: dict[date, _Journal] = defaultdict(lambda: _Journal(m))

    # --- sales from finalised bills (RPT-01 basis)
    bills = db.execute(select(Bill.business_date, func.sum(Bill.gross_total), func.sum(Bill.discount_total), func.sum(Bill.service_charge_total), func.sum(Bill.tax_total),
                              func.sum(Bill.delivery_fee), func.sum(Bill.rounding_total), func.sum(Bill.total))
                       .where(Bill.branch_id == b, Bill.status.in_(("Paid", "Refunded")), Bill.business_date.between(start, end)).group_by(Bill.business_date)).all()
    cat_map = m["category_accounts"]
    for d, gross, disc, svc, tax, fee, rnd, total in bills:
        j = days[d]
        rest = gross
        if cat_map:
            for cat, amt in db.execute(select(OrderItem.category_name_snapshot, func.sum(BillLine.amount_gross)).join(OrderItem, OrderItem.id == BillLine.order_item_id)
                                       .join(Bill, Bill.id == BillLine.bill_id).where(Bill.branch_id == b, Bill.status.in_(("Paid", "Refunded")), Bill.business_date == d)
                                       .group_by(OrderItem.category_name_snapshot)):
                if cat in cat_map:
                    j.add("sales", -q(amt), f"Sales: {cat}", code=cat_map[cat])
                    rest -= q(amt)
        j.add("sales", -rest, "Sales")
        j.add("discounts", disc, "Discounts")
        j.add("service_charge", -svc, "Service charge")
        j.add("tax_payable", -tax, "Tax on sales")
        j.add("delivery_fees", -fee, "Delivery fees")
        j.add("rounding", -rnd, "Bill rounding")
        j.add("unpaid_bills", total, "Bills finalised")

    # --- payments received (clearing by method), KHR rounding, applied to bills
    for d, method, base, rounding in db.execute(select(Payment.business_date, Payment.method_code, func.sum(Payment.amount_base), func.sum(Payment.rounding_base))
                                                .where(Payment.branch_id == b, Payment.status == "Confirmed", Payment.business_date.between(start, end))
                                                .group_by(Payment.business_date, Payment.method_code)):
        j = days[d]
        j.add("", base, f"Payments: {method}", method=method)
        j.add("rounding", -rounding, "Cash rounding")
        j.add("unpaid_bills", -(base - rounding), "Payments applied to bills")

    # --- customer credit account settlements (charges arrive as ON_ACCOUNT payments above)
    from app.models import CreditTransaction

    for d, method, amt in db.execute(select(CreditTransaction.business_date, CreditTransaction.method_code, func.sum(CreditTransaction.amount)).where(
            CreditTransaction.branch_id == b, CreditTransaction.kind == "Settlement", CreditTransaction.business_date.between(start, end))
            .group_by(CreditTransaction.business_date, CreditTransaction.method_code)):
        days[d].add("", -amt, f"Account settlements: {method}", method=method)
        days[d].add("", amt, "Account settlements", method="ON_ACCOUNT")

    # --- refunds
    for d, method, amt in db.execute(select(Refund.business_date, Refund.method_code, func.sum(Refund.amount_base)).where(
            Refund.branch_id == b, Refund.status == "Completed", Refund.business_date.between(start, end)).group_by(Refund.business_date, Refund.method_code)):
        days[d].add("refunds", amt, "Refunds")
        days[d].add("", -amt, f"Refunds paid: {method}", method=method)

    # --- cash over/short from closed sessions
    from app.services.billing import current_rate

    rate = current_rate(db, "KHR")
    for sess in db.scalars(select(CashierSession).where(CashierSession.branch_id == b, CashierSession.status == "Closed", CashierSession.business_date.between(start, end))):
        var = ZERO
        for r in sess.results:
            if r.currency == "USD":
                var += r.variance
            elif r.currency == "KHR" and rate is not None and r.variance:
                var += q(r.variance / rate.rate)
        days[sess.business_date].add("", var, "Cash count difference", method="CASH_USD")
        days[sess.business_date].add("cash_over_short", -var, "Cash over/short")

    # --- delivery platform commissions (a cost, BR-044)
    for d, amt in db.execute(select(Order.business_date, func.sum(PlatformOrder.commission_amount)).join(Order, Order.id == PlatformOrder.order_id).where(
            PlatformOrder.branch_id == b, Order.order_status != "Cancelled", Order.business_date.between(start, end)).group_by(Order.business_date)):
        days[d].add("platform_commission", amt, "Platform commissions")
        days[d].add("", -amt, "Platform commissions deducted", method="PLATFORM")

    # --- stock movements at weighted average cost
    if s.get("include_inventory", True):
        for d, t, src, cost in db.execute(select(InventoryTransaction.business_date, InventoryTransaction.txn_type, InventoryTransaction.source_type,
                                                 func.sum(InventoryTransaction.total_cost)).where(InventoryTransaction.branch_id == b,
                                                                                                   InventoryTransaction.business_date.between(start, end))
                                          .group_by(InventoryTransaction.business_date, InventoryTransaction.txn_type, InventoryTransaction.source_type)):
            if t in ("TRANSFER_IN", "TRANSFER_OUT"):
                if src != "InterBranchTransfer":
                    continue  # moves between this branch's own locations net to zero
                counter = "inter_branch"
            else:
                counter = INVENTORY_COUNTER.get(t, "stock_adjustments")
            label = t.replace("_", " ").title()
            days[d].add("inventory", cost, f"Inventory: {label}")
            days[d].add(counter, -cost, label)

    # --- expenses (by expense date) and their payments (by payment date)
    if s.get("include_expenses", True):
        exp_map = m["expense_category_accounts"]
        rows = db.execute(select(Expense, ExpenseCategory.name_en).join(ExpenseCategory, ExpenseCategory.id == Expense.category_id).where(
            Expense.branch_id == b, Expense.status.in_(("Approved", "Paid")), Expense.expense_date.between(start - timedelta(days=31), end + timedelta(days=1)))).all()
        for e, cat in rows:
            if start <= e.expense_date <= end:
                days[e.expense_date].add("expenses_default", e.amount_base, f"Expense: {cat}", code=exp_map.get(cat))
                days[e.expense_date].add("expenses_payable", -e.amount_base, "Expenses incurred")
            pd = _bdate(ctx, e.paid_at)
            if e.status == "Paid" and pd and start <= pd <= end:
                days[pd].add("expenses_payable", e.amount_base, "Expenses paid")
                days[pd].add("", -e.amount_base, f"Expenses paid: {e.payment_method}", method=e.payment_method)

    # --- supplier invoices and payments
    if s.get("include_purchasing", True):
        for d, amt in db.execute(select(SupplierInvoice.invoice_date, func.sum(SupplierInvoice.amount)).where(SupplierInvoice.branch_id == b,
                                                                                                             SupplierInvoice.invoice_date.between(start, end))
                                 .group_by(SupplierInvoice.invoice_date)):
            days[d].add("grni", amt, "Supplier invoices")
            days[d].add("ap_clearing", -amt, "Supplier invoices")
        for p in db.scalars(select(SupplierPayment).join(SupplierInvoice, SupplierInvoice.id == SupplierPayment.invoice_id).where(SupplierInvoice.branch_id == b)):
            pd = _bdate(ctx, p.paid_at)
            if pd and start <= pd <= end:
                days[pd].add("ap_clearing", p.amount, "Supplier payments")
                days[pd].add("", -p.amount, f"Supplier payments: {p.method}", method=p.method)

    out = []
    for d in sorted(days):
        j = days[d]
        diff = q(sum(j.lines.values(), ZERO))
        warnings = []
        if diff:
            j.add("suspense", -diff, "Export difference (check)")
            warnings.append(f"Lines didn't balance by {diff}; the difference is on the suspense account.")
        lines = j.out()
        if len(lines) > XERO_MAX_LINES:
            warnings.append(f"{len(lines)} lines; Xero imports at most {XERO_MAX_LINES} per journal.")
        if not lines:
            continue
        out.append({"date": d, "branch": ctx.branch.code, "narration": f"RMS {ctx.branch.code} daily summary {d.isoformat()}", "lines": lines,
                    "debits": sum((x["amount"] for x in lines if x["amount"] > 0), ZERO), "credits": -sum((x["amount"] for x in lines if x["amount"] < 0), ZERO),
                    "warnings": warnings})
    return out


def xero_csv(ctx: Ctx, journals: list[dict]) -> str:
    """Xero manual journal import: Narration and Date on the first line of each journal; debits positive, credits negative."""
    m = mapping(ctx)
    if not m["mapping_confirmed"]:
        raise Conflict("MAPPING_NOT_CONFIRMED", "Confirm the account mapping (accounting settings) before exporting to Xero; placeholder codes are still in use.")
    fmt, tax, tracking = m["date_format"] or "%Y-%m-%d", m["tax_rate_name"] or "Tax Exempt", m["tracking_name"] or ""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["*Narration", "*Date", "Description", "*AccountCode", "*TaxRate", "*Amount", "TrackingName1", "TrackingOption1"])
    for jn in journals:
        for i, ln in enumerate(jn["lines"]):
            w.writerow([jn["narration"] if i == 0 else "", jn["date"].strftime(fmt) if i == 0 else "", ln["description"], ln["account_code"], tax, f"{ln['amount']:.2f}",
                        tracking if tracking else "", jn["branch"] if tracking else ""])
    audit(ctx.db, ctx, "accounting.export", "Branch", ctx.branch_id, after={"journals": len(journals), "from": journals[0]["date"] if journals else None,
                                                                           "to": journals[-1]["date"] if journals else None, "format": "xero"})
    return buf.getvalue()
