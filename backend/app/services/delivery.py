"""Delivery and takeaway (SRS §6.15 DLV; BR-044, BR-052).

Statuses: PendingAssignment -> Assigned -> OutForDelivery -> Delivered, with Failed (back to PendingAssignment
for re-delivery, or the order is cancelled through the normal order flow) and Cancelled.
Delivery fees are a separate order charge taxed by the zone's own tax profile. Platform commissions are a cost
recorded per platform order and checked against platform settlements; they are never discounts.
"""
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.core.realtime import emit
from app.models import Delivery, DeliveryZone, Order, OrderItem, PlatformOrder, PlatformSettlement, PlatformSettlementLine, User
from app.services.platform import audit, notify_users
from app.utils.money import ZERO, q
from app.utils.timeutil import utcnow

FLOW = {"PendingAssignment": {"Assigned", "Cancelled"}, "Assigned": {"Assigned", "OutForDelivery", "Failed", "Cancelled"},
        "OutForDelivery": {"Delivered", "Failed"}, "Failed": {"PendingAssignment", "Cancelled"}, "Delivered": set(), "Cancelled": set()}


# ---------------------------------------------------------------- zones and fees (FR-DLV-002, FR-DLV-003)
def zone(ctx: Ctx, zone_id: uuid.UUID) -> DeliveryZone:
    z = ctx.db.get(DeliveryZone, zone_id)
    if z is None or z.branch_id != ctx.branch_id:
        raise NotFound("Delivery zone")
    return z


def zone_fee(z: DeliveryZone, food_subtotal: Decimal) -> tuple[Decimal, str]:
    if z.free_over is not None and food_subtotal >= z.free_over:
        return ZERO, "FreeOver"
    return z.fee, "Zone"


def for_order(ctx: Ctx, order_id: uuid.UUID, lock: bool = False) -> Delivery | None:
    stmt = select(Delivery).where(Delivery.order_id == order_id, Delivery.branch_id == ctx.branch_id)
    return ctx.db.scalar(stmt.with_for_update() if lock else stmt)


def attach(ctx: Ctx, order: Order, data: dict) -> Delivery:
    """Called when a POS delivery order is created. Zone must be active at this branch; the fee comes from its rule unless overridden."""
    if not order.customer_phone or not data.get("address"):
        raise BusinessRuleError("DELIVERY_DETAILS_REQUIRED", "Delivery orders need a phone number and address.")
    z = zone(ctx, data["zone_id"])
    if not z.is_active:
        raise BusinessRuleError("ZONE_NOT_SERVED", f"{z.name} isn't served at the moment.")
    d = Delivery(order_id=order.id, branch_id=ctx.branch_id, zone_id=z.id, address=data["address"], landmark=data.get("landmark"), latitude=data.get("latitude"),
                 longitude=data.get("longitude"), phone=order.customer_phone, fee=z.fee)
    if data.get("fee_override") is not None:
        ctx.require("delivery.fee_override")
        d.fee, d.fee_rule, d.fee_overridden_by = data["fee_override"], "Manual", ctx.user_id
    order.delivery_address = data["address"]
    ctx.db.add(d)
    ctx.db.flush()
    audit(ctx.db, ctx, "delivery.create", "Order", order.id, after={"zone": z.name, "fee_rule": d.fee_rule, "fee": d.fee})
    return d


def refresh_fee(ctx: Ctx, order: Order) -> None:
    """Zone fee rules follow the food subtotal (free over a threshold). Manual and platform fees stay as set. Called from orders.recalc."""
    from app.services.orders import calculation, paid_total

    d = for_order(ctx, order.id)
    if d is None:
        return
    if d.fee_rule in ("Zone", "FreeOver") and d.zone_id and paid_total(ctx.db, order) == 0:
        subtotal = calculation(ctx.db, order).subtotal
        d.fee, d.fee_rule = zone_fee(ctx.db.get(DeliveryZone, d.zone_id), subtotal)
    order.delivery_fee = d.fee


