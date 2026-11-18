"""Loyalty points (FR-PROMO-011, FR-CUST-008; rules decided by the owner for D-14).

* Earn: 1 point per whole 1.00 USD of net sales (the order's discounted subtotal: no tax, service charge or delivery fee),
  once, when an order with a customer completes. All channels earn, including orders with promotions (configurable).
* Redeem: in steps of 100 points = 1.00 USD off, as an order-level discount that can't exceed the order.
* Expiry: each earned lot expires 12 months after it was earned; redemptions use the oldest points first.
* Refunds take back points in proportion to the amount refunded. Removing a redemption or cancelling the order returns its points.
The ledger is append-only; Customer.loyalty_points is the running balance and can go below zero only through refund clawbacks.
"""
import calendar
import math
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, NotFound
from app.models import Customer, LoyaltyTransaction, Order, OrderDiscount, Refund
from app.services.platform import audit, get_setting
from app.utils.money import ZERO
from app.utils.timeutil import utcnow


def settings(db: Session, branch_id) -> dict:
    return get_setting(db, "loyalty", branch_id)


def add_months(dt: datetime, months: int) -> datetime:
    y, m = divmod(dt.month - 1 + months, 12)
    year, month = dt.year + y, m + 1
    return dt.replace(year=year, month=month, day=min(dt.day, calendar.monthrange(year, month)[1]))


def _customer(db: Session, customer_id) -> Customer:
    c = db.scalar(select(Customer).where(Customer.id == customer_id).with_for_update())
    if c is None:
        raise NotFound("Customer")
    return c


def _lots(db: Session, customer_id, now: datetime, first_order_id=None) -> list[LoyaltyTransaction]:
    lots = db.scalars(select(LoyaltyTransaction).where(LoyaltyTransaction.customer_id == customer_id, LoyaltyTransaction.remaining > 0,
                                                       LoyaltyTransaction.expires_at > now).order_by(LoyaltyTransaction.expires_at, LoyaltyTransaction.created_at)
                      .with_for_update()).all()
    if first_order_id:
        lots.sort(key=lambda x: x.order_id != first_order_id)  # a clawback takes from the order's own lot first
    return lots


def _consume(db: Session, customer_id, points: int, now: datetime, first_order_id=None) -> tuple[int, datetime | None]:
    """Take points from lots oldest first. Returns (points taken, earliest expiry touched)."""
    taken, earliest = 0, None
    for lot in _lots(db, customer_id, now, first_order_id):
        if taken >= points:
            break
        use = min(lot.remaining, points - taken)
        lot.remaining -= use
        taken += use
        earliest = lot.expires_at if earliest is None else min(earliest, lot.expires_at)
    return taken, earliest


def expire_due(db: Session, now: datetime | None = None, customer_id=None) -> int:
    """Expire lots past their date (daily worker, and before every redemption). Returns points expired."""
    now = now or utcnow()
    stmt = select(LoyaltyTransaction).where(LoyaltyTransaction.remaining > 0, LoyaltyTransaction.expires_at <= now)
    if customer_id:
        stmt = stmt.where(LoyaltyTransaction.customer_id == customer_id)
    total = 0
    for lot in db.scalars(stmt.order_by(LoyaltyTransaction.customer_id).with_for_update()):
        c = _customer(db, lot.customer_id)
        db.add(LoyaltyTransaction(customer_id=c.id, kind="Expire", points=-lot.remaining, reason=f"Points earned {lot.created_at:%Y-%m-%d} expired"))
        c.loyalty_points -= lot.remaining
        total += lot.remaining
        lot.remaining = 0
    db.flush()
    return total


# ---------------------------------------------------------------- earning
def earn(ctx: Ctx, order: Order) -> LoyaltyTransaction | None:
    db = ctx.db
    s = settings(db, order.branch_id)
    if not s.get("enabled") or not order.customer_id or order.channel not in s.get("earn_channels", []):
        return None
    if not s.get("earn_with_promotions", True) and db.scalar(select(OrderDiscount.id).where(OrderDiscount.order_id == order.id, OrderDiscount.removed_at.is_(None),
                                                                                           OrderDiscount.promotion_id.is_not(None))):
        return None
    if db.scalar(select(LoyaltyTransaction.id).where(LoyaltyTransaction.order_id == order.id, LoyaltyTransaction.kind == "Earn")):
        return None  # once per order
    points = int(math.floor(order.subtotal * Decimal(str(s.get("points_per_usd", "1")))))
    if points <= 0:
        return None
    c = _customer(db, order.customer_id)
    if c.anonymised_at or c.merged_into_id:
        return None
    now = utcnow()
    t = LoyaltyTransaction(customer_id=c.id, branch_id=order.branch_id, order_id=order.id, kind="Earn", points=points, remaining=points,
                           expires_at=add_months(now, int(s.get("expiry_months", 12))), reason=f"Order {order.order_no}", created_by=ctx.user_id)
    db.add(t)
    c.loyalty_points += points
    db.flush()
    audit(db, ctx, "loyalty.earn", "Customer", c.id, after={"order": order.order_no, "points": points, "balance": c.loyalty_points})
    return t


