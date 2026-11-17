"""Phase 2 reports (SRS §11.3): RPT-05, 08, 09, 10, 15, 16, 19, 20, 21, 22, 23, 25, 26, and dashboard trend/cost widgets.

Every function returns (rows, summary) from posted records and order-time snapshots. Net sales per order use the
order's discounted subtotal (BR-008 step 5) for completed orders; the branch-level net sales in RPT-01 also deduct refunds.
"""
import math
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError
from app.models import (AuditLog, Customer, DiningArea, Expense, ExpenseCategory, GoodsReceipt, GoodsReceiptItem, Ingredient, InventoryTransaction, MenuItem,
                        Order, OrderDiscount, OrderItem, Payment, PurchaseOrder, PurchaseOrderItem, RestaurantTable, StockBalance, Supplier, SupplierInvoice,
                        SupplierPayment, User)
from app.services.platform import get_setting
from app.utils.money import ZERO, q

HUNDRED = Decimal(100)
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _names(ctx: Ctx, ids) -> dict:
    ids = [i for i in set(ids) if i]
    return dict(ctx.db.execute(select(User.id, User.full_name).where(User.id.in_(ids or [None]))).all())


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return q(Decimal(part) * HUNDRED / whole) if whole else ZERO


def _minutes(a: datetime | None, b: datetime | None) -> float | None:
    return (b - a).total_seconds() / 60 if a and b and b >= a else None


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[max(math.ceil(0.9 * len(s)) - 1, 0)]  # nearest-rank


def _r1(v: float | None) -> Decimal | None:
    return Decimal(str(round(v, 1))) if v is not None else None


def _completed(ctx: Ctx, start: date, end: date):
    return and_(Order.branch_id == ctx.branch_id, Order.order_status == "Completed", Order.business_date.between(start, end))


def _period_days(start: date, end: date) -> int:
    return (end - start).days + 1


# ---------------------------------------------------------------- RPT-05 sales by employee
def rpt05(ctx: Ctx, start: date, end: date, f: dict):
    db = ctx.db
    stmt = select(Order.server_user_id, func.count(), func.coalesce(func.sum(Order.guest_count), 0), func.sum(Order.subtotal), func.sum(Order.discount_total)).where(
        _completed(ctx, start, end)).group_by(Order.server_user_id)
    if f.get("user_id"):
        stmt = stmt.where(Order.server_user_id == f["user_id"])
    servers = db.execute(stmt).all()
    voids = dict(db.execute(select(OrderItem.added_by, func.count()).join(Order).where(Order.branch_id == ctx.branch_id, Order.business_date.between(start, end),
                                                                                      OrderItem.item_status == "Cancelled", OrderItem.void_type.is_not(None))
                            .group_by(OrderItem.added_by)).all())
    cash = db.execute(select(Payment.received_by, func.count(), func.sum(Payment.amount_base)).where(Payment.branch_id == ctx.branch_id, Payment.status == "Confirmed",
                                                                                                    Payment.business_date.between(start, end)).group_by(Payment.received_by)).all()
    names = _names(ctx, [s[0] for s in servers] + [c[0] for c in cash] + list(voids))
    rows = [{"role": "Server", "user_id": u, "employee": names.get(u), "orders": n, "covers": covers, "net_sales": q(net), "average_order_value": q(net / n) if n else ZERO,
             "discounts": q(disc), "voided_items": voids.get(u, 0)} for u, n, covers, net, disc in servers]
    rows += [{"role": "Cashier", "user_id": u, "employee": names.get(u), "payments": n, "collected_base": q(amt)} for u, n, amt in cash
             if not f.get("user_id") or str(u) == str(f["user_id"])]
    return rows, {"note": "Server figures by order server; cashier figures by the user who received each payment."}


