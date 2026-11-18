import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, or_, select

from app.core.dependencies import Ctx, require
from app.core.exceptions import BusinessRuleError, Conflict, NotFound
from app.models import (ItemModifierGroup, KitchenStation, MenuCategory, MenuItem, MenuItemVariant, MenuSchedule, MenuScheduleItem, Modifier, ModifierGroup,
                        OrderItem, PriceList, TaxProfile)
from app.schemas.common import Message, Page
from app.schemas.menu import (ComboSlotOut, ComboSlotsIn, AttachGroupsIn, AvailabilityIn, AvailabilityOut, CategoryIn, CategoryOut, MenuItemIn, MenuItemOut, MenuItemUpdate, ModifierGroupIn,
                              ModifierGroupOut, PriceIn, PriceListIn, PriceListOut, PriceListPatch, PriceOut, ScheduleIn, ScheduleOut)
from app.services import combos
from app.services import menu as svc
from app.services.platform import audit
from app.utils.timeutil import utcnow

router = APIRouter(tags=["menu"])
View = Annotated[Ctx, Depends(require("menu.view"))]
Manage = Annotated[Ctx, Depends(require("menu.manage"))]


def item_out(ctx: Ctx, item: MenuItem, list_id: uuid.UUID | None = None, channel: str | None = None, base_code: str | None = None) -> dict:
    """With a channel, prices are what an order on that channel would be charged right now (time-based lists included)."""
    list_id = list_id or svc.price_list_id(ctx.db, base_code, ctx.branch_id)
    reason = svc.availability(ctx.db, ctx.branch_id, item)
    variants = []
    for v in item.variants:
        base = svc.current_price(ctx.db, v.id, ctx.branch_id, list_id)
        p, applied = svc.effective_price(ctx.db, v.id, ctx.branch_id, channel, None, base_code) if channel else (base, None)
        variants.append({"id": v.id, "name_en": v.name_en, "name_km": v.name_km, "portion_factor": v.portion_factor, "is_active": v.is_active, "price": p.price if p else None,
                         "regular_price": base.price if applied and base else None, "price_list": applied.name if applied else None})
    return {**{c: getattr(item, c) for c in ("id", "code", "name_en", "name_km", "description", "category_id", "item_type", "station_code", "tax_profile_id", "barcode",
                                             "image_url", "channels", "is_active", "version")},
            "category_name_en": item.category.name_en, "available": reason is None, "unavailable_reason": reason, "variants": variants,
            "modifier_groups": svc.item_groups(ctx.db, item.id), "combo_slots": combos.slots_out(ctx.db, item.id) if item.item_type == "Combo" else []}


def _item(ctx: Ctx, item_id: uuid.UUID) -> MenuItem:
    item = ctx.db.get(MenuItem, item_id)
    if item is None:
        raise NotFound("Menu item")
    return item


def _validate_refs(ctx: Ctx, category_id=None, tax_profile_id=None, station_code=None) -> None:
    if category_id and ctx.db.get(MenuCategory, category_id) is None:
        raise BusinessRuleError("VALIDATION_ERROR", "Unknown category.", details=[{"field": "category_id", "issue": "not found"}])
    if tax_profile_id and ctx.db.get(TaxProfile, tax_profile_id) is None:
        raise BusinessRuleError("VALIDATION_ERROR", "Unknown tax profile.", details=[{"field": "tax_profile_id", "issue": "not found"}])
    if station_code and not ctx.db.scalar(select(KitchenStation.id).where(KitchenStation.branch_id == ctx.branch_id, KitchenStation.code == station_code)):
        raise BusinessRuleError("VALIDATION_ERROR", "Unknown kitchen station.", details=[{"field": "station_code", "issue": "not found"}])


# ---------------------------------------------------------------- categories
@router.get("/menu-categories", response_model=list[CategoryOut])
def list_categories(ctx: View):
    return ctx.db.scalars(select(MenuCategory).where(MenuCategory.restaurant_id == ctx.branch.restaurant_id).order_by(MenuCategory.sort_order)).all()


