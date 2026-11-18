"""Promotions and promotion codes (SRS §6.16; BR-037, BR-038; FR-PROMO-004 to 010).

Promotions are stored as rows in order_discounts with promotion_id set, so the calculation engine
(services/pricing.py, BR-008) handles them exactly like manual discounts: item level first, then
order level on the remainder, never making a line negative.

Combination (BR-037):
* Candidates are ranked by priority, then by customer benefit.
* A non-combinable promotion never applies together with another promotion.
* At most one order-level discount, and one discount per item (manual discounts keep their scope).
* Everything that doesn't apply is returned with the reason (FR-PROMO-005).
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, NotFound
from app.models import Customer, MenuItem, Order, OrderDiscount, Promotion, PromotionCode, PromotionRedemption
from app.services.platform import audit
from app.utils.money import ZERO, q4
from app.utils.timeutil import utcnow

HUNDRED = Decimal(100)


@dataclass
class Candidate:
    promo: Promotion
    code_id: uuid.UUID | None
    benefit: Decimal = ZERO
    # scope -> (kind, value); scope None = order level, otherwise order item id
    discounts: dict = field(default_factory=dict)


def _local(ctx: Ctx, moment: datetime) -> datetime:
    return moment.astimezone(ZoneInfo(ctx.branch.timezone))


def ineligible_reason(ctx: Ctx, p: Promotion, order: Order, now: datetime) -> str | None:
    """BR-038 validity: dates, days, time window, branch, order type, customer segment."""
    if not p.is_active:
        return "Promotion is inactive"
    if now < p.valid_from or (p.valid_to and now >= p.valid_to):
        return "Outside the promotion's validity dates"
    local = _local(ctx, now)
    if p.days_of_week and local.weekday() not in p.days_of_week:
        return "Not valid on this day"
    if p.time_from and p.time_to:
        t = local.time()
        inside = p.time_from <= t < p.time_to if p.time_from <= p.time_to else (t >= p.time_from or t < p.time_to)
        if not inside:
            return f"Only valid {p.time_from:%H:%M}-{p.time_to:%H:%M}"
    if p.branch_ids and str(ctx.branch_id) not in p.branch_ids:
        return "Not valid at this branch"
    if p.order_types and order.order_type not in p.order_types:
        return f"Not valid for {order.order_type} orders"
    if p.classifications:
        cls = ctx.db.scalar(select(Customer.classification).where(Customer.id == order.customer_id)) if order.customer_id else None
        if cls not in p.classifications:
            return "Customer segment doesn't qualify"
    return None


def _target_items(ctx: Ctx, p: Promotion, items) -> list:
    targets = set(p.target_ids or [])
    if p.scope == "Item":
        return [i for i in items if str(i.menu_item_id) in targets]
    cats = {str(mi.id): str(mi.category_id) for mi in ctx.db.scalars(select(MenuItem).where(MenuItem.id.in_({i.menu_item_id for i in items})))}
    return [i for i in items if cats.get(str(i.menu_item_id)) in targets]


def _item_discount(p: Promotion, item) -> tuple[str, Decimal] | None:
    unit = item.unit_price_snapshot + item.modifiers_total
    gross = q4(unit * item.quantity)
    if gross <= 0:
        return None
    if p.promo_type == "Percent":
        return ("Percent", min(p.value, HUNDRED)) if p.value > 0 else None
    if p.promo_type == "Amount":
        amount = min(q4(p.value * item.quantity), gross)
    elif p.promo_type == "FixedPrice":
        amount = q4(max(unit - p.value, ZERO) * item.quantity)
    else:  # BuyXGetY, within the line: every (buy + get) units, `get` are free
        group = (p.buy_qty or 0) + (p.get_qty or 0)
        free = (int(item.quantity) // group) * (p.get_qty or 0) if group else 0
        amount = q4(unit * free)
    return ("Amount", amount) if amount > 0 else None


def _amount(kind: str, value: Decimal, base: Decimal) -> Decimal:
    return min(q4(base * value / HUNDRED) if kind == "Percent" else value, base)


def evaluate(ctx: Ctx, order: Order) -> tuple[list[Candidate], list[dict]]:
    """Pure evaluation: which promotions apply to this order now, and why the others don't."""
    from app.services.orders import live_items

    db = ctx.db
    now = utcnow()
    items = [i for i in live_items(order) if i.unit_price_snapshot + i.modifiers_total > 0 and i.parent_item_id is None]  # combo items are already a set price
    redeemed = {r.promotion_id: r.code_id for r in db.scalars(select(PromotionRedemption).where(PromotionRedemption.order_id == order.id,
                                                                                                PromotionRedemption.cancelled_at.is_(None)))}
    promos = db.scalars(select(Promotion).where(Promotion.is_active.is_(True), (Promotion.auto_apply.is_(True)) | (Promotion.id.in_(list(redeemed) or [None])))).all()
    manual = {d.order_item_id: d for d in db.scalars(select(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.removed_at.is_(None),
                                                                                OrderDiscount.promotion_id.is_(None)))}
    not_applied: list[dict] = []
    cands: list[Candidate] = []
    for p in promos:
        reason = ineligible_reason(ctx, p, order, now)
        if reason:
            not_applied.append({"promotion_id": p.id, "name": p.name, "reason": reason})
            continue
        c = Candidate(p, redeemed.get(p.id))
        if p.scope == "Order":
            c.discounts[None] = (p.promo_type, p.value)
            c.benefit = _amount(p.promo_type, p.value, sum((q4((i.unit_price_snapshot + i.modifiers_total) * i.quantity) for i in items), ZERO))
        else:
            for i in _target_items(ctx, p, items):
                d = _item_discount(p, i)
                if d:
                    c.discounts[i.id] = d
                    c.benefit += _amount(d[0], d[1], q4((i.unit_price_snapshot + i.modifiers_total) * i.quantity))
        if not c.discounts:
            not_applied.append({"promotion_id": p.id, "name": p.name, "reason": "No qualifying items on the order"})
            continue
        cands.append(c)

    cands.sort(key=lambda c: (-c.promo.priority, -c.benefit, c.promo.name))
    selected: list[Candidate] = []
    taken: dict = {scope: "a manual discount" for scope in manual}
    for c in cands:
        if selected and not c.promo.combinable:
            reason = f"Not combinable; '{selected[0].promo.name}' has higher priority or benefit"
        elif any(not s.promo.combinable for s in selected):
            reason = f"'{next(s for s in selected if not s.promo.combinable).promo.name}' can't be combined with other promotions"
        else:
            free = {k: v for k, v in c.discounts.items() if k not in taken}
            if not free:
                reason = "Only one order-level discount is allowed" if None in c.discounts else "These items already have a discount"
                reason += f" ({taken[next(iter(c.discounts))]} applies)"
            else:
                c.discounts = free
                for k in free:
                    taken[k] = f"'{c.promo.name}'"
                selected.append(c)
                continue
        not_applied.append({"promotion_id": c.promo.id, "name": c.promo.name, "reason": reason})
    return selected, not_applied