def override_fee(ctx: Ctx, order: Order, fee: Decimal, reason: str) -> Delivery:
    from app.services.orders import ensure_editable, paid_total, recalc

    ctx.require("delivery.fee_override")
    ensure_editable(order)
    if paid_total(ctx.db, order) > 0:
        raise Conflict("ORDER_PARTLY_PAID", "The fee can't change after payment has started.")
    d = for_order(ctx, order.id, lock=True)
    if d is None:
        raise NotFound("Delivery")
    before = {"fee": d.fee, "rule": d.fee_rule}
    d.fee, d.fee_rule, d.fee_overridden_by = fee, "Manual", ctx.user_id
    recalc(ctx, order)
    audit(ctx.db, ctx, "delivery.fee_override", "Order", order.id, before=before, after={"fee": fee}, reason=reason)
    return d


def check_minimum(ctx: Ctx, order: Order) -> None:
    """Before sending to the kitchen: the zone's minimum order (food subtotal) must be met."""
    from app.services.orders import calculation

    d = for_order(ctx, order.id)
    if d is None or not d.zone_id:
        return
    z = ctx.db.get(DeliveryZone, d.zone_id)
    if z.min_order is not None and calculation(ctx.db, order).subtotal < z.min_order:
        raise BusinessRuleError("MINIMUM_ORDER_NOT_MET", f"{z.name} has a minimum order of {z.min_order:.2f}.")


# ---------------------------------------------------------------- riders and status (FR-DLV-004, FR-DLV-005, FR-DLV-009)
def _move(ctx: Ctx, d: Delivery, to: str) -> None:
    if to not in FLOW[d.status]:
        raise Conflict("DELIVERY_STATUS_INVALID", f"A {d.status} delivery can't become {to}.")
    d.status = to


def _can_act(ctx: Ctx, d: Delivery) -> None:
    if ctx.can("delivery.manage"):
        return
    if ctx.can("delivery.operate") and d.rider_user_id == ctx.user_id:
        return
    raise Forbidden("Only the assigned rider or a manager can update this delivery.", code="NOT_YOUR_DELIVERY")


def assign(ctx: Ctx, d: Delivery, rider_id: uuid.UUID) -> Delivery:
    from app.core.dependencies import load_permissions

    ctx.require("delivery.manage")
    rider = ctx.db.get(User, rider_id)
    if rider is None or rider.status != "Active" or ctx.branch_id not in {b.id for b in rider.branches}:
        raise NotFound("Rider")
    if "delivery.operate" not in load_permissions(ctx.db, rider)[0]:
        raise BusinessRuleError("NOT_A_RIDER", "This user doesn't have the rider permission.")
    _move(ctx, d, "Assigned")
    d.rider_user_id, d.assigned_at = rider.id, utcnow()
    order = ctx.db.get(Order, d.order_id)
    notify_users(ctx.db, [rider.id], ctx.branch_id, "Delivery", f"Delivery {order.order_no}", d.address, f"/rider/{d.id}", {"delivery_id": str(d.id)})
    audit(ctx.db, ctx, "delivery.assign", "Order", d.order_id, after={"rider": rider.username})
    return d


def out_for_delivery(ctx: Ctx, d: Delivery) -> Delivery:
    _can_act(ctx, d)
    order = ctx.db.get(Order, d.order_id)
    live = [i for i in order.items if i.item_status != "Cancelled"]
    if not live or any(i.item_status not in ("Ready", "Collected") for i in live):
        raise Conflict("ORDER_NOT_READY", "All items must be ready before the order leaves.")
    _move(ctx, d, "OutForDelivery")
    d.out_at = utcnow()
    _event(ctx, d, order)
    return d


def delivered(ctx: Ctx, d: Delivery, recipient_name: str | None) -> Delivery:
    """Rider confirms on a phone browser. Items become Collected; the order completes once it is also paid (BR-031)."""
    from app.services.orders import serve

    _can_act(ctx, d)
    _move(ctx, d, "Delivered")
    d.delivered_at, d.recipient_name = utcnow(), recipient_name
    order = ctx.db.get(Order, d.order_id, with_for_update=True)
    serve(ctx, order, None)
    _event(ctx, d, order)
    return d


