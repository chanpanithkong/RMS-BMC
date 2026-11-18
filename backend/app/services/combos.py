"""Combo and set meals (SRS FR-MENU-005).

A combo is a menu item of type Combo whose variant price is the combo price. Its slots (e.g. Main, Drink) list the
item variants that may fill them, each with an optional extra charge.

On an order the combo becomes a header line at 0.00 plus one child line per chosen item. The combo price (plus any
extra charges) is shared across the children in proportion to their normal prices (owner's decision: "split across
items"), so item sales reports, food cost, tax per item, kitchen routing and stock consumption all work from the chosen
items. The order total equals the combo price because the shares always add up to it.
"""
import uuid
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, NotFound
from app.models import ComboSlot, ComboSlotOption, MenuItem, MenuItemVariant, Order, OrderItem
from app.services import menu as menu_svc
from app.services.platform import audit

ZERO = Decimal("0")
CENT = Decimal("0.01")


def slots_out(db, combo_item_id: uuid.UUID) -> list[dict]:
    slots = db.scalars(select(ComboSlot).where(ComboSlot.combo_item_id == combo_item_id).order_by(ComboSlot.sort_order, ComboSlot.name_en)).all()
    out = []
    for s in slots:
        rows = db.execute(select(ComboSlotOption, MenuItemVariant, MenuItem).join(MenuItemVariant, MenuItemVariant.id == ComboSlotOption.variant_id)
                          .join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id).where(ComboSlotOption.slot_id == s.id)
                          .order_by(ComboSlotOption.sort_order, MenuItem.name_en)).all()
        out.append({"id": s.id, "name_en": s.name_en, "name_km": s.name_km, "min_select": s.min_select, "max_select": s.max_select,
                    "options": [{"id": o.id, "variant_id": v.id, "menu_item_id": i.id, "item_name_en": i.name_en, "item_name_km": i.name_km, "variant_name": v.name_en,
                                 "price_delta": o.price_delta, "available": i.is_active and v.is_active} for o, v, i in rows]})
    return out


def set_slots(ctx: Ctx, item: MenuItem, slots: list[dict]) -> list[dict]:
    """Replace the combo's slots. Orders keep their own copies (names and prices are snapshotted), so this never changes history."""
    db = ctx.db
    if item.item_type != "Combo":
        raise BusinessRuleError("NOT_A_COMBO", "Set the item type to Combo before adding slots.")
    if not slots:
        raise BusinessRuleError("COMBO_EMPTY", "A combo needs at least one slot.")
    for s in slots:
        if s["min_select"] > s["max_select"]:
            raise BusinessRuleError("VALIDATION_ERROR", f"In {s['name_en']}, the minimum can't exceed the maximum.")
        if s["max_select"] > len(s["options"]) or not s["options"]:
            raise BusinessRuleError("VALIDATION_ERROR", f"{s['name_en']} needs at least as many items as can be chosen.")
        for o in s["options"]:
            v = db.get(MenuItemVariant, o["variant_id"])
            if v is None:
                raise NotFound("Variant")
            child = db.get(MenuItem, v.menu_item_id)
            if child.restaurant_id != item.restaurant_id or child.item_type == "Combo":
                raise BusinessRuleError("VALIDATION_ERROR", f"{child.name_en} can't be part of a combo.")
    before = slots_out(db, item.id)
    old = list(db.scalars(select(ComboSlot.id).where(ComboSlot.combo_item_id == item.id)))
    if old:
        db.execute(delete(ComboSlotOption).where(ComboSlotOption.slot_id.in_(old)))
        db.execute(delete(ComboSlot).where(ComboSlot.id.in_(old)))
    for n, s in enumerate(slots):
        slot = ComboSlot(combo_item_id=item.id, name_en=s["name_en"], name_km=s.get("name_km"), sort_order=n, min_select=s["min_select"], max_select=s["max_select"])
        db.add(slot)
        db.flush()
        db.add_all([ComboSlotOption(slot_id=slot.id, variant_id=o["variant_id"], price_delta=Decimal(str(o.get("price_delta") or 0)), sort_order=k)
                    for k, o in enumerate(s["options"])])
    db.flush()
    after = slots_out(db, item.id)
    audit(db, ctx, "menu.combo_slots", "MenuItem", item.id, before={"slots": len(before)}, after={"slots": [{"name": s["name_en"], "options": len(s["options"])} for s in after]})
    return after