def summary(ctx: Ctx, order: Order) -> dict:
    selected, not_applied = evaluate(ctx, order)
    return {"applied": [{"promotion_id": c.promo.id, "name": c.promo.name, "code_id": c.code_id, "benefit": c.benefit,
                         "lines": [{"order_item_id": k, "kind": v[0], "value": v[1]} for k, v in c.discounts.items()]} for c in selected],
            "not_applied": not_applied}


def _release_codes(ctx: Ctx, order: Order) -> None:
    for r in ctx.db.scalars(select(PromotionRedemption).where(PromotionRedemption.order_id == order.id, PromotionRedemption.cancelled_at.is_(None))):
        _cancel_redemption(ctx, r)


def _cancel_redemption(ctx: Ctx, r: PromotionRedemption) -> None:
    r.cancelled_at = utcnow()
    if r.code_id:
        pc = ctx.db.scalar(select(PromotionCode).where(PromotionCode.id == r.code_id).with_for_update())
        pc.uses = max(pc.uses - 1, 0)


def reconcile(ctx: Ctx, order: Order) -> None:
    """Bring the order's promotion discounts in line with evaluate(). Called from orders.recalc before totals."""
    from app.services.orders import log_event, paid_total

    db = ctx.db
    if order.order_status == "Cancelled":
        _release_codes(ctx, order)
        return
    if order.order_status == "Completed" or paid_total(db, order) > 0:
        return  # discounts are frozen once payment starts
    existing = {d.order_item_id: d for d in db.scalars(select(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.removed_at.is_(None),
                                                                                  OrderDiscount.promotion_id.is_not(None)))}
    if not existing and not db.scalar(select(func.count()).select_from(Promotion).where(Promotion.is_active.is_(True))):
        return
    selected, _ = evaluate(ctx, order)
    wanted = {scope: (c.promo, kind, value) for c in selected for scope, (kind, value) in c.discounts.items()}
    removed = []
    for scope, d in existing.items():
        w = wanted.get(scope)
        if w and w[0].id == d.promotion_id and w[1] == d.kind and w[2] == d.value:
            wanted.pop(scope)
            continue
        d.removed_at = utcnow()
        removed.append({"promotion_id": d.promotion_id, "item_id": scope, "kind": d.kind, "value": d.value})
    db.flush()
    added = []
    for scope, (p, kind, value) in wanted.items():
        db.add(OrderDiscount(order_id=order.id, order_item_id=scope, kind=kind, value=value, reason=f"Promotion: {p.name}", requested_by=ctx.user_id,
                             promotion_id=p.id))
        added.append({"promotion_id": p.id, "item_id": scope, "kind": kind, "value": value})
    db.flush()
    if added or removed:  # FR-PROMO-009
        log_event(ctx, order, "promotions_changed", {"added": added, "removed": removed})
        audit(db, ctx, "promotion.apply", "Order", order.id, before={"removed": removed} if removed else None, after={"added": added} if added else None)