# ---------------------------------------------------------------- RPT-08 order volume and AOV
def rpt08(ctx: Ctx, start: date, end: date, f: dict):
    data = ctx.db.execute(select(Order.order_type, Order.channel, func.count(), func.sum(Order.subtotal), func.coalesce(func.sum(Order.guest_count), 0))
                          .where(_completed(ctx, start, end)).group_by(Order.order_type, Order.channel).order_by(Order.order_type, Order.channel)).all()
    rows = [{"order_type": t, "channel": ch, "orders": n, "net_sales": q(net), "average_order_value": q(net / n) if n else ZERO, "covers": cov,
             "spend_per_cover": q(net / cov) if cov else None} for t, ch, n, net, cov in data]
    n = sum(r["orders"] for r in rows)
    net = sum((r["net_sales"] for r in rows), ZERO)
    return rows, {"orders": n, "net_sales": net, "average_order_value": q(net / n) if n else ZERO, "orders_per_day": q(Decimal(n) / _period_days(start, end))}


# ---------------------------------------------------------------- RPT-09 peak hours
def rpt09(ctx: Ctx, start: date, end: date, f: dict):
    tz = ZoneInfo(ctx.branch.timezone)
    orders = ctx.db.execute(select(Order.id, Order.created_at, Order.subtotal).where(_completed(ctx, start, end))).all()
    prep = defaultdict(list)
    for oid, sent, ready in ctx.db.execute(select(OrderItem.order_id, OrderItem.sent_at, OrderItem.ready_at).join(Order).where(_completed(ctx, start, end))):
        m = _minutes(sent, ready)
        if m is not None:
            prep[oid].append(m)
    cells: dict = defaultdict(lambda: {"orders": 0, "net_sales": ZERO, "prep": []})
    for oid, created, net in orders:
        local = created.astimezone(tz)
        c = cells[(local.weekday(), local.hour)]
        c["orders"] += 1
        c["net_sales"] += net
        c["prep"] += prep.get(oid, [])
    rows = [{"day_of_week": DAYS[d], "hour": h, "orders": c["orders"], "net_sales": q(c["net_sales"]),
             "avg_prep_minutes": _r1(sum(c["prep"]) / len(c["prep"])) if c["prep"] else None} for (d, h), c in sorted(cells.items())]
    by_hour: dict = defaultdict(int)
    for r in rows:
        by_hour[r["hour"]] += r["orders"]
    peak = max(by_hour.items(), key=lambda kv: kv[1]) if by_hour else None
    return rows, {"peak_hour": peak[0] if peak else None, "peak_hour_orders": peak[1] if peak else 0, "timezone": ctx.branch.timezone}


# ---------------------------------------------------------------- RPT-10 table turnover
def rpt10(ctx: Ctx, start: date, end: date, f: dict):
    data = ctx.db.execute(select(RestaurantTable.table_code, DiningArea.name, RestaurantTable.capacity, Order.guest_count, Order.created_at, Order.completed_at)
                          .join(RestaurantTable, RestaurantTable.id == Order.table_id).join(DiningArea, DiningArea.id == RestaurantTable.dining_area_id)
                          .where(_completed(ctx, start, end), Order.order_type == "DineIn")).all()
    per: dict = defaultdict(lambda: {"seatings": 0, "covers": 0, "minutes": []})
    for code, area, cap, guests, created, done in data:
        p = per[(area, code, cap)]
        p["seatings"] += 1
        p["covers"] += guests or 0
        m = _minutes(created, done)
        if m is not None:
            p["minutes"].append(m)
    days = _period_days(start, end)
    rows = [{"area": a, "table": t, "capacity": cap, "seatings": p["seatings"], "covers": p["covers"],
             "avg_dining_minutes": _r1(sum(p["minutes"]) / len(p["minutes"])) if p["minutes"] else None, "turns_per_day": q(Decimal(p["seatings"]) / days)}
            for (a, t, cap), p in sorted(per.items())]
    return rows, {"seatings": sum(r["seatings"] for r in rows), "covers": sum(r["covers"] for r in rows),
                  "note": "Dining time runs from order creation to order completion."}