def clawback(ctx: Ctx, order: Order, refund: Refund) -> int:
    """Take back points in proportion to what has been refunded on the order (total refunds ÷ order total)."""
    db = ctx.db
    earned = db.scalar(select(LoyaltyTransaction).where(LoyaltyTransaction.order_id == order.id, LoyaltyTransaction.kind == "Earn"))
    if earned is None or order.grand_total <= 0:
        return 0
    from app.models import Bill

    refunded = db.scalar(select(func.coalesce(func.sum(Refund.amount_base), 0)).join(Bill, Bill.id == Refund.bill_id).where(Bill.order_id == order.id,
                                                                                                                         Refund.status == "Completed")) or ZERO
    keep = int(math.floor(earned.points * max(Decimal(1) - refunded / order.grand_total, ZERO)))
    already = -(db.scalar(select(func.coalesce(func.sum(LoyaltyTransaction.points), 0)).where(LoyaltyTransaction.order_id == order.id,
                                                                                           LoyaltyTransaction.kind == "Clawback")) or 0)
    take = earned.points - keep - already
    if take <= 0:
        return 0
    c = _customer(db, earned.customer_id)
    _consume(db, c.id, take, utcnow(), first_order_id=order.id)  # if already spent, the balance goes below zero
    db.add(LoyaltyTransaction(customer_id=c.id, branch_id=order.branch_id, order_id=order.id, refund_id=refund.id, kind="Clawback", points=-take,
                              reason=f"Refund {refund.refund_no}", created_by=ctx.user_id))
    c.loyalty_points -= take
    db.flush()
    audit(db, ctx, "loyalty.clawback", "Customer", c.id, after={"order": order.order_no, "points": take, "balance": c.loyalty_points})
    return take


# ---------------------------------------------------------------- redemption
def redemption_for(db: Session, discount_id) -> LoyaltyTransaction | None:
    return db.scalar(select(LoyaltyTransaction).where(LoyaltyTransaction.discount_id == discount_id, LoyaltyTransaction.kind == "Redeem"))


def redeem(ctx: Ctx, order: Order, points: int) -> OrderDiscount:
    from app.services.orders import calculation, ensure_editable, log_event, paid_total, recalc

    db = ctx.db
    s = settings(db, ctx.branch_id)
    if not s.get("enabled"):
        raise BusinessRuleError("LOYALTY_DISABLED", "Loyalty isn't enabled at this branch.")
    ensure_editable(order)
    if not order.customer_id:
        raise BusinessRuleError("LOYALTY_CUSTOMER_REQUIRED", "Attach the customer to the order first.")
    if paid_total(db, order) > 0:
        raise Conflict("ORDER_PARTLY_PAID", "Points can't be redeemed after payment has started.")
    step = int(s.get("redeem_step_points", 100))
    if points <= 0 or points % step:
        raise BusinessRuleError("LOYALTY_STEP", f"Redeem points in steps of {step}.", details=[{"field": "points", "issue": f"multiple of {step}"}])
    existing = db.scalar(select(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.order_item_id.is_(None), OrderDiscount.removed_at.is_(None)))
    if existing is not None:
        if redemption_for(db, existing.id):
            raise Conflict("LOYALTY_ALREADY_REDEEMED", "Points are already redeemed on this order. Remove that redemption to change it.")
        raise Conflict("LOYALTY_NOT_COMBINABLE", "This order already has an order discount (only one order-level discount applies, BR-037).")
    value = (Decimal(points) / step * Decimal(str(s.get("redeem_step_value", "1.00")))).quantize(Decimal("0.01"))
    calc = calculation(db, order)
    if value > calc.gross_total - calc.item_discount_total:
        raise BusinessRuleError("LOYALTY_EXCEEDS_ORDER", "That's more than the order amount. Redeem fewer points.")
    c = _customer(db, order.customer_id)
    now = utcnow()
    expire_due(db, now, c.id)
    if c.loyalty_points < points:
        raise BusinessRuleError("LOYALTY_INSUFFICIENT", f"The customer has {max(c.loyalty_points, 0)} points.", balance=c.loyalty_points)
    d = OrderDiscount(order_id=order.id, order_item_id=None, kind="Amount", value=value, reason=f"Loyalty: {points} points", requested_by=ctx.user_id)
    db.add(d)
    db.flush()
    taken, earliest = _consume(db, c.id, points, now)
    db.add(LoyaltyTransaction(customer_id=c.id, branch_id=ctx.branch_id, order_id=order.id, discount_id=d.id, kind="Redeem", points=-points, value=value,
                              expires_at=earliest, reason=f"Order {order.order_no}", created_by=ctx.user_id))
    c.loyalty_points -= points
    recalc(ctx, order)
    log_event(ctx, order, "loyalty_redeemed", {"points": points, "value": value})
    audit(db, ctx, "loyalty.redeem", "Customer", c.id, after={"order": order.order_no, "points": points, "value": value, "balance": c.loyalty_points})
    return d