def failed(ctx: Ctx, d: Delivery, reason: str) -> Delivery:
    _can_act(ctx, d)
    _move(ctx, d, "Failed")
    d.failed_at, d.failure_reason = utcnow(), reason
    order = ctx.db.get(Order, d.order_id)
    from app.services.platform import notify_permission

    notify_permission(ctx.db, ctx.branch_id, "delivery.manage", "Delivery", f"Delivery {order.order_no} failed", reason, f"/orders/{order.id}")
    _event(ctx, d, order, reason)
    return d


def redeliver(ctx: Ctx, d: Delivery) -> Delivery:
    ctx.require("delivery.manage")
    _move(ctx, d, "PendingAssignment")
    d.rider_user_id = d.assigned_at = d.out_at = None
    audit(ctx.db, ctx, "delivery.redeliver", "Order", d.order_id, after={"previous_failure": d.failure_reason})
    return d


def on_order_cancelled(ctx: Ctx, order: Order) -> None:
    """Order cancellation (BR-006 voids, BR-012 refunds) is done by the order flow; the delivery follows it."""
    d = for_order(ctx, order.id, lock=True)
    if d and d.status not in ("Delivered", "Cancelled"):
        d.status = "Cancelled"


def _event(ctx: Ctx, d: Delivery, order: Order, reason: str | None = None) -> None:
    audit(ctx.db, ctx, f"delivery.{d.status[0].lower() + d.status[1:]}", "Order", order.id, after={"status": d.status, "recipient": d.recipient_name}, reason=reason)
    emit(ctx.db, f"branch:{ctx.branch_id}", "delivery.updated", {"order_id": str(order.id), "status": d.status})


def delivery_out(ctx: Ctx, d: Delivery, order: Order | None = None) -> dict:
    from app.services.orders import paid_total

    order = order or ctx.db.get(Order, d.order_id)
    return {**{k: getattr(d, k) for k in ("id", "order_id", "zone_id", "address", "landmark", "latitude", "longitude", "phone", "fee", "fee_rule", "status", "rider_user_id",
                                          "assigned_at", "out_at", "delivered_at", "failed_at", "failure_reason", "recipient_name")},
            "order_no": order.order_no, "customer_name": order.customer_name, "scheduled_at": order.scheduled_at, "order_total": order.grand_total,
            "amount_due": max(order.grand_total - paid_total(ctx.db, order), ZERO), "kitchen_status": order.kitchen_status}


# ---------------------------------------------------------------- takeaway ready board (FR-DLV-006, AT-DLV-03)
def ready_board(ctx: Ctx) -> list[dict]:
    rows = ctx.db.scalars(select(Order).where(Order.branch_id == ctx.branch_id, Order.order_status == "Open", Order.order_type == "Takeaway", Order.kitchen_status == "Ready")
                          .order_by(Order.created_at)).all()
    return [{"order_id": o.id, "order_no": o.order_no, "pickup_name": o.pickup_name or o.customer_name, "scheduled_at": o.scheduled_at} for o in rows]


# ---------------------------------------------------------------- platform orders (FR-DLV-007, FR-DLV-010, AT-DLV-02)
def record_platform_order(ctx: Ctx, order: Order, platform: str, ref: str, rate: Decimal | None, amount: Decimal | None) -> PlatformOrder:
    if ctx.db.scalar(select(PlatformOrder.id).where(func.lower(PlatformOrder.platform) == platform.lower(), PlatformOrder.platform_ref == ref)):
        raise Conflict("PLATFORM_REF_EXISTS", "This platform order is already recorded.")  # BR-030, unique per platform
    po = PlatformOrder(order_id=order.id, branch_id=ctx.branch_id, platform=platform, platform_ref=ref, commission_rate=rate, commission_amount=ZERO)
    ctx.db.add(po)
    ctx.db.flush()
    po.commission_amount = amount if amount is not None else ZERO
    update_commission(ctx, po, order)
    audit(ctx.db, ctx, "platform.order_record", "Order", order.id, after={"platform": platform, "ref": ref, "rate": rate, "commission": po.commission_amount})
    return po