# ---------------------------------------------------------------- RPT-15 kitchen preparation time
def rpt15(ctx: Ctx, start: date, end: date, f: dict):
    late = float(get_setting(ctx.db, "kitchen", ctx.branch_id).get("late_ticket_minutes", 15))
    tz = ZoneInfo(ctx.branch.timezone)
    stmt = select(OrderItem.station_code, OrderItem.item_name_en_snapshot, OrderItem.sent_at, OrderItem.ready_at).join(Order).where(
        Order.branch_id == ctx.branch_id, Order.business_date.between(start, end), OrderItem.sent_at.is_not(None), OrderItem.ready_at.is_not(None))
    if f.get("station_code"):
        stmt = stmt.where(OrderItem.station_code == f["station_code"])
    groups = {"station": defaultdict(list), "item": defaultdict(list), "hour": defaultdict(list)}
    for station, item, sent, ready in ctx.db.execute(stmt):
        m = _minutes(sent, ready)
        if m is None:
            continue
        groups["station"][station].append(m)
        groups["item"][(station, item)].append(m)
        groups["hour"][sent.astimezone(tz).hour].append(m)

    def stats(v):
        return {"items": len(v), "avg_minutes": _r1(sum(v) / len(v)), "p90_minutes": _r1(_p90(v)), "late_items": sum(1 for x in v if x > late)}

    rows = [{"station_code": s, **stats(v)} for s, v in sorted(groups["station"].items(), key=lambda kv: str(kv[0]))]
    return rows, {"late_threshold_minutes": late, "by_item": [{"station_code": s, "item": i, **stats(v)} for (s, i), v in sorted(groups["item"].items(), key=lambda kv: str(kv[0]))],
                  "by_hour": [{"hour": h, **stats(v)} for h, v in sorted(groups["hour"].items())],
                  "note": "Preparation time is Sent to Ready per item. The late threshold is the kitchen setting late_ticket_minutes."}


# ---------------------------------------------------------------- RPT-16 consumption and variance
def rpt16(ctx: Ctx, start: date, end: date, f: dict):
    kinds = ("SALE_CONSUMPTION", "SALE_REVERSAL", "WASTE", "COUNT_ADJUSTMENT")
    stmt = select(Ingredient.code, Ingredient.name_en, Ingredient.category, InventoryTransaction.txn_type, func.sum(InventoryTransaction.quantity),
                  func.sum(InventoryTransaction.total_cost)).join(Ingredient, Ingredient.id == InventoryTransaction.ingredient_id).where(
        InventoryTransaction.branch_id == ctx.branch_id, InventoryTransaction.business_date.between(start, end), InventoryTransaction.txn_type.in_(kinds)).group_by(
        Ingredient.code, Ingredient.name_en, Ingredient.category, InventoryTransaction.txn_type)
    if f.get("category"):
        stmt = stmt.where(Ingredient.category == f["category"])
    per: dict = defaultdict(lambda: {k: [ZERO, ZERO] for k in kinds})
    meta = {}
    for code, name, cat, t, qty, cost in ctx.db.execute(stmt):
        per[code][t] = [qty or ZERO, cost or ZERO]
        meta[code] = (name, cat)
    rows = []
    for code, v in sorted(per.items()):
        theo_q = -(v["SALE_CONSUMPTION"][0] + v["SALE_REVERSAL"][0])
        theo_v = -(v["SALE_CONSUMPTION"][1] + v["SALE_REVERSAL"][1])
        waste_q, waste_v = -v["WASTE"][0], -v["WASTE"][1]
        var_q, var_v = v["COUNT_ADJUSTMENT"]
        rows.append({"code": code, "ingredient": meta[code][0], "category": meta[code][1], "theoretical_qty": theo_q, "theoretical_value": q(theo_v), "wastage_qty": waste_q,
                     "wastage_value": q(waste_v), "count_variance_qty": var_q, "count_variance_value": q(var_v), "actual_usage_qty": theo_q + waste_q - var_q,
                     "actual_usage_value": q(theo_v + waste_v - var_v)})
    return rows, {"theoretical_value": sum((r["theoretical_value"] for r in rows), ZERO), "actual_usage_value": sum((r["actual_usage_value"] for r in rows), ZERO),
                  "note": "Actual usage = theoretical (recipes) + wastage − count adjustments. Choose a period that starts and ends on stock counts."}


