"""Menu catalogue, effective-dated prices and availability (SRS §6.2; BR-003, BR-026, BR-048)."""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal

from sqlalchemy import DateTime, and_, cast, or_, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, NotFound
from app.core.realtime import emit
from app.models import Branch, BranchMenuItem, ItemModifierGroup, MenuItem, MenuItemVariant, MenuPrice, MenuSchedule, MenuScheduleItem, ModifierGroup, PriceList
from app.services.platform import audit, get_setting
from app.utils.timeutil import utcnow


def price_list_id(db: Session, code: str | None, branch_id: uuid.UUID) -> uuid.UUID:
    code = code or get_setting(db, "billing", branch_id).get("default_price_list", "STANDARD")
    pl = db.scalar(select(PriceList).where(PriceList.code == code, PriceList.is_active))
    if pl is None:
        raise BusinessRuleError("CONFIG_INCOMPLETE", f"Price list {code} is not configured.")
    return pl.id


def current_price(db: Session, variant_id: uuid.UUID, branch_id: uuid.UUID, list_id: uuid.UUID, at: datetime | None = None) -> MenuPrice | None:
    at = at or utcnow()
    stmt = (select(MenuPrice).where(MenuPrice.variant_id == variant_id, MenuPrice.price_list_id == list_id,
                                    or_(MenuPrice.branch_id == branch_id, MenuPrice.branch_id.is_(None)),
                                    MenuPrice.valid_during.op("@>")(cast(at, DateTime(timezone=True))))
            .order_by(MenuPrice.branch_id.is_(None)))  # branch-specific price wins over restaurant default
    return db.scalars(stmt).first()


def _in_window(local: datetime, days: list[int] | None, t_from, t_to) -> bool:
    """Days (0 = Monday) and a time window that may pass midnight, in the branch's local time."""
    if days and local.weekday() not in days:
        return False
    if t_from and t_to:
        t = local.time()
        return t_from <= t < t_to if t_from <= t_to else (t >= t_from or t < t_to)
    return True


def local_now(db: Session, branch_id: uuid.UUID, at: datetime | None = None) -> datetime:
    b = db.get(Branch, branch_id)
    return (at or utcnow()).astimezone(ZoneInfo(b.timezone))


def list_applies(pl: PriceList, branch_id: uuid.UUID, channel: str | None, order_type: str | None, local: datetime) -> bool:
    if not (pl.is_active and pl.auto_apply):
        return False
    if pl.channels and channel not in pl.channels:
        return False
    if pl.order_types and order_type not in pl.order_types:
        return False
    if pl.branch_ids and str(branch_id) not in pl.branch_ids:
        return False
    return _in_window(local, pl.days_of_week, pl.time_from, pl.time_to)


def effective_price(db: Session, variant_id: uuid.UUID, branch_id: uuid.UUID, channel: str | None = None, order_type: str | None = None,
                    base_code: str | None = None, at: datetime | None = None) -> tuple[MenuPrice | None, PriceList | None]:
    """FR-MENU-008: the highest-priority automatic price list in effect now that has a price for the variant, else the base list.
    Returns the price and the list it came from (None = base list)."""
    at = at or utcnow()
    local = local_now(db, branch_id, at)
    for pl in db.scalars(select(PriceList).where(PriceList.is_active, PriceList.auto_apply).order_by(PriceList.priority.desc(), PriceList.code)):
        if list_applies(pl, branch_id, channel, order_type, local):
            p = current_price(db, variant_id, branch_id, pl.id, at)
            if p is not None:
                return p, pl
    return current_price(db, variant_id, branch_id, price_list_id(db, base_code, branch_id), at), None


def schedule_reason(db: Session, branch_id: uuid.UUID, item: MenuItem, at: datetime | None = None) -> str | None:
    """BR-003: an item on one or more active schedules is sellable only while at least one of them is in effect."""
    schedules = list(db.scalars(select(MenuSchedule).join(MenuScheduleItem, MenuScheduleItem.schedule_id == MenuSchedule.id)
                                .where(MenuScheduleItem.menu_item_id == item.id, MenuSchedule.is_active)))
    if not schedules:
        return None
    local = local_now(db, branch_id, at)
    for s in schedules:
        if s.branch_ids and str(branch_id) not in s.branch_ids:
            continue
        if s.date_from and local.date() < s.date_from or s.date_to and local.date() > s.date_to:
            continue
        if _in_window(local, s.days_of_week, s.time_from, s.time_to):
            return None
    return "outside its menu schedule"


def availability(db: Session, branch_id: uuid.UUID, item: MenuItem) -> str | None:
    """None when the item can be sold now; otherwise the reason (BR-003)."""
    if not item.is_active:
        return "inactive"
    bmi = db.get(BranchMenuItem, (branch_id, item.id))
    if bmi is not None and not bmi.is_assigned:
        return "not sold at this branch"
    if bmi is not None and bmi.unavailable_until and bmi.unavailable_until > utcnow():
        return bmi.unavailable_reason or "unavailable (86)"
    return schedule_reason(db, branch_id, item)