def update_commission(ctx: Ctx, po: PlatformOrder, order: Order) -> None:
    if po.commission_rate is not None:
        po.commission_amount = q(order.grand_total * po.commission_rate)


def settle(ctx: Ctx, data: dict) -> PlatformSettlement:
    ctx.require("platform.reconcile")
    db = ctx.db
    if db.scalar(select(PlatformSettlement.id).where(func.lower(PlatformSettlement.platform) == data["platform"].lower(), PlatformSettlement.statement_ref == data["statement_ref"])):
        raise Conflict("SETTLEMENT_EXISTS", "This statement is already recorded.")
    s = PlatformSettlement(branch_id=ctx.branch_id, platform=data["platform"], statement_ref=data["statement_ref"], period_from=data["period_from"],
                           period_to=data["period_to"], amount_paid=data["amount_paid"], recorded_by=ctx.user_id)
    db.add(s)
    db.flush()
    for ln in data["lines"]:
        po = db.scalar(select(PlatformOrder).where(func.lower(PlatformOrder.platform) == s.platform.lower(), PlatformOrder.platform_ref == ln["platform_ref"],
                                                   PlatformOrder.branch_id == ctx.branch_id).with_for_update())
        db.add(PlatformSettlementLine(settlement_id=s.id, platform_ref=ln["platform_ref"], gross=ln["gross"], commission=ln["commission"], net=ln["net"],
                                      platform_order_id=po.id if po else None))
    db.flush()
    db.refresh(s)
    rec = reconcile(ctx, s)
    bad = {x["platform_ref"] for x in rec["differences"] if x["platform_ref"]}
    for ln in s.lines:
        if ln.platform_order_id:
            po = db.get(PlatformOrder, ln.platform_order_id)
            po.settlement_id, po.settlement_status = s.id, "Disputed" if ln.platform_ref in bad else "Settled"
    audit(db, ctx, "platform.settlement_record", "PlatformSettlement", s.id, after={"platform": s.platform, "statement": s.statement_ref, "paid": s.amount_paid,
                                                                                    "differences": len(rec["differences"])})
    return s


def reconcile(ctx: Ctx, s: PlatformSettlement) -> dict:
    """Differences between the statement and RMS: unknown or missing orders, gross, commission, line arithmetic and payout total (BR-044)."""
    db = ctx.db
    diffs: list[dict] = []
    seen = set()
    for ln in s.lines:
        seen.add(ln.platform_ref)
        if ln.gross - ln.commission != ln.net:
            diffs.append({"platform_ref": ln.platform_ref, "issue": "Line net isn't gross minus commission", "statement": ln.net, "rms": ln.gross - ln.commission})
        if not ln.platform_order_id:
            diffs.append({"platform_ref": ln.platform_ref, "issue": "Not recorded in RMS", "statement": ln.gross, "rms": None})
            continue
        po = db.get(PlatformOrder, ln.platform_order_id)
        order = db.get(Order, po.order_id)
        if order.order_status == "Cancelled":
            diffs.append({"platform_ref": ln.platform_ref, "issue": "Order is cancelled in RMS", "statement": ln.gross, "rms": ZERO})
        elif order.grand_total != ln.gross:
            diffs.append({"platform_ref": ln.platform_ref, "issue": "Gross differs", "statement": ln.gross, "rms": order.grand_total})
        if po.commission_amount != ln.commission:
            diffs.append({"platform_ref": ln.platform_ref, "issue": "Commission differs", "statement": ln.commission, "rms": po.commission_amount})
    missing = db.execute(select(PlatformOrder.platform_ref, Order.grand_total).join(Order, Order.id == PlatformOrder.order_id).where(
        func.lower(PlatformOrder.platform) == s.platform.lower(), PlatformOrder.branch_id == s.branch_id, Order.business_date.between(s.period_from, s.period_to),
        Order.order_status != "Cancelled")).all()
    for ref, total in missing:
        if ref not in seen:
            diffs.append({"platform_ref": ref, "issue": "Missing from the statement", "statement": None, "rms": total})
    lines_net = sum((ln.net for ln in s.lines), ZERO)
    if lines_net != s.amount_paid:
        diffs.append({"platform_ref": None, "issue": "Payout differs from the sum of lines", "statement": s.amount_paid, "rms": lines_net})
    return {"settlement_id": s.id, "platform": s.platform, "statement_ref": s.statement_ref, "amount_paid": s.amount_paid,
            "gross": sum((ln.gross for ln in s.lines), ZERO), "commission": sum((ln.commission for ln in s.lines), ZERO), "lines": len(s.lines), "differences": diffs}