# ---------------------------------------------------------------- RPT-19 wastage
def rpt19(ctx: Ctx, start: date, end: date, f: dict):
    data = ctx.db.execute(select(InventoryTransaction, Ingredient.name_en, Ingredient.code).join(Ingredient, Ingredient.id == InventoryTransaction.ingredient_id).where(
        InventoryTransaction.branch_id == ctx.branch_id, InventoryTransaction.business_date.between(start, end), InventoryTransaction.txn_type == "WASTE")
        .order_by(InventoryTransaction.posted_at)).all()
    names = _names(ctx, [t.posted_by for t, *_ in data])
    rows = [{"business_date": t.business_date, "code": code, "ingredient": name, "quantity": -t.quantity, "value": q(-(t.total_cost or ZERO)), "reason": t.reason,
             "source": t.source_type, "posted_by": names.get(t.posted_by)} for t, name, code in data]
    by_reason: dict = defaultdict(lambda: ZERO)
    for r in rows:
        by_reason[r["reason"] or "—"] += r["value"]
    return rows, {"total_value": sum((r["value"] for r in rows), ZERO), "by_reason": [{"reason": k, "value": v} for k, v in sorted(by_reason.items(), key=lambda kv: -kv[1])]}


# ---------------------------------------------------------------- RPT-20 purchases
def _gr_lines(ctx: Ctx, start: date, end: date, supplier_id=None):
    stmt = select(GoodsReceipt, GoodsReceiptItem, PurchaseOrderItem).join(GoodsReceiptItem, GoodsReceiptItem.gr_id == GoodsReceipt.id).outerjoin(
        PurchaseOrderItem, PurchaseOrderItem.id == GoodsReceiptItem.po_item_id).where(GoodsReceipt.branch_id == ctx.branch_id, GoodsReceipt.status == "Posted",
                                                                                     func.date(GoodsReceipt.posted_at).between(start, end))
    if supplier_id:
        stmt = stmt.where(GoodsReceipt.supplier_id == supplier_id)
    return ctx.db.execute(stmt).all()


def rpt20(ctx: Ctx, start: date, end: date, f: dict):
    po_stmt = select(PurchaseOrder.supplier_id, func.count(), func.sum(PurchaseOrder.total)).where(
        PurchaseOrder.branch_id == ctx.branch_id, func.date(PurchaseOrder.created_at).between(start, end), PurchaseOrder.status != "Cancelled").group_by(PurchaseOrder.supplier_id)
    pos = {s: (n, t) for s, n, t in ctx.db.execute(po_stmt)}
    per: dict = defaultdict(lambda: {"receipts": set(), "received_value": ZERO, "price_variance": ZERO})
    items: dict = defaultdict(lambda: {"qty": ZERO, "value": ZERO, "variance": ZERO})
    for gr, ln, pi in _gr_lines(ctx, start, end, f.get("supplier_id")):
        accepted = ln.qty_received - ln.qty_rejected
        value = accepted * ln.unit_cost
        var = (ln.unit_cost - pi.unit_price) * accepted if pi else ZERO
        p = per[gr.supplier_id]
        p["receipts"].add(gr.id)
        p["received_value"] += value
        p["price_variance"] += var
        it = items[(gr.supplier_id, ln.ingredient_id)]
        it["qty"] += accepted
        it["value"] += value
        it["variance"] += var
    sids = set(pos) | set(per)
    if f.get("supplier_id"):
        sids &= {uuid.UUID(str(f["supplier_id"]))}
    sup = dict(ctx.db.execute(select(Supplier.id, Supplier.name).where(Supplier.id.in_(sids or [None]))).all())
    ing = dict(ctx.db.execute(select(Ingredient.id, Ingredient.name_en).where(Ingredient.id.in_({k[1] for k in items} or [None]))).all())
    rows = [{"supplier": sup.get(s), "supplier_id": s, "purchase_orders": pos.get(s, (0, ZERO))[0], "ordered_value": q(pos.get(s, (0, ZERO))[1] or ZERO),
             "receipts": len(per[s]["receipts"]) if s in per else 0, "received_value": q(per[s]["received_value"]) if s in per else ZERO,
             "price_variance": q(per[s]["price_variance"]) if s in per else ZERO} for s in sorted(sids, key=lambda x: sup.get(x) or "")]
    return rows, {"received_value": sum((r["received_value"] for r in rows), ZERO), "price_variance": sum((r["price_variance"] for r in rows), ZERO),
                  "by_item": [{"supplier": sup.get(s), "ingredient": ing.get(i), "quantity": v["qty"], "value": q(v["value"]), "price_variance": q(v["variance"])}
                              for (s, i), v in items.items()],
                  "note": "Price variance = (received unit cost − PO unit price) × accepted quantity."}