@router.post("/menu-categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, ctx: Manage):
    cat = MenuCategory(restaurant_id=ctx.branch.restaurant_id, **body.model_dump())
    ctx.db.add(cat)
    ctx.db.flush()
    audit(ctx.db, ctx, "menu.category_create", "MenuCategory", cat.id, after=body.model_dump())
    return cat


@router.patch("/menu-categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: uuid.UUID, body: CategoryIn, ctx: Manage):
    cat = ctx.db.get(MenuCategory, category_id)
    if cat is None:
        raise NotFound("Category")
    before = {k: getattr(cat, k) for k in body.model_fields}
    for k, v in body.model_dump().items():
        setattr(cat, k, v)
    audit(ctx.db, ctx, "menu.category_update", "MenuCategory", cat.id, before=before, after=body.model_dump())
    return cat


# ---------------------------------------------------------------- items
@router.get("/menu-items", response_model=Page[MenuItemOut], summary="Search by name (EN/KM), code or barcode; filter by category, status, station")
def list_items(ctx: View, search: str | None = Query(None, min_length=1), category_id: uuid.UUID | None = None, active: bool | None = None,
               station_code: str | None = None, channel: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200)):
    stmt = select(MenuItem).where(MenuItem.restaurant_id == ctx.branch.restaurant_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(MenuItem.name_en.ilike(like), MenuItem.name_km.ilike(like), MenuItem.code.ilike(like), MenuItem.barcode == search))
    if category_id:
        stmt = stmt.where(MenuItem.category_id == category_id)
    if active is not None:
        stmt = stmt.where(MenuItem.is_active == active)
    if station_code:
        stmt = stmt.where(MenuItem.station_code == station_code)
    if channel:
        stmt = stmt.where(MenuItem.channels.any(channel))
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(MenuItem.code).offset((page - 1) * page_size).limit(page_size)).all()
    list_id = svc.price_list_id(ctx.db, None, ctx.branch_id)
    return {"data": [item_out(ctx, i, list_id) for i in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/menu-items", response_model=MenuItemOut, status_code=201)
def create_item(body: MenuItemIn, ctx: Manage):
    _validate_refs(ctx, body.category_id, body.tax_profile_id, body.station_code)
    if ctx.db.scalar(select(MenuItem.id).where(MenuItem.restaurant_id == ctx.branch.restaurant_id, MenuItem.code == body.code)):
        raise Conflict("MENU_CODE_EXISTS", "An item with this code already exists.")
    data = body.model_dump(exclude={"variants"})
    item = MenuItem(restaurant_id=ctx.branch.restaurant_id, **data)
    ctx.db.add(item)
    ctx.db.flush()
    for i, v in enumerate(body.variants):
        var = MenuItemVariant(menu_item_id=item.id, name_en=v.name_en, name_km=v.name_km, portion_factor=v.portion_factor, sort_order=i)
        ctx.db.add(var)
        ctx.db.flush()
        if v.price is not None:
            ctx.db.refresh(item)
            ctx.require("prices.manage")
            svc.add_price(ctx, item, var.id, v.price, utcnow(), None, None, None)
    ctx.db.refresh(item)
    audit(ctx.db, ctx, "menu.item_create", "MenuItem", item.id, after=body.model_dump())
    return item_out(ctx, item)


@router.get("/menu-items/{item_id}", response_model=MenuItemOut)
def get_item(item_id: uuid.UUID, ctx: View):
    return item_out(ctx, _item(ctx, item_id))


@router.get("/menu-items/{item_id}/combo-slots", response_model=list[ComboSlotOut])
def get_combo_slots(item_id: uuid.UUID, ctx: View):
    return combos.slots_out(ctx.db, _item(ctx, item_id).id)


@router.put("/menu-items/{item_id}/combo-slots", response_model=list[ComboSlotOut], summary="Replace a combo's slots (FR-MENU-005); orders already placed keep their items")
def set_combo_slots(item_id: uuid.UUID, body: ComboSlotsIn, ctx: Manage):
    return combos.set_slots(ctx, _item(ctx, item_id), body.model_dump()["slots"])


@router.patch("/menu-items/{item_id}", response_model=MenuItemOut)
def update_item(item_id: uuid.UUID, body: MenuItemUpdate, ctx: Manage):
    item = _item(ctx, item_id)
    data = body.model_dump(exclude_unset=True)
    version = data.pop("version", None)
    if version is not None and version != item.version:
        raise Conflict("VERSION_CONFLICT", "This item was changed by someone else. Reload and try again.")
    _validate_refs(ctx, data.get("category_id"), data.get("tax_profile_id"), data.get("station_code"))
    before = {k: getattr(item, k) for k in data}
    for k, v in data.items():
        setattr(item, k, v)
    ctx.db.flush()
    audit(ctx.db, ctx, "menu.item_update", "MenuItem", item.id, before=before, after=data)
    return item_out(ctx, item)


@router.delete("/menu-items/{item_id}", response_model=Message, summary="Deactivate (ordered items are never deleted, FR-MENU-011)")
def deactivate_item(item_id: uuid.UUID, ctx: Manage):
    item = _item(ctx, item_id)
    item.is_active = False
    ordered = ctx.db.scalar(select(func.count()).select_from(OrderItem).where(OrderItem.menu_item_id == item.id))
    audit(ctx.db, ctx, "menu.item_deactivate", "MenuItem", item.id, after={"is_active": False, "times_ordered": ordered})
    return {"message": "Item deactivated. Open orders keep their snapshot."}


@router.post("/menu-items/{item_id}/prices", response_model=PriceOut, status_code=201, summary="Effective-dated price (BR-048)")
def add_price(item_id: uuid.UUID, body: PriceIn, ctx: Annotated[Ctx, Depends(require("prices.manage"))]):
    p = svc.add_price(ctx, _item(ctx, item_id), body.variant_id, body.price, body.valid_from, body.valid_to, body.branch_id, body.price_list)
    return _price_out(p)


def _price_out(p) -> dict:
    return {"id": p.id, "variant_id": p.variant_id, "branch_id": p.branch_id, "price": p.price, "currency": p.currency, "valid_from": p.valid_during.lower,
            "valid_to": p.valid_during.upper, "created_at": p.created_at, "created_by": p.created_by}


@router.get("/menu-items/{item_id}/price-history", response_model=list[PriceOut])
def price_history(item_id: uuid.UUID, ctx: View):
    return [_price_out(p) for p in svc.price_history(ctx.db, _item(ctx, item_id))]


@router.post("/menu-items/{item_id}/availability", response_model=AvailabilityOut, summary="Mark sold out (86) or available again (FR-MENU-009)")
def set_availability(item_id: uuid.UUID, body: AvailabilityIn, ctx: Annotated[Ctx, Depends(require("menu.availability"))]):
    bmi = svc.set_availability(ctx, _item(ctx, item_id), body.available, body.until, body.reason)
    return {"menu_item_id": item_id, "available": body.available, "unavailable_until": bmi.unavailable_until, "reason": bmi.unavailable_reason}


@router.put("/menu-items/{item_id}/modifier-groups", response_model=MenuItemOut)
def attach_groups(item_id: uuid.UUID, body: AttachGroupsIn, ctx: Manage):
    item = _item(ctx, item_id)
    if ctx.db.scalar(select(func.count()).select_from(ModifierGroup).where(ModifierGroup.id.in_(body.group_ids))) != len(set(body.group_ids)):
        raise NotFound("Modifier group")
    ctx.db.execute(delete(ItemModifierGroup).where(ItemModifierGroup.menu_item_id == item.id))
    ctx.db.add_all([ItemModifierGroup(menu_item_id=item.id, group_id=g, sort_order=i) for i, g in enumerate(body.group_ids)])
    ctx.db.flush()
    audit(ctx.db, ctx, "menu.item_modifier_groups", "MenuItem", item.id, after={"group_ids": body.group_ids})
    return item_out(ctx, item)


# ---------------------------------------------------------------- modifiers
# ---------------------------------------------------------------- price lists (FR-MENU-008)
@router.get("/price-lists", response_model=list[PriceListOut])
def price_lists(ctx: View):
    return ctx.db.scalars(select(PriceList).order_by(PriceList.priority.desc(), PriceList.code)).all()


@router.post("/price-lists", response_model=PriceListOut, status_code=201, summary="Then add prices per item with price_list = this code")
def create_price_list(body: PriceListIn, ctx: Manage):
    if ctx.db.scalar(select(PriceList.id).where(PriceList.code == body.code)):
        raise Conflict("PRICE_LIST_EXISTS", f"A price list with code {body.code} already exists.")
    data = body.model_dump()
    data["branch_ids"] = [str(b) for b in data["branch_ids"]]
    pl = PriceList(**data)
    ctx.db.add(pl)
    ctx.db.flush()
    audit(ctx.db, ctx, "menu.price_list_create", "PriceList", pl.id, after=body.model_dump(mode="json"))
    return pl


@router.patch("/price-lists/{list_id}", response_model=PriceListOut)
def update_price_list(list_id: uuid.UUID, body: PriceListPatch, ctx: Manage):
    pl = ctx.db.get(PriceList, list_id)
    if pl is None:
        raise NotFound("Price list")
    data = body.model_dump(exclude_unset=True)
    if pl.code == "STANDARD" and set(data) - {"name"}:
        raise BusinessRuleError("STANDARD_LIST", "The Standard price list is the base for every price; only its name can change.")
    before = PriceListOut.model_validate(pl).model_dump(mode="json")
    if data.get("branch_ids") is not None:
        data["branch_ids"] = [str(b) for b in data["branch_ids"]]
    for k, v in data.items():
        setattr(pl, k, [] if v is None and k in ("days_of_week", "channels", "order_types", "branch_ids") else v)
    if (pl.time_from is None) != (pl.time_to is None):
        raise BusinessRuleError("VALIDATION_ERROR", "Give both a start and an end time, or neither.")
    if pl.days_of_week and any(d < 0 or d > 6 for d in pl.days_of_week):
        raise BusinessRuleError("VALIDATION_ERROR", "Days are 0 (Monday) to 6 (Sunday).")
    audit(ctx.db, ctx, "menu.price_list_update", "PriceList", pl.id, before=before, after=body.model_dump(mode="json", exclude_unset=True))
    return pl


@router.get("/price-lists/{list_id}/prices", summary="Prices in effect now on this list, per item variant")
def price_list_prices(list_id: uuid.UUID, ctx: View):
    pl = ctx.db.get(PriceList, list_id)
    if pl is None:
        raise NotFound("Price list")
    out = []
    rows = ctx.db.execute(select(MenuItemVariant, MenuItem).join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id)
                          .where(MenuItem.restaurant_id == ctx.branch.restaurant_id, MenuItem.is_active, MenuItemVariant.is_active).order_by(MenuItem.code))
    for v, item in rows:
        p = svc.current_price(ctx.db, v.id, ctx.branch_id, pl.id)
        if p is not None:
            out.append({"menu_item_id": item.id, "item": item.name_en, "variant_id": v.id, "variant": v.name_en, "price": p.price,
                        "valid_from": p.valid_during.lower, "valid_to": p.valid_during.upper, "branch_id": p.branch_id})
    return out


# ---------------------------------------------------------------- menu schedules (BR-003)
def _schedule_out(ctx: Ctx, s: MenuSchedule) -> dict:
    ids = list(ctx.db.scalars(select(MenuScheduleItem.menu_item_id).where(MenuScheduleItem.schedule_id == s.id)))
    return {**ScheduleOut.model_validate(s).model_dump(), "item_ids": ids}


def _set_schedule_items(ctx: Ctx, s: MenuSchedule, item_ids: list[uuid.UUID]) -> None:
    if item_ids:
        found = set(ctx.db.scalars(select(MenuItem.id).where(MenuItem.id.in_(item_ids), MenuItem.restaurant_id == ctx.branch.restaurant_id)))
        if set(item_ids) - found:
            raise NotFound("Menu item")
    ctx.db.execute(delete(MenuScheduleItem).where(MenuScheduleItem.schedule_id == s.id))
    ctx.db.add_all([MenuScheduleItem(schedule_id=s.id, menu_item_id=i) for i in dict.fromkeys(item_ids)])
    ctx.db.flush()


@router.get("/menu-schedules", response_model=list[ScheduleOut])
def schedules(ctx: View):
    rows = ctx.db.scalars(select(MenuSchedule).where(MenuSchedule.restaurant_id == ctx.branch.restaurant_id).order_by(MenuSchedule.name))
    return [_schedule_out(ctx, s) for s in rows]


@router.post("/menu-schedules", response_model=ScheduleOut, status_code=201, summary="Items on a schedule are sold only while one of their schedules is in effect")
def create_schedule(body: ScheduleIn, ctx: Manage):
    data = body.model_dump(exclude={"item_ids"})
    data["branch_ids"] = [str(b) for b in data["branch_ids"]]
    s = MenuSchedule(**data, restaurant_id=ctx.branch.restaurant_id, created_by=ctx.user_id)
    ctx.db.add(s)
    ctx.db.flush()
    _set_schedule_items(ctx, s, body.item_ids)
    audit(ctx.db, ctx, "menu.schedule_create", "MenuSchedule", s.id, after=body.model_dump(mode="json"))
    return _schedule_out(ctx, s)


@router.put("/menu-schedules/{schedule_id}", response_model=ScheduleOut, summary="Replace the schedule's rules and items")
def update_schedule(schedule_id: uuid.UUID, body: ScheduleIn, ctx: Manage):
    s = ctx.db.get(MenuSchedule, schedule_id)
    if s is None or s.restaurant_id != ctx.branch.restaurant_id:
        raise NotFound("Menu schedule")
    before = ScheduleOut.model_validate(s).model_dump(mode="json")
    for k, v in body.model_dump(exclude={"item_ids"}).items():
        setattr(s, k, [str(b) for b in v] if k == "branch_ids" else v)
    _set_schedule_items(ctx, s, body.item_ids)
    audit(ctx.db, ctx, "menu.schedule_update", "MenuSchedule", s.id, before=before, after=body.model_dump(mode="json"))
    return _schedule_out(ctx, s)


@router.get("/modifier-groups", response_model=list[ModifierGroupOut])
def list_groups(ctx: View):
    return ctx.db.scalars(select(ModifierGroup).order_by(ModifierGroup.name_en)).all()


@router.post("/modifier-groups", response_model=ModifierGroupOut, status_code=201)
def create_group(body: ModifierGroupIn, ctx: Manage):
    g = ModifierGroup(name_en=body.name_en, name_km=body.name_km, min_select=body.min_select, max_select=body.max_select)
    ctx.db.add(g)
    ctx.db.flush()
    ctx.db.add_all([Modifier(group_id=g.id, sort_order=i, **m.model_dump()) for i, m in enumerate(body.modifiers)])
    ctx.db.flush()
    ctx.db.refresh(g)
    audit(ctx.db, ctx, "menu.modifier_group_create", "ModifierGroup", g.id, after=body.model_dump())
    return g


# ---------------------------------------------------------------- POS feed
@router.get("/menu/pos", summary="Everything the POS needs: categories, sellable items, current prices, modifiers and 86 status")
def pos_menu(ctx: View, channel: str = "POS"):
    cats = ctx.db.scalars(select(MenuCategory).where(MenuCategory.restaurant_id == ctx.branch.restaurant_id, MenuCategory.is_active).order_by(MenuCategory.sort_order)).all()
    items = ctx.db.scalars(select(MenuItem).where(MenuItem.restaurant_id == ctx.branch.restaurant_id, MenuItem.is_active, MenuItem.channels.any(channel)).order_by(MenuItem.code)).all()
    list_id = svc.price_list_id(ctx.db, None, ctx.branch_id)
    return {"categories": [CategoryOut.model_validate(c) for c in cats], "items": [MenuItemOut.model_validate(item_out(ctx, i, list_id, channel)) for i in items],
            "generated_at": utcnow()}