def platform_commissions(ctx: Ctx, start: date, end: date) -> Decimal:
    """Platform cost for the period: commissions on platform orders that weren't cancelled (BR-044: a cost, not a discount)."""
    return ctx.db.scalar(select(func.coalesce(func.sum(PlatformOrder.commission_amount), 0)).join(Order, Order.id == PlatformOrder.order_id).where(
        PlatformOrder.branch_id == ctx.branch_id, Order.business_date.between(start, end), Order.order_status != "Cancelled")) or ZERO


# ---------------------------------------------------------------- performance (FR-DLV-011)
def performance(ctx: Ctx, start: date, end: date) -> dict:
    db = ctx.db
    data = db.execute(select(Delivery, Order, DeliveryZone.name, DeliveryZone.estimated_minutes).join(Order, Order.id == Delivery.order_id)
                      .outerjoin(DeliveryZone, DeliveryZone.id == Delivery.zone_id).where(Delivery.branch_id == ctx.branch_id, Order.business_date.between(start, end))).all()
    prep: dict = defaultdict(list)
    for oid, sent, ready in db.execute(select(OrderItem.order_id, OrderItem.sent_at, OrderItem.ready_at).where(OrderItem.order_id.in_([o.id for _, o, _, _ in data] or [None]),
                                                                                                             OrderItem.ready_at.is_not(None), OrderItem.sent_at.is_not(None))):
        prep[oid].append((ready - sent).total_seconds() / 60)
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_({d.rider_user_id for d, *_ in data if d.rider_user_id} or {None}))).all())

    def group(key):
        g: dict = defaultdict(lambda: {"orders": 0, "delivered": 0, "failed": 0, "late": 0, "prep": [], "ride": []})
        for d, o, zname, est in data:
            r = g[key(d, o, zname)]
            r["orders"] += 1
            r["prep"] += prep.get(o.id, [])
            if d.status == "Delivered":
                r["delivered"] += 1
                if d.out_at and d.delivered_at:
                    r["ride"].append((d.delivered_at - d.out_at).total_seconds() / 60)
                if est and d.delivered_at and (d.delivered_at - o.created_at).total_seconds() / 60 > est:
                    r["late"] += 1
            if d.failed_at:
                r["failed"] += 1
        return [{"key": k, "orders": v["orders"], "delivered": v["delivered"], "failed": v["failed"], "late": v["late"],
                 "avg_prep_minutes": round(sum(v["prep"]) / len(v["prep"]), 1) if v["prep"] else None,
                 "avg_delivery_minutes": round(sum(v["ride"]) / len(v["ride"]), 1) if v["ride"] else None} for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))]

    platform = dict(db.execute(select(PlatformOrder.order_id, PlatformOrder.platform).where(PlatformOrder.order_id.in_([o.id for _, o, _, _ in data] or [None]))).all())
    return {"from": start, "to": end, "by_rider": group(lambda d, o, z: names.get(d.rider_user_id, "Unassigned")), "by_zone": group(lambda d, o, z: z or "No zone"),
            "by_platform": group(lambda d, o, z: platform.get(o.id, "Own delivery")),
            "note": "Late = delivered later than the zone's estimated minutes after the order was created. Delivery time runs from out-for-delivery to delivered."}