# ---------------------------------------------------------------- RPT-21 supplier performance and balances
def rpt21(ctx: Ctx, start: date, end: date, f: dict):
    from app.services import purchasing

    tol = Decimal(str(get_setting(ctx.db, "purchasing", ctx.branch_id)["receipt_tolerance_pct"])) / HUNDRED
    stmt = select(Supplier).order_by(Supplier.name)
    if f.get("supplier_id"):
        stmt = stmt.where(Supplier.id == f["supplier_id"])
    lines = _gr_lines(ctx, start, end, f.get("supplier_id"))
    rows = []
    for s in ctx.db.scalars(stmt):
        mine = [x for x in lines if x[0].supplier_id == s.id]
        grs = {gr.id: gr for gr, _, _ in mine}
        po_ids = {gr.po_id for gr in grs.values() if gr.po_id}
        pos = {p.id: p for p in ctx.db.scalars(select(PurchaseOrder).where(PurchaseOrder.id.in_(po_ids or [None])))}
        dated = [gr for gr in grs.values() if gr.po_id and pos[gr.po_id].delivery_date]
        on_time = sum(1 for gr in dated if gr.posted_at.date() <= pos[gr.po_id].delivery_date)
        po_lines = [(ln, pi) for _, ln, pi in mine if pi]
        accurate = sum(1 for ln, pi in po_lines if abs(ln.qty_received - pi.qty_ordered) <= pi.qty_ordered * tol)
        inv = ctx.db.execute(select(func.count(), func.coalesce(func.sum(SupplierInvoice.amount), 0)).where(
            SupplierInvoice.supplier_id == s.id, SupplierInvoice.branch_id == ctx.branch_id, SupplierInvoice.invoice_date.between(start, end))).one()
        paid = ctx.db.scalar(select(func.coalesce(func.sum(SupplierPayment.amount), 0)).join(SupplierInvoice, SupplierInvoice.id == SupplierPayment.invoice_id).where(
            SupplierInvoice.supplier_id == s.id, SupplierInvoice.branch_id == ctx.branch_id, func.date(SupplierPayment.paid_at).between(start, end)))
        if not grs and not inv[0] and not paid and not f.get("supplier_id"):
            bal = purchasing.supplier_balance(ctx, s)
            if not bal["balance"]:
                continue
        rows.append({"supplier": s.name, "supplier_id": s.id, "receipts": len(grs), "on_time_percent": _pct(on_time, len(dated)) if dated else None,
                     "quantity_accuracy_percent": _pct(accurate, len(po_lines)) if po_lines else None, "invoices": inv[0], "invoiced": q(inv[1]), "paid": q(paid),
                     **purchasing.supplier_balance(ctx, s)})
    return rows, {"note": f"On time = posted on or before the PO delivery date. Accurate = received within {tol * HUNDRED}% of ordered (purchasing setting)."}


