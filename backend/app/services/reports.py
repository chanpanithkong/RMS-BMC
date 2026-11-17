"""Dashboard (SRS §6.1) and Phase 1 reports (§11.3). All figures come from posted records and order-time snapshots."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, func, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Forbidden, NotFound
from app.models import (Bill, BillCharge, CashierSession, Ingredient, InventoryLocation, KitchenTicket, Order, OrderDiscount, OrderItem, Payment, Refund, RestaurantTable,
                        StockBalance, User)
from app.services import cash as csvc
from app.utils.money import ZERO, q
from app.utils.timeutil import utcnow

FIN = "report.financial.view"


def _range(date_from: date | None, date_to: date | None, ctx: Ctx) -> tuple[date, date]:
    today = ctx.business_date()
    start, end = date_from or today, date_to or today
    if end < start:
        raise BusinessRuleError("VALIDATION_ERROR", "date_to must be on or after date_from.")
    if (end - start).days > 731:
        raise BusinessRuleError("RANGE_TOO_LONG", "The maximum range is 24 months.")
    return start, end


def sales(ctx: Ctx, start: date, end: date) -> dict:
    """§6.1 metric definitions. Sales are recognised on finalised bills; refunds by refund business day."""
    db = ctx.db
    b = select(func.coalesce(func.sum(Bill.gross_total), 0), func.coalesce(func.sum(Bill.discount_total), 0), func.coalesce(func.sum(Bill.service_charge_total), 0),
               func.coalesce(func.sum(Bill.tax_total), 0), func.coalesce(func.sum(Bill.delivery_fee), 0), func.count(Bill.id)).where(
        Bill.branch_id == ctx.branch_id, Bill.status.in_(("Paid", "Refunded")), Bill.business_date.between(start, end))
    gross, disc, svc, tax, fee, bills = db.execute(b).one()
    refunds = db.scalar(select(func.coalesce(func.sum(Refund.amount_base), 0)).where(Refund.branch_id == ctx.branch_id, Refund.status == "Completed",
                                                                                     Refund.business_date.between(start, end))) or ZERO
    net = gross - disc - refunds
    return {"gross_sales": q(gross), "discounts": q(disc), "refunds": q(refunds), "net_sales": q(net), "service_charges": q(svc), "taxes": q(tax), "delivery_fees": q(fee),
            "finalised_bills": bills}


def payments_by_method(ctx: Ctx, start: date, end: date) -> list[dict]:
    rows = ctx.db.execute(select(Payment.method_code, Payment.currency, func.count(), func.sum(Payment.amount_tendered - case((Payment.change_currency == Payment.currency, Payment.change_amount), else_=0)),
                                 func.sum(Payment.amount_base)).where(Payment.branch_id == ctx.branch_id, Payment.status == "Confirmed", Payment.business_date.between(start, end))
                          .group_by(Payment.method_code, Payment.currency).order_by(Payment.method_code)).all()
    refunds = dict(ctx.db.execute(select(Refund.method_code, func.sum(Refund.amount_base)).where(Refund.branch_id == ctx.branch_id, Refund.status == "Completed",
                                                                                                 Refund.business_date.between(start, end)).group_by(Refund.method_code)).all())
    return [{"method": m, "currency": c, "count": n, "amount_in_currency": q(a, c), "amount_base": q(base), "refunds_base": q(refunds.get(m, ZERO)),
             "net_collected_base": q(base - refunds.get(m, ZERO))} for m, c, n, a, base in rows]


def order_counts(ctx: Ctx, start: date, end: date, net_sales: Decimal | None) -> dict:
    db = ctx.db
    rows = dict(db.execute(select(Order.order_status, func.count()).where(Order.branch_id == ctx.branch_id, Order.business_date.between(start, end)).group_by(Order.order_status)).all())
    received = sum(v for k, v in rows.items() if k != "Draft")
    completed = rows.get("Completed", 0)
    out = {"received": received, "completed": completed, "cancelled": rows.get("Cancelled", 0), "open": rows.get("Open", 0)}
    if net_sales is not None:
        out["average_order_value"] = q(net_sales / completed) if completed else ZERO
    return out


def kitchen_pending(ctx: Ctx) -> list[dict]:
    now = utcnow()
    rows = ctx.db.execute(select(KitchenTicket.station_code, func.count(func.distinct(KitchenTicket.id)), func.min(KitchenTicket.created_at))
                          .join(OrderItem, and_(OrderItem.order_id == KitchenTicket.order_id, OrderItem.station_code == KitchenTicket.station_code))
                          .where(KitchenTicket.branch_id == ctx.branch_id, KitchenTicket.ticket_type.in_(("New", "Addition")), OrderItem.item_status.in_(("Sent", "InPreparation")))
                          .group_by(KitchenTicket.station_code)).all()
    return [{"station_code": s, "pending_tickets": n, "oldest_age_minutes": int((now - oldest).total_seconds() // 60)} for s, n, oldest in rows]


def occupancy(ctx: Ctx) -> dict:
    active = ctx.db.scalar(select(func.count()).select_from(RestaurantTable).where(RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.is_active, ~RestaurantTable.is_out_of_service)) or 0
    occupied = ctx.db.scalar(select(func.count()).select_from(RestaurantTable).where(RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.is_active,
                                                                                     RestaurantTable.service_state.in_(("Seated", "Ordering", "Served", "AwaitingPayment")))) or 0
    return {"occupied": occupied, "active": active, "percent": q(Decimal(occupied) * 100 / active) if active else ZERO}


def stock(ctx: Ctx) -> dict:
    rows = ctx.db.execute(select(StockBalance, Ingredient).join(Ingredient).where(StockBalance.branch_id == ctx.branch_id)).all()
    return {"low_stock_count": sum(1 for b, i in rows if b.quantity <= i.reorder_level),
            "valuation": q(sum((max(b.quantity, ZERO) * b.avg_cost for b, _ in rows), ZERO))}


def top_items(ctx: Ctx, start: date, end: date, n: int = 10) -> dict:
    base = (select(OrderItem.item_name_en_snapshot, func.sum(OrderItem.quantity).label("qty"), func.sum(OrderItem.line_net).label("net"))
            .join(Bill, Bill.order_id == OrderItem.order_id).where(Bill.branch_id == ctx.branch_id, Bill.status == "Paid", Bill.business_date.between(start, end),
                                                                   OrderItem.item_status != "Cancelled").group_by(OrderItem.item_name_en_snapshot))
    by_qty = ctx.db.execute(base.order_by(func.sum(OrderItem.quantity).desc()).limit(n)).all()
    return {"by_quantity": [{"item": a, "quantity": b} for a, b, _ in by_qty]}


def dashboard(ctx: Ctx, date_from: date | None, date_to: date | None, trend: str = "day") -> dict:
    """FR-DASH-001: only widgets the role is allowed to see; financial values only with report.financial.view."""
    start, end = _range(date_from, date_to, ctx)
    out: dict = {"business_date": ctx.business_date(), "from": start, "to": end, "calculated_at": utcnow(), "widgets": {}}
    w = out["widgets"]
    financial = ctx.can(FIN)
    if financial:
        s = sales(ctx, start, end)
        w["sales"] = s
        w["payments_by_method"] = payments_by_method(ctx, start, end)
        w["top_items"] = top_items(ctx, start, end)
        from app.services import reports_advanced as adv

        costs = adv.cost_indicators(ctx, start, end, s["net_sales"])  # FR-DASH-010
        w["indicative_operating_result"] = costs.pop("indicative_operating_result")  # FR-DASH-011
        w["costs"] = costs
        w["trends"] = {"grain": trend, "series": adv.trends(ctx, start, end, trend)}  # FR-DASH-013
    if ctx.can("orders.view_all") or financial:
        w["orders"] = order_counts(ctx, start, end, w.get("sales", {}).get("net_sales") if financial else None)
        w["table_occupancy"] = occupancy(ctx)
    if ctx.can("kitchen.view") and (ctx.can("kitchen.manage") or financial):
        w["kitchen"] = kitchen_pending(ctx)
    if ctx.can("inventory.view"):
        w["stock"] = stock(ctx)
    if ctx.can("cash.view") or financial:
        w["cashier_sessions"] = [{"session_id": cs.id, "user_id": cs.user_id, "status": cs.status,
                                  "expected": csvc.expected(ctx, cs) if cs.status == "Open" else None, "results": csvc.result_rows(cs) if cs.status != "Open" else None}
                                 for cs in ctx.db.scalars(select(CashierSession).where(CashierSession.branch_id == ctx.branch_id).order_by(CashierSession.opened_at.desc()).limit(10))]
    elif ctx.can("cash.operate"):
        own = ctx.db.scalar(select(CashierSession).where(CashierSession.branch_id == ctx.branch_id, CashierSession.user_id == ctx.user_id, CashierSession.status == "Open"))
        w["my_session"] = {"session_id": own.id, "opened_at": own.opened_at} if own else None
    return out


# ---------------------------------------------------------------- report catalogue (Phase 1 subset of §11.3)
CATALOGUE = {
    "RPT-01": ("Daily sales report", FIN), "RPT-02": ("Monthly sales report", FIN), "RPT-03": ("Sales by menu category", FIN), "RPT-04": ("Sales by menu item", FIN),
    "RPT-07": ("Sales by payment method", FIN), "RPT-11": ("Cancelled and voided items", FIN), "RPT-12": ("Refund report", FIN), "RPT-13": ("Discount report", FIN),
    "RPT-14": ("Tax and service-charge summary", FIN), "RPT-17": ("Inventory valuation", "inventory.view"), "RPT-18": ("Low-stock report", "inventory.view"),
    "RPT-24": ("Cashier shift report", "cash.view"),
}


def _all_reports() -> dict:
    """id -> (name, any-of permissions). Phase 1 reports above, Phase 2 in reports_advanced."""
    from app.services.reports_advanced import REPORTS

    out = {k: (n, (p,)) for k, (n, p) in CATALOGUE.items()}
    out.update({k: (n, perms) for k, (n, perms, _) in REPORTS.items()})
    return dict(sorted(out.items()))


def catalogue(ctx: Ctx) -> list[dict]:
    return [{"id": k, "name": n, "available": any(ctx.can(p) for p in perms)} for k, (n, perms) in _all_reports().items()
            if any(ctx.can(p) for p in perms) or ctx.can("report.view")]


def run(ctx: Ctx, report_id: str, date_from: date | None, date_to: date | None, filters: dict | None = None) -> dict:
    from app.services.reports_advanced import REPORTS

    reports = _all_reports()
    if report_id not in reports:
        raise NotFound("Report")
    name, perms = reports[report_id]
    if not any(ctx.can(p) for p in perms):
        raise Forbidden(f"You don't have access to {name}.", code="REPORT_FORBIDDEN")
    start, end = _range(date_from, date_to, ctx)
    if report_id in REPORTS:
        rows, summary = REPORTS[report_id][2](ctx, start, end, {k: v for k, v in (filters or {}).items() if v is not None})
        return {"id": report_id, "name": name, "from": start, "to": end, "branch": ctx.branch.code, "currency": "USD", "generated_at": utcnow(),
                "generated_by": ctx.user.username, "filters": {k: v for k, v in (filters or {}).items() if v is not None}, "summary": summary, "rows": rows,
                "note": "Figures derived from recorded transactions."}
    db = ctx.db
    rows: list[dict]
    summary: dict = {}
    paid = and_(Bill.branch_id == ctx.branch_id, Bill.status.in_(("Paid", "Refunded")), Bill.business_date.between(start, end))
    if report_id == "RPT-01":
        summary = {**sales(ctx, start, end), "orders": order_counts(ctx, start, end, sales(ctx, start, end)["net_sales"])}
        rows = payments_by_method(ctx, start, end)
    elif report_id == "RPT-02":
        rows = []
        d = start
        while d <= end:
            s = sales(ctx, d, d)
            rows.append({"business_date": d, **s})
            d += timedelta(days=1)
        summary = sales(ctx, start, end)
    elif report_id in ("RPT-03", "RPT-04"):
        key = OrderItem.category_name_snapshot if report_id == "RPT-03" else OrderItem.item_name_en_snapshot
        data = db.execute(select(key, func.sum(OrderItem.quantity), func.sum(OrderItem.line_gross), func.sum(OrderItem.line_discount), func.sum(OrderItem.line_net))
                          .join(Bill, Bill.order_id == OrderItem.order_id).where(paid, Bill.split_index == 1, OrderItem.item_status != "Cancelled").group_by(key)
                          .order_by(func.sum(OrderItem.line_net).desc())).all()
        total_net = sum((r[4] for r in data), ZERO)
        rows = [{"name": n, "quantity": qty, "gross": q(g), "discounts": q(dsc), "net_sales": q(net), "share_percent": q(net * 100 / total_net) if total_net else ZERO}
                for n, qty, g, dsc, net in data]
    elif report_id == "RPT-07":
        rows = payments_by_method(ctx, start, end)
    elif report_id == "RPT-11":
        data = db.execute(select(OrderItem, Order.order_no).join(Order).where(Order.branch_id == ctx.branch_id, Order.business_date.between(start, end),
                                                                              OrderItem.item_status == "Cancelled", OrderItem.void_type.is_not(None))).all()
        rows = [{"order_no": no, "item": i.item_name_en_snapshot, "quantity": i.quantity, "value": q(i.unit_price_snapshot * i.quantity), "void_type": i.void_type,
                 "reason": i.void_reason, "approved_by": i.void_approved_by, "waste_outcome": i.waste_outcome} for i, no in data]
    elif report_id == "RPT-12":
        rows = [{"refund_no": r.refund_no, "payment_id": r.payment_id, "amount_base": r.amount_base, "method": r.method_code, "reason": r.reason, "status": r.status,
                 "requested_by": r.requested_by, "approved_by": r.approved_by}
                for r in db.scalars(select(Refund).where(Refund.branch_id == ctx.branch_id, Refund.business_date.between(start, end)).order_by(Refund.created_at))]
    elif report_id == "RPT-13":
        data = db.execute(select(OrderDiscount, Order.order_no).join(Order).where(Order.branch_id == ctx.branch_id, Order.business_date.between(start, end))).all()
        rows = [{"order_no": no, "scope": "item" if d.order_item_id else "order", "kind": d.kind, "value": d.value, "reason": d.reason, "requested_by": d.requested_by,
                 "approved_by": d.approved_by, "removed": d.removed_at is not None} for d, no in data]
    elif report_id == "RPT-14":
        data = db.execute(select(BillCharge.charge_type, BillCharge.name, BillCharge.rate, Order.order_type, func.sum(BillCharge.base_amount), func.sum(BillCharge.amount))
                          .join(Bill, Bill.id == BillCharge.bill_id).join(Order, Order.id == Bill.order_id).where(paid)
                          .group_by(BillCharge.charge_type, BillCharge.name, BillCharge.rate, Order.order_type)).all()
        rows = [{"charge_type": t, "name": n, "rate": r, "order_type": ot, "base": q(b), "amount": q(a)} for t, n, r, ot, b, a in data]
        summary = {"basis": "As configured in tax profiles; seeded rates are illustrative and unverified (V-01)."}
    elif report_id in ("RPT-17", "RPT-18"):
        data = db.execute(select(StockBalance, Ingredient, InventoryLocation).join(Ingredient).join(InventoryLocation).where(StockBalance.branch_id == ctx.branch_id)
                          .order_by(Ingredient.code)).all()
        rows = [{"ingredient": i.name_en, "code": i.code, "location": loc.name, "on_hand": b.quantity, "unit": i.stock_uom.code, "avg_cost": b.avg_cost,
                 "value": q(max(b.quantity, ZERO) * b.avg_cost), "reorder_level": i.reorder_level, "suggested_order": i.reorder_qty}
                for b, i, loc in data if report_id == "RPT-17" or b.quantity <= i.reorder_level]
        summary = {"valuation": q(sum((r["value"] for r in rows), ZERO))} if report_id == "RPT-17" else {"items": len(rows)}
    else:  # RPT-24
        sessions = db.scalars(select(CashierSession).where(CashierSession.branch_id == ctx.branch_id, CashierSession.business_date.between(start, end))).all()
        names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_([s.user_id for s in sessions] or [None]))).all())
        rows = [{"session_id": s.id, "cashier": names.get(s.user_id), "status": s.status, "results": csvc.result_rows(s), "approved_by": s.approved_by} for s in sessions]
    return {"id": report_id, "name": name, "from": start, "to": end, "branch": ctx.branch.code, "currency": "USD", "generated_at": utcnow(), "generated_by": ctx.user.username,
            "summary": summary, "rows": rows, "note": "Figures derived from recorded transactions."}