def split(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Share a unit price in proportion to the weights, in cents; the last share takes the rounding remainder."""
    if not weights:
        return []
    w_sum = sum(weights, ZERO)
    shares = []
    for w in weights[:-1]:
        part = (total * w / w_sum) if w_sum > 0 else total / len(weights)
        shares.append(part.quantize(CENT, rounding=ROUND_HALF_UP))
    shares.append(total - sum(shares, ZERO))
    if shares[-1] < 0:  # a heavy rounding case with tiny weights: fall back to an equal split
        each = (total / len(weights)).quantize(CENT, rounding=ROUND_HALF_UP)
        shares = [each] * (len(weights) - 1) + [total - each * (len(weights) - 1)]
    return shares


def add_combo(ctx: Ctx, order: Order, item: MenuItem, variant: MenuItemVariant, combo_price: Decimal, quantity: Decimal, choices: list[dict],
              note: str | None, seat_no: int | None, add_line) -> OrderItem:
    """Validate the choices and create the header and child lines. `add_line(item, variant, unit_price, station, extra)` creates one order line."""
    db = ctx.db
    slots = {s["id"]: s for s in slots_out(db, item.id)}
    if not slots:
        raise BusinessRuleError("COMBO_NOT_SET_UP", f"{item.name_en} has no slots yet.")
    picked: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for c in choices:
        slot = slots.get(uuid.UUID(str(c["slot_id"])))
        if slot is None:
            raise BusinessRuleError("COMBO_CHOICE_INVALID", "A choice doesn't belong to this combo.", details=[{"field": "combo", "issue": str(c["slot_id"])}])
        opt = next((o for o in slot["options"] if str(o["variant_id"]) == str(c["variant_id"])), None)
        if opt is None or not opt["available"]:
            raise BusinessRuleError("COMBO_CHOICE_INVALID", f"That item can't be chosen for {slot['name_en']}.", details=[{"field": "combo", "issue": str(c["variant_id"])}])
        picked[slot["id"]].append(opt)
    for sid, slot in slots.items():
        n = len(picked[sid])
        if n < slot["min_select"]:
            raise BusinessRuleError("COMBO_CHOICE_REQUIRED", f"Choose {slot['min_select']} for {slot['name_en']}.", details=[{"field": "combo", "issue": slot["name_en"]}])
        if n > slot["max_select"]:
            raise BusinessRuleError("COMBO_CHOICE_LIMIT", f"Choose at most {slot['max_select']} for {slot['name_en']}.", details=[{"field": "combo", "issue": slot["name_en"]}])
    chosen = [(slot, o) for sid, slot in slots.items() for o in picked[sid]]
    unit_total = combo_price + sum((o["price_delta"] for _, o in chosen), ZERO)
    children = []
    for slot, o in chosen:
        child_variant, child_item = menu_svc.variant_or_404(db, o["variant_id"])
        if reason := menu_svc.availability(db, ctx.branch_id, child_item):
            raise BusinessRuleError("ITEM_UNAVAILABLE", f"{child_item.name_en} can't be sold right now: {reason}.", details=[{"field": "combo", "issue": reason}])
        normal, _ = menu_svc.effective_price(db, child_variant.id, ctx.branch_id, order.channel, order.order_type)
        children.append((slot, child_item, child_variant, normal.price if normal else ZERO))
    shares = split(unit_total, [w for *_, w in children])
    header = add_line(item, variant, ZERO, None, {"quantity": quantity, "note": note, "seat_no": seat_no})
    for (slot, child_item, child_variant, _), share in zip(children, shares, strict=True):
        add_line(child_item, child_variant, share, child_item.station_code,
                 {"quantity": quantity, "seat_no": seat_no, "parent_item_id": header.id, "combo_slot_name": slot["name_en"]})
    return header


def children_of(order: Order, item: OrderItem) -> list[OrderItem]:
    return [i for i in order.items if i.parent_item_id == item.id]