# ---------------------------------------------------------------- RPT-22 expenses
def rpt22(ctx: Ctx, start: date, end: date, f: dict):
    stmt = select(ExpenseCategory.name_en, Expense.status, Expense.payment_method, func.count(), func.sum(Expense.amount_base)).join(
        ExpenseCategory, ExpenseCategory.id == Expense.category_id).where(Expense.branch_id == ctx.branch_id, Expense.expense_date.between(start, end),
                                                                          Expense.status != "Draft").group_by(ExpenseCategory.name_en, Expense.status, Expense.payment_method)
    if f.get("category"):
        stmt = stmt.where(ExpenseCategory.name_en == f["category"])
    rows = [{"category": c, "status": s, "payment_method": m, "count": n, "amount_base": q(a)} for c, s, m, n, a in ctx.db.execute(stmt.order_by(ExpenseCategory.name_en))]
    counted = ("Approved", "Paid")
    daily = ctx.db.execute(select(Expense.expense_date, func.sum(Expense.amount_base)).where(Expense.branch_id == ctx.branch_id, Expense.expense_date.between(start, end),
                                                                                            Expense.status.in_(counted)).group_by(Expense.expense_date).order_by(Expense.expense_date)).all()
    monthly: dict = defaultdict(lambda: ZERO)
    for d, a in daily:
        monthly[d.strftime("%Y-%m")] += a
    return rows, {"approved_total": q(sum((a for _, a in daily), ZERO)), "daily": [{"date": d, "amount_base": q(a)} for d, a in daily],
                  "monthly": [{"month": k, "amount_base": q(v)} for k, v in sorted(monthly.items())], "note": "Totals count Approved and Paid expenses; reversed ones are excluded."}


# ---------------------------------------------------------------- RPT-23 food cost and gross margin
def rpt23(ctx: Ctx, start: date, end: date, f: dict):
    db = ctx.db
    stmt = select(OrderItem.id, OrderItem.category_name_snapshot, OrderItem.item_name_en_snapshot, OrderItem.variant_name_snapshot, OrderItem.quantity, OrderItem.line_net).join(
        Order).where(_completed(ctx, start, end), OrderItem.item_status != "Cancelled")
    if f.get("category"):
        stmt = stmt.where(OrderItem.category_name_snapshot == f["category"])
    items = db.execute(stmt).all()
    cost = dict(db.execute(select(InventoryTransaction.source_id, func.sum(InventoryTransaction.total_cost)).where(
        InventoryTransaction.source_type == "OrderItem", InventoryTransaction.txn_type.in_(("SALE_CONSUMPTION", "SALE_REVERSAL")),
        InventoryTransaction.source_id.in_([i[0] for i in items] or [None])).group_by(InventoryTransaction.source_id)).all())
    per: dict = defaultdict(lambda: {"qty": ZERO, "net": ZERO, "cost": ZERO, "unmapped": ZERO})
    for iid, cat, name, variant, qty, net in items:
        p = per[(cat, f"{name} ({variant})" if variant and variant != "Regular" else name)]
        p["qty"] += qty
        p["net"] += net
        if iid in cost:
            p["cost"] += -cost[iid]
        else:
            p["unmapped"] += qty
    rows = [{"category": c, "item": i, "quantity_sold": p["qty"], "net_sales": q(p["net"]), "recipe_cost": q(p["cost"]),
             "unit_cost": q(p["cost"] / p["qty"]) if p["qty"] else ZERO, "average_price": q(p["net"] / p["qty"]) if p["qty"] else ZERO,
             "food_cost_percent": _pct(p["cost"], p["net"]), "gross_margin": q(p["net"] - p["cost"]), "quantity_without_recipe": p["unmapped"]}
            for (c, i), p in sorted(per.items(), key=lambda kv: (kv[0][0], -kv[1]["net"]))]
    cats: dict = defaultdict(lambda: [ZERO, ZERO])
    for r in rows:
        cats[r["category"]][0] += r["net_sales"]
        cats[r["category"]][1] += r["recipe_cost"]
    net = sum((r["net_sales"] for r in rows), ZERO)
    cst = sum((r["recipe_cost"] for r in rows), ZERO)
    return rows, {"net_sales": net, "recipe_cost": cst, "food_cost_percent": _pct(cst, net), "gross_margin": net - cst,
                  "categories": [{"category": k, "net_sales": v[0], "recipe_cost": v[1], "food_cost_percent": _pct(v[1], v[0]), "gross_margin": v[0] - v[1]} for k, v in sorted(cats.items())],
                  "note": "Theoretical cost: ingredients posted by recipes when items were sent, at the weighted average cost of that moment. Items sold without a recipe have no cost and are counted separately."}