def reverse_redemption(ctx: Ctx, discount: OrderDiscount, reason: str) -> int:
    """Points come back with the expiry of the oldest lot they were taken from."""
    db = ctx.db
    r = redemption_for(db, discount.id)
    if r is None or db.scalar(select(LoyaltyTransaction.id).where(LoyaltyTransaction.discount_id == discount.id, LoyaltyTransaction.kind == "RedeemReversal")):
        return 0
    c = _customer(db, r.customer_id)
    back = -r.points
    db.add(LoyaltyTransaction(customer_id=c.id, branch_id=r.branch_id, order_id=r.order_id, discount_id=discount.id, kind="RedeemReversal", points=back,
                              remaining=back, expires_at=r.expires_at or add_months(utcnow(), 12), reason=reason, created_by=ctx.user_id))
    c.loyalty_points += back
    db.flush()
    audit(db, ctx, "loyalty.redeem_reversal", "Customer", c.id, after={"points": back, "balance": c.loyalty_points}, reason=reason)
    return back


def on_order_cancelled(ctx: Ctx, order: Order) -> None:
    for d in ctx.db.scalars(select(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.removed_at.is_(None))):
        if redemption_for(ctx.db, d.id):
            reverse_redemption(ctx, d, f"Order {order.order_no} cancelled")


# ---------------------------------------------------------------- manual adjustment and history
def adjust(ctx: Ctx, customer_id: uuid.UUID, points: int, reason: str) -> Customer:
    ctx.require("promotions.manage")
    db = ctx.db
    c = _customer(db, customer_id)
    if c.anonymised_at or c.merged_into_id:
        raise Conflict("CUSTOMER_INACTIVE", "This customer record is merged or anonymised.")
    now = utcnow()
    if points > 0:
        db.add(LoyaltyTransaction(customer_id=c.id, branch_id=ctx.branch_id, kind="Adjust", points=points, remaining=points,
                                  expires_at=add_months(now, int(settings(db, ctx.branch_id).get("expiry_months", 12))), reason=reason, created_by=ctx.user_id))
    else:
        expire_due(db, now, c.id)
        if c.loyalty_points < -points:
            raise BusinessRuleError("LOYALTY_INSUFFICIENT", f"The customer has {max(c.loyalty_points, 0)} points.")
        _consume(db, c.id, -points, now)
        db.add(LoyaltyTransaction(customer_id=c.id, branch_id=ctx.branch_id, kind="Adjust", points=points, reason=reason, created_by=ctx.user_id))
    c.loyalty_points += points
    db.flush()
    audit(db, ctx, "loyalty.adjust", "Customer", c.id, after={"points": points, "balance": c.loyalty_points}, reason=reason)
    return c


def summary(ctx: Ctx, customer_id: uuid.UUID) -> dict:
    db = ctx.db
    c = db.get(Customer, customer_id)
    if c is None:
        raise NotFound("Customer")
    now = utcnow()
    soon = db.scalar(select(func.coalesce(func.sum(LoyaltyTransaction.remaining), 0)).where(
        LoyaltyTransaction.customer_id == c.id, LoyaltyTransaction.remaining > 0, LoyaltyTransaction.expires_at > now,
        LoyaltyTransaction.expires_at <= now + timedelta(days=30))) or 0
    nxt = db.scalar(select(func.min(LoyaltyTransaction.expires_at)).where(LoyaltyTransaction.customer_id == c.id, LoyaltyTransaction.remaining > 0,
                                                                          LoyaltyTransaction.expires_at > now))
    s = settings(db, ctx.branch_id)
    step = int(s.get("redeem_step_points", 100))
    redeemable = max(c.loyalty_points, 0) // step * step
    history = db.scalars(select(LoyaltyTransaction).where(LoyaltyTransaction.customer_id == c.id).order_by(LoyaltyTransaction.created_at.desc()).limit(100)).all()
    return {"customer_id": c.id, "balance": c.loyalty_points, "redeemable_points": redeemable,
            "redeemable_value": (Decimal(redeemable) / step * Decimal(str(s.get("redeem_step_value", "1.00")))).quantize(Decimal("0.01")),
            "expiring_within_30_days": soon, "next_expiry": nxt,
            "history": [{"kind": t.kind, "points": t.points, "remaining": t.remaining, "expires_at": t.expires_at, "order_id": t.order_id, "value": t.value,
                         "reason": t.reason, "created_at": t.created_at} for t in history]}


def move_on_merge(db: Session, from_id, to_id) -> None:
    """Customer merge: the ledger follows the surviving record (the balance is moved by the merge itself)."""
    for t in db.scalars(select(LoyaltyTransaction).where(LoyaltyTransaction.customer_id == from_id)):
        t.customer_id = to_id