def item_groups(db: Session, item_id: uuid.UUID) -> list[ModifierGroup]:
    ids = list(db.scalars(select(ItemModifierGroup.group_id).where(ItemModifierGroup.menu_item_id == item_id).order_by(ItemModifierGroup.sort_order)))
    if not ids:
        return []
    groups = {g.id: g for g in db.scalars(select(ModifierGroup).where(ModifierGroup.id.in_(ids), ModifierGroup.is_active))}
    return [groups[i] for i in ids if i in groups]


def add_price(ctx: Ctx, item: MenuItem, variant_id: uuid.UUID, price: Decimal, valid_from: datetime, valid_to: datetime | None, branch_id: uuid.UUID | None,
              price_list_code: str | None) -> MenuPrice:
    """BR-048: effective-dated, never overwritten. An open-ended current price is closed at the new start; any other overlap is rejected."""
    db = ctx.db
    if variant_id not in {v.id for v in item.variants}:
        raise NotFound("Variant")
    if valid_to is not None and valid_to <= valid_from:
        raise BusinessRuleError("VALIDATION_ERROR", "valid_to must be after valid_from.", details=[{"field": "valid_to", "issue": "before valid_from"}])
    list_id = price_list_id(db, price_list_code, ctx.branch_id)
    new_range = Range(valid_from, valid_to)
    branch_match = MenuPrice.branch_id == branch_id if branch_id else MenuPrice.branch_id.is_(None)
    overlapping = list(db.scalars(select(MenuPrice).where(MenuPrice.variant_id == variant_id, MenuPrice.price_list_id == list_id, branch_match,
                                                          MenuPrice.valid_during.op("&&")(cast(new_range, MenuPrice.valid_during.type))).with_for_update()))
    for old in overlapping:
        if old.valid_during.upper is None and old.valid_during.lower is not None and old.valid_during.lower < valid_from:
            before = {"valid_during": str(old.valid_during)}
            old.valid_during = Range(old.valid_during.lower, valid_from)
            audit(db, ctx, "menu.price_closed", "MenuPrice", old.id, before=before, after={"valid_during": str(old.valid_during)})
        else:
            raise Conflict("PRICE_OVERLAP", "This price overlaps an existing price for the same item, price list and branch.")
    db.flush()
    row = MenuPrice(variant_id=variant_id, price_list_id=list_id, branch_id=branch_id, price=price, currency="USD", valid_during=new_range, created_by=ctx.user_id)
    db.add(row)
    db.flush()
    audit(db, ctx, "menu.price_set", "MenuItem", item.id, after={"variant_id": variant_id, "price": price, "valid_from": valid_from, "valid_to": valid_to, "branch_id": branch_id})
    return row


def set_availability(ctx: Ctx, item: MenuItem, available: bool, until: datetime | None, reason: str | None) -> BranchMenuItem:
    db = ctx.db
    bmi = db.get(BranchMenuItem, (ctx.branch_id, item.id), with_for_update=True) or BranchMenuItem(branch_id=ctx.branch_id, menu_item_id=item.id)
    db.add(bmi)
    before = {"unavailable_until": bmi.unavailable_until}
    if available:
        bmi.unavailable_until, bmi.unavailable_reason = None, None
    else:
        bmi.unavailable_until = until or end_of_business_day(ctx)
        bmi.unavailable_reason = reason or "Sold out"
    bmi.updated_by = ctx.user_id
    db.flush()
    audit(db, ctx, "menu.availability", "MenuItem", item.id, before=before, after={"available": available, "unavailable_until": bmi.unavailable_until, "reason": reason})
    emit(db, f"branch:{ctx.branch_id}", "menu.availability", {"menu_item_id": str(item.id), "available": available, "until": bmi.unavailable_until})
    from app.services import grabfood

    grabfood.on_availability(ctx, item, available)
    return bmi


def end_of_business_day(ctx: Ctx) -> datetime:
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(ctx.branch.timezone)
    day = ctx.business_date() + timedelta(days=1)
    return datetime.combine(day, ctx.branch.day_end_time, tzinfo=tz)


def price_history(db: Session, item: MenuItem) -> list[MenuPrice]:
    ids = [v.id for v in item.variants]
    return list(db.scalars(select(MenuPrice).where(MenuPrice.variant_id.in_(ids)).order_by(MenuPrice.created_at.desc()))) if ids else []


def variant_or_404(db: Session, variant_id: uuid.UUID) -> tuple[MenuItemVariant, MenuItem]:
    v = db.get(MenuItemVariant, variant_id)
    if v is None or not v.is_active:
        raise NotFound("Menu item variant")
    return v, db.get(MenuItem, v.menu_item_id)


_ = and_  # re-exported helpers for repositories