# ---------------------------------------------------------------- RPT-25 customer purchase history
def rpt25(ctx: Ctx, start: date, end: date, f: dict):
    from app.services.front import mask_email, mask_phone

    ctx.require("customers.view")
    contact = ctx.can("customers.contact.view")
    base = and_(Order.branch_id == ctx.branch_id, Order.business_date.between(start, end), Order.order_status == "Completed", Order.customer_id.is_not(None))
    if f.get("customer_id"):
        c = ctx.db.get(Customer, f["customer_id"])
        if c is None:
            raise BusinessRuleError("VALIDATION_ERROR", "Unknown customer.")
        orders = ctx.db.scalars(select(Order).where(base, Order.customer_id == c.id).order_by(Order.created_at.desc())).all()
        rows = [{"order_no": o.order_no, "business_date": o.business_date, "order_type": o.order_type, "items": ", ".join(f"{i.quantity:g} × {i.item_name_en_snapshot}" for i in o.items
                                                                                                                       if i.item_status != "Cancelled"), "spend": o.subtotal} for o in orders]
        return rows, {"customer": c.name, "phone": c.phone_e164 if contact else mask_phone(c.phone_e164), "email": c.email if contact else mask_email(c.email),
                      "visits": len(orders), "spend": q(sum((o.subtotal for o in orders), ZERO)), "last_visit": orders[0].business_date if orders else None}
    data = ctx.db.execute(select(Customer, func.count(Order.id), func.sum(Order.subtotal), func.max(Order.business_date)).join(Order, Order.customer_id == Customer.id)
                          .where(base).group_by(Customer.id).order_by(func.sum(Order.subtotal).desc()).limit(500)).all()
    rows = [{"customer_id": c.id, "customer": c.name, "classification": c.classification, "phone": c.phone_e164 if contact else mask_phone(c.phone_e164), "visits": n,
             "spend": q(s), "average_spend": q(s / n), "last_visit": last} for c, n, s, last in data]
    return rows, {"customers": len(rows), "contact_masked": not contact}


# ---------------------------------------------------------------- RPT-26 control exceptions
def rpt26(ctx: Ctx, start: date, end: date, f: dict):
    from app.services.recipes import unmapped_items

    tz = ZoneInfo(ctx.branch.timezone)
    lo = datetime.combine(start, time.min, tz)
    hi = datetime.combine(end + timedelta(days=1), time.min, tz)
    rows: list[dict] = []
    actions = {"cash.force_close": "Forced cashier session close", "receipt.reprint": "Receipt reprint", "menu.price_set": "Menu price change"}
    for a in ctx.db.scalars(select(AuditLog).where(AuditLog.branch_id == ctx.branch_id, AuditLog.action.in_(list(actions)), AuditLog.occurred_at >= lo, AuditLog.occurred_at < hi)
                            .order_by(AuditLog.occurred_at)):
        rows.append({"type": actions[a.action], "when": a.occurred_at, "user_id": a.actor_user_id, "entity": f"{a.entity_type} {a.entity_id or ''}".strip(), "detail": a.after_data})
    # Self-approval is blocked by the API; any rows here mean data was changed outside it.
    for d, no in ctx.db.execute(select(OrderDiscount, Order.order_no).join(Order).where(Order.branch_id == ctx.branch_id, Order.business_date.between(start, end),
                                                                                       OrderDiscount.approved_by == OrderDiscount.requested_by)):
        rows.append({"type": "Self-approved discount", "when": d.created_at, "user_id": d.requested_by, "entity": f"Order {no}", "detail": {"kind": d.kind, "value": d.value}})
    for o in ctx.db.scalars(select(Order).where(Order.branch_id == ctx.branch_id, Order.business_date.between(start, min(end, ctx.business_date() - timedelta(days=1))),
                                                Order.order_status.in_(("Draft", "Open")))):
        rows.append({"type": "Order open after day end", "when": o.created_at, "user_id": o.server_user_id, "entity": f"Order {o.order_no}", "detail": {"business_date": o.business_date}})
    for b, ing in ctx.db.execute(select(StockBalance, Ingredient.name_en).join(Ingredient).where(StockBalance.branch_id == ctx.branch_id, StockBalance.quantity < 0)):
        rows.append({"type": "Negative stock (now)", "when": None, "user_id": None, "entity": ing, "detail": {"quantity": b.quantity}})
    for u in unmapped_items(ctx, max(_period_days(start, end), 1)):
        rows.append({"type": "Sold without recipe", "when": None, "user_id": None, "entity": u.get("item"), "detail": u})
    names = _names(ctx, [r["user_id"] for r in rows])
    for r in rows:
        r["user"] = names.get(r["user_id"])
    counts: dict = defaultdict(int)
    for r in rows:
        counts[r["type"]] += 1
    return rows, {"counts": dict(counts), "note": "Negative stock is the current position. Sold-without-recipe covers the same number of days up to today."}