# ---------------------------------------------------------------- codes (FR-PROMO-006, AT-PROMO-03)
def apply_code(ctx: Ctx, order: Order, code: str) -> PromotionRedemption:
    from app.services.orders import ensure_editable, paid_total, recalc

    db = ctx.db
    ensure_editable(order)
    if paid_total(db, order) > 0:
        raise Conflict("ORDER_PARTLY_PAID", "Promotions can't change after payment has started.")
    # Row lock: concurrent redemptions of the same code are serialised (BR-038).
    pc = db.scalar(select(PromotionCode).where(func.lower(PromotionCode.code) == code.strip().lower()).with_for_update())
    if pc is None or not pc.is_active:
        raise BusinessRuleError("PROMO_CODE_INVALID", "This promotion code doesn't exist or is no longer active.")
    p = db.get(Promotion, pc.promotion_id)
    prior = db.scalar(select(PromotionRedemption).where(PromotionRedemption.code_id == pc.id, PromotionRedemption.order_id == order.id))
    if prior and prior.cancelled_at is None:
        raise Conflict("PROMO_ALREADY_APPLIED", "This code is already applied to the order.")  # FR-PROMO-010
    reason = ineligible_reason(ctx, p, order, utcnow())
    if reason:
        raise BusinessRuleError("PROMO_NOT_APPLICABLE", reason)
    if pc.max_uses is not None and pc.uses >= pc.max_uses:
        raise Conflict("PROMO_LIMIT_REACHED", "This code has no uses left.")
    if pc.max_uses_per_customer is not None:
        if not order.customer_id:
            raise BusinessRuleError("PROMO_CUSTOMER_REQUIRED", "Attach a customer to the order to use this code.")
        used = db.scalar(select(func.count()).select_from(PromotionRedemption).where(PromotionRedemption.code_id == pc.id, PromotionRedemption.customer_id == order.customer_id,
                                                                                   PromotionRedemption.cancelled_at.is_(None)))
        if used >= pc.max_uses_per_customer:
            raise Conflict("PROMO_LIMIT_REACHED", "This customer has used this code the maximum number of times.")
    pc.uses += 1
    if prior:
        prior.cancelled_at, prior.customer_id, r = None, order.customer_id, prior
    else:
        r = PromotionRedemption(promotion_id=p.id, code_id=pc.id, order_id=order.id, customer_id=order.customer_id)
        db.add(r)
    db.flush()
    recalc(ctx, order)
    applied = db.scalar(select(func.count()).select_from(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.promotion_id == p.id,
                                                                             OrderDiscount.removed_at.is_(None)))
    if not applied:  # raising rolls back the use count with the rest of the request
        why = next((x["reason"] for x in evaluate(ctx, order)[1] if x["promotion_id"] == p.id), "It doesn't apply to this order")
        raise BusinessRuleError("PROMO_NOT_APPLICABLE", why)
    audit(db, ctx, "promotion.code_redeem", "Order", order.id, after={"code": pc.code, "promotion_id": p.id, "uses": pc.uses})
    return r


def remove_code(ctx: Ctx, order: Order, redemption_id: uuid.UUID) -> None:
    from app.services.orders import ensure_editable, paid_total, recalc

    ensure_editable(order)
    if paid_total(ctx.db, order) > 0:
        raise Conflict("ORDER_PARTLY_PAID", "Promotions can't change after payment has started.")
    r = ctx.db.get(PromotionRedemption, redemption_id)
    if r is None or r.order_id != order.id or r.cancelled_at:
        raise NotFound("Promotion code on this order")
    _cancel_redemption(ctx, r)
    ctx.db.flush()
    recalc(ctx, order)
    audit(ctx.db, ctx, "promotion.code_remove", "Order", order.id, after={"redemption_id": r.id})