def rpt06(ctx: Ctx, start: date, end: date, f: dict):
    from app.services.branches import comparison

    data = comparison(ctx, start, end, None)
    return data["rows"], {"consolidated": data["total"], "note": "Branches you are assigned to; needs report.cross_branch (BR-025)."}


REPORTS = {
    "RPT-06": ("Sales by branch", ("report.cross_branch",), rpt06),
    "RPT-05": ("Sales by employee", ("report.financial.view",), rpt05),
    "RPT-08": ("Order volume and AOV", ("report.financial.view",), rpt08),
    "RPT-09": ("Peak-hour analysis", ("report.financial.view", "kitchen.manage"), rpt09),
    "RPT-10": ("Table turnover", ("report.view",), rpt10),
    "RPT-15": ("Kitchen preparation time", ("kitchen.manage", "report.financial.view"), rpt15),
    "RPT-16": ("Ingredient consumption and variance", ("inventory.view", "report.financial.view"), rpt16),
    "RPT-19": ("Wastage report", ("inventory.view", "report.financial.view"), rpt19),
    "RPT-20": ("Purchase report", ("purchases.view",), rpt20),
    "RPT-21": ("Supplier report", ("purchases.view",), rpt21),
    "RPT-22": ("Expense report", ("report.financial.view",), rpt22),
    "RPT-23": ("Food cost and gross margin", ("report.financial.view", "recipes.manage"), rpt23),
    "RPT-25": ("Customer purchase history", ("report.financial.view",), rpt25),
    "RPT-26": ("Control exceptions", ("audit.view",), rpt26),
}


# ---------------------------------------------------------------- dashboard (FR-DASH-010, 011, 013)
def trends(ctx: Ctx, start: date, end: date, grain: str) -> list[dict]:
    data = ctx.db.execute(select(Order.business_date, func.count(), func.sum(Order.subtotal)).where(_completed(ctx, start, end)).group_by(Order.business_date)).all()
    buckets: dict = defaultdict(lambda: [0, ZERO])
    for d, n, net in data:
        key = d if grain == "day" else (d - timedelta(days=d.weekday()) if grain == "week" else d.replace(day=1))
        buckets[key][0] += n
        buckets[key][1] += net
    return [{"period_start": k, "orders": v[0], "net_sales": q(v[1])} for k, v in sorted(buckets.items())]


def cost_indicators(ctx: Ctx, start: date, end: date, net_sales: Decimal) -> dict:
    cogs = -(ctx.db.scalar(select(func.coalesce(func.sum(InventoryTransaction.total_cost), 0)).where(
        InventoryTransaction.branch_id == ctx.branch_id, InventoryTransaction.business_date.between(start, end),
        InventoryTransaction.txn_type.in_(("SALE_CONSUMPTION", "SALE_REVERSAL")))) or ZERO)
    expenses = ctx.db.scalar(select(func.coalesce(func.sum(Expense.amount_base), 0)).where(Expense.branch_id == ctx.branch_id, Expense.expense_date.between(start, end),
                                                                                          Expense.status.in_(("Approved", "Paid")))) or ZERO
    from app.services.delivery import platform_commissions

    platform = platform_commissions(ctx, start, end)  # BR-044: a cost, not a discount
    return {"theoretical_food_cost": q(cogs), "theoretical_food_cost_percent": _pct(cogs, net_sales), "approved_expenses": q(expenses), "platform_commissions": q(platform),
            "indicative_operating_result": {"value": q(net_sales - cogs - expenses - platform),
                                            "label": "indicative — not accounting profit (net sales − theoretical food cost − approved expenses − platform commissions)"}}
