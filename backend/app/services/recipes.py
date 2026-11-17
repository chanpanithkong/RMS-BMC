"""Recipes, food cost and ingredient consumption (SRS §6.11; BR-014, BR-015, BR-041) and advanced inventory (§6.10)."""
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.models import (Ingredient, InventoryLocation, InventoryTransaction, MenuItem, MenuItemVariant, Modifier, Order, OrderItem, OrderItemModifier, Recipe,
                        RecipeIngredient, RecipeVersion, StockBalance, StockBatch, StockCount, StockCountLine, StockTransfer, StockTransferLine)
from app.services import inventory as inv
from app.services import menu as menu_svc
from app.services.platform import audit, get_setting, next_number
from app.utils.money import ZERO, q, q4
from app.utils.timeutil import utcnow

NS = uuid.UUID("6f0c5b52-6a3e-4f37-9c84-5f1e3a1d2b10")
HUNDRED = Decimal(100)


# ---------------------------------------------------------------- recipe definition
def get_recipe(ctx: Ctx, recipe_id: uuid.UUID) -> Recipe:
    r = ctx.db.get(Recipe, recipe_id)
    if r is None:
        raise NotFound("Recipe")
    return r


def create_recipe(ctx: Ctx, variant_id: uuid.UUID | None, modifier_id: uuid.UUID | None) -> Recipe:
    if (variant_id is None) == (modifier_id is None):
        raise BusinessRuleError("RECIPE_TARGET", "A recipe belongs to exactly one menu item variant or one modifier.")
    if variant_id:
        v, item = menu_svc.variant_or_404(ctx.db, variant_id)
        name = f"{item.name_en} ({v.name_en})"
        existing = ctx.db.scalar(select(Recipe).where(Recipe.variant_id == variant_id))
    else:
        m = ctx.db.get(Modifier, modifier_id)
        if m is None:
            raise NotFound("Modifier")
        name = f"Modifier: {m.name_en}"
        existing = ctx.db.scalar(select(Recipe).where(Recipe.modifier_id == modifier_id))
    if existing:
        raise Conflict("RECIPE_EXISTS", "This item already has a recipe. Add a new version instead.", recipe_id=str(existing.id))
    r = Recipe(variant_id=variant_id, modifier_id=modifier_id, name=name)
    ctx.db.add(r)
    ctx.db.flush()
    audit(ctx.db, ctx, "recipe.create", "Recipe", r.id, after={"name": name})
    return r


def _validate_lines(ctx: Ctx, lines: list[dict]) -> None:
    for ln in lines:
        ing = ctx.db.get(Ingredient, ln["ingredient_id"])
        if ing is None:
            raise NotFound("Ingredient")
        inv.to_stock_qty(ctx, ing, Decimal("1"), ln["uom_id"])  # raises UNIT_INCOMPATIBLE (BR-015, AT-RCP-02)


def add_version(ctx: Ctx, recipe: Recipe, yield_qty: Decimal, lines: list[dict], method_text: str | None) -> RecipeVersion:
    _validate_lines(ctx, lines)
    no = (max((v.version_no for v in recipe.versions), default=0)) + 1
    v = RecipeVersion(recipe_id=recipe.id, version_no=no, yield_qty=yield_qty, method_text=method_text, created_by=ctx.user_id)
    ctx.db.add(v)
    ctx.db.flush()
    ctx.db.add_all([RecipeIngredient(version_id=v.id, **ln) for ln in lines])
    ctx.db.flush()
    ctx.db.refresh(v)
    audit(ctx.db, ctx, "recipe.version_create", "Recipe", recipe.id, after={"version": no, "lines": len(lines)})
    return v


def update_draft(ctx: Ctx, v: RecipeVersion, yield_qty: Decimal | None, lines: list[dict] | None, method_text: str | None) -> RecipeVersion:
    if v.status != "Draft":
        raise Conflict("VERSION_PUBLISHED", "Published versions can't be changed. Create a new version.")  # FR-RCP-003
    if lines is not None:
        _validate_lines(ctx, lines)
        for old in list(v.lines):
            ctx.db.delete(old)
        ctx.db.flush()
        ctx.db.add_all([RecipeIngredient(version_id=v.id, **ln) for ln in lines])
    if yield_qty is not None:
        v.yield_qty = yield_qty
    if method_text is not None:
        v.method_text = method_text
    ctx.db.flush()
    ctx.db.refresh(v)
    audit(ctx.db, ctx, "recipe.version_update", "RecipeVersion", v.id, after={"lines": len(v.lines)})
    return v


def publish(ctx: Ctx, v: RecipeVersion, effective_from: datetime | None) -> RecipeVersion:
    if v.status != "Draft":
        raise Conflict("VERSION_PUBLISHED", "This version is already published.")
    if not v.lines:
        raise BusinessRuleError("RECIPE_EMPTY", "Add at least one ingredient before publishing.")
    eff = effective_from or utcnow()
    if eff < utcnow() - timedelta(minutes=5):
        raise BusinessRuleError("EFFECTIVE_IN_PAST", "A recipe version takes effect now or later.")
    if ctx.db.scalar(select(RecipeVersion.id).where(RecipeVersion.recipe_id == v.recipe_id, RecipeVersion.status == "Published", RecipeVersion.effective_from == eff)):
        raise Conflict("VERSION_EFFECTIVE_CONFLICT", "Another version takes effect at the same time.")
    v.status, v.effective_from, v.published_by, v.published_at = "Published", eff, ctx.user_id, utcnow()
    audit(ctx.db, ctx, "recipe.publish", "RecipeVersion", v.id, after={"version": v.version_no, "effective_from": eff})  # FR-RCP-009
    return v


def active_version(db, recipe_id: uuid.UUID, at: datetime | None = None) -> RecipeVersion | None:
    return db.scalar(select(RecipeVersion).where(RecipeVersion.recipe_id == recipe_id, RecipeVersion.status == "Published", RecipeVersion.effective_from <= (at or utcnow()))
                     .order_by(RecipeVersion.effective_from.desc()).limit(1))


def gross_per_portion(ctx: Ctx, v: RecipeVersion, line: RecipeIngredient) -> Decimal:
    """BR-015 / FR-RCP-005: gross = net ÷ ((1 − prep loss)(1 − cook loss)), in stock unit, 4 dp."""
    ing = ctx.db.get(Ingredient, line.ingredient_id)
    retained = (1 - line.prep_loss_pct / HUNDRED) * (1 - line.cook_loss_pct / HUNDRED)
    gross = line.quantity / retained / v.yield_qty
    return inv.to_stock_qty(ctx, ing, gross, line.uom_id)


def branch_avg_cost(ctx: Ctx, ingredient_id: uuid.UUID) -> Decimal | None:
    qty, value = ctx.db.execute(select(func.sum(StockBalance.quantity), func.sum(StockBalance.quantity * StockBalance.avg_cost))
                                .where(StockBalance.branch_id == ctx.branch_id, StockBalance.ingredient_id == ingredient_id, StockBalance.quantity > 0)).one()
    if qty:
        return (value / qty).quantize(Decimal("0.000001"))
    last = ctx.db.scalar(select(StockBalance.avg_cost).where(StockBalance.branch_id == ctx.branch_id, StockBalance.ingredient_id == ingredient_id, StockBalance.avg_cost > 0).limit(1))
    return last


def version_cost(ctx: Ctx, v: RecipeVersion) -> dict:
    """FR-RCP-007: cost per portion from current weighted average costs, with the calculation time."""
    lines, total, incomplete = [], ZERO, False
    for ln in v.lines:
        qty = gross_per_portion(ctx, v, ln)
        cost = branch_avg_cost(ctx, ln.ingredient_id)
        if cost is None:
            incomplete = True
        line_cost = q4(qty * (cost or ZERO))
        total += line_cost
        ing = ctx.db.get(Ingredient, ln.ingredient_id)
        lines.append({"ingredient_id": ln.ingredient_id, "ingredient": ing.name_en, "gross_qty_stock_unit": qty, "stock_unit": ing.stock_uom.code, "avg_cost": cost,
                      "cost": line_cost, "cost_missing": cost is None})
    return {"version_id": v.id, "version_no": v.version_no, "cost_per_portion": q(total), "incomplete": incomplete, "lines": lines, "calculated_at": utcnow()}


def food_cost(ctx: Ctx, recipe: Recipe) -> dict:
    """FR-RCP-008, AT-RCP-03: food cost % = recipe cost ÷ selling price excluding tax."""
    v = active_version(ctx.db, recipe.id)
    if v is None:
        raise Conflict("NO_ACTIVE_VERSION", "This recipe has no published version in effect.")
    cost = version_cost(ctx, v)
    out = {"recipe_id": recipe.id, "name": recipe.name, **cost}
    if recipe.variant_id:
        price = menu_svc.current_price(ctx.db, recipe.variant_id, ctx.branch_id, menu_svc.price_list_id(ctx.db, None, ctx.branch_id))
        selling = price.price if price else None
        target = Decimal(str(get_setting(ctx.db, "recipes", ctx.branch_id)["target_food_cost_pct"]))
        pct = (cost["cost_per_portion"] * HUNDRED / selling).quantize(Decimal("0.1")) if selling else None
        out.update({"selling_price_ex_tax": selling, "food_cost_pct": pct, "gross_margin": q(selling - cost["cost_per_portion"]) if selling else None,
                    "target_pct": target, "above_target": bool(pct is not None and pct > target)})
    return out


def unmapped_items(ctx: Ctx, days: int = 30) -> list[dict]:
    """FR-RCP-010: menu items sold without a recipe in effect."""
    since = ctx.business_date() - timedelta(days=days)
    sold = ctx.db.execute(select(OrderItem.variant_id, OrderItem.item_name_en_snapshot, OrderItem.variant_name_snapshot, func.sum(OrderItem.quantity))
                          .join(Order).where(Order.branch_id == ctx.branch_id, Order.business_date >= since, OrderItem.item_status != "Cancelled")
                          .group_by(OrderItem.variant_id, OrderItem.item_name_en_snapshot, OrderItem.variant_name_snapshot)).all()
    out = []
    for vid, name, variant, qty in sold:
        r = ctx.db.scalar(select(Recipe).where(Recipe.variant_id == vid))
        if r is None or active_version(ctx.db, r.id) is None:
            out.append({"variant_id": vid, "item": name, "variant": variant, "quantity_sold": qty, "recipe_id": r.id if r else None})
    return out


# ---------------------------------------------------------------- consumption (BR-014, FR-RCP-006)
def consumption_location(ctx: Ctx, ing: Ingredient) -> uuid.UUID:
    if ing.default_location_id:
        return ing.default_location_id
    loc = ctx.db.scalar(select(InventoryLocation.id).where(InventoryLocation.branch_id == ctx.branch_id, InventoryLocation.is_active).order_by(InventoryLocation.name).limit(1))
    if loc is None:
        raise BusinessRuleError("CONFIG_INCOMPLETE", "No inventory location is configured for this branch.")
    return loc


def _recipe_lines_for_item(ctx: Ctx, item: OrderItem) -> list[tuple[RecipeVersion, RecipeIngredient, Decimal, str]]:
    """(version, line, multiplier, key) for the item's variant recipe and its modifier recipes."""
    out = []
    variant = ctx.db.get(MenuItemVariant, item.variant_id)
    r = ctx.db.scalar(select(Recipe).where(Recipe.variant_id == item.variant_id))
    if r and (v := active_version(ctx.db, r.id, item.sent_at)):
        out += [(v, ln, variant.portion_factor * item.quantity, f"v:{v.id}") for ln in v.lines]
    for m in ctx.db.scalars(select(OrderItemModifier).where(OrderItemModifier.order_item_id == item.id)):
        mr = ctx.db.scalar(select(Recipe).where(Recipe.modifier_id == m.modifier_id))
        if mr and (mv := active_version(ctx.db, mr.id, item.sent_at)):
            out += [(mv, ln, Decimal(m.quantity) * item.quantity, f"m:{m.id}") for ln in mv.lines]
    return out


def post_consumption(ctx: Ctx, items: list[OrderItem]) -> int:
    """Posted exactly once per order item and ingredient (unique source line). Items without a recipe are reported as unmapped."""
    if get_setting(ctx.db, "inventory", ctx.branch_id).get("consumption_point", "Send") != "Send":
        return 0
    allow_negative = bool(get_setting(ctx.db, "inventory", ctx.branch_id).get("allow_negative_from_sales", True))
    posted = 0
    for item in items:
        totals: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        versions = {}
        for v, ln, mult, key in _recipe_lines_for_item(ctx, item):
            totals[(ln.ingredient_id, key)] += gross_per_portion(ctx, v, ln) * mult
            versions[key] = v.version_no
        for (ing_id, key), qty in totals.items():
            ing = ctx.db.get(Ingredient, ing_id)
            source_line = uuid.uuid5(NS, f"{item.id}:{ing_id}:{key}")
            if ctx.db.scalar(select(InventoryTransaction.id).where(InventoryTransaction.source_type == "OrderItem", InventoryTransaction.source_line_id == source_line,
                                                                   InventoryTransaction.txn_type == "SALE_CONSUMPTION")):
                continue
            inv.post_txn(ctx, location_id=consumption_location(ctx, ing), ingredient=ing, txn_type="SALE_CONSUMPTION", quantity=-q4(qty), unit_cost=None,
                         source_type="OrderItem", source_id=item.id, source_line_id=source_line, reason=f"Recipe v{versions[key]}", allow_negative=allow_negative)
            posted += 1
    return posted


def reverse_consumption(ctx: Ctx, item: OrderItem, reason: str) -> int:
    """BR-014: cancellation before preparation (or a reusable prepared item) puts the ingredients back."""
    n = 0
    for t in ctx.db.scalars(select(InventoryTransaction).where(InventoryTransaction.source_type == "OrderItem", InventoryTransaction.source_id == item.id,
                                                               InventoryTransaction.txn_type == "SALE_CONSUMPTION")):
        if ctx.db.scalar(select(InventoryTransaction.id).where(InventoryTransaction.source_type == "OrderItem", InventoryTransaction.source_line_id == t.source_line_id,
                                                               InventoryTransaction.txn_type == "SALE_REVERSAL")):
            continue
        ing = ctx.db.get(Ingredient, t.ingredient_id)
        inv.post_txn(ctx, location_id=t.location_id, ingredient=ing, txn_type="SALE_REVERSAL", quantity=-t.quantity, unit_cost=t.unit_cost, source_type="OrderItem",
                     source_id=item.id, source_line_id=t.source_line_id, reason=reason, allow_negative=True)
        n += 1
    return n


def menu_item_wastage(ctx: Ctx, variant_id: uuid.UUID, quantity: Decimal, reason: str) -> list[InventoryTransaction]:
    """FR-INV-009: wastage of prepared menu items converted to ingredients with the active recipe."""
    ctx.require("inventory.wastage")
    r = ctx.db.scalar(select(Recipe).where(Recipe.variant_id == variant_id))
    v = active_version(ctx.db, r.id) if r else None
    if v is None:
        raise Conflict("NO_ACTIVE_VERSION", "This item has no recipe in effect, so its ingredients can't be calculated.")
    variant = ctx.db.get(MenuItemVariant, variant_id)
    doc_id = uuid.uuid4()
    txns = []
    for ln in v.lines:
        ing = ctx.db.get(Ingredient, ln.ingredient_id)
        qty = q4(gross_per_portion(ctx, v, ln) * variant.portion_factor * quantity)
        txns.append(inv.post_txn(ctx, location_id=consumption_location(ctx, ing), ingredient=ing, txn_type="WASTE", quantity=-qty, unit_cost=None, source_type="MenuItemWastage",
                                 source_id=doc_id, source_line_id=uuid.uuid5(NS, f"{doc_id}:{ln.id}"), reason=reason, allow_negative=True))
    audit(ctx.db, ctx, "inventory.menu_wastage", "MenuItemVariant", variant_id, after={"quantity": quantity, "ingredients": len(txns)}, reason=reason)
    return txns


# ---------------------------------------------------------------- stock counts (FR-INV-010, AT-INV-03)
def create_count(ctx: Ctx, location_id: uuid.UUID, ingredient_ids: list[uuid.UUID] | None) -> StockCount:
    ctx.require("inventory.manage")
    loc = ctx.db.get(InventoryLocation, location_id)
    if loc is None or loc.branch_id != ctx.branch_id:
        raise NotFound("Location")
    if not ingredient_ids:
        ingredient_ids = list(ctx.db.scalars(select(StockBalance.ingredient_id).where(StockBalance.location_id == location_id)))
    if not ingredient_ids:
        raise BusinessRuleError("COUNT_EMPTY", "Choose the ingredients to count.")
    c = StockCount(branch_id=ctx.branch_id, count_no=f"CNT-{next_number(ctx.db, ctx.branch_id, 'COUNT', 'C'):06d}", location_id=location_id, counted_by=ctx.user_id)
    ctx.db.add(c)
    ctx.db.flush()
    ctx.db.add_all([StockCountLine(count_id=c.id, ingredient_id=i) for i in dict.fromkeys(ingredient_ids)])
    ctx.db.flush()
    ctx.db.refresh(c)
    return c


def count_out(ctx: Ctx, c: StockCount) -> dict:
    blind = c.status == "Draft"  # system quantities stay hidden until the count is submitted
    lines = []
    for ln in c.lines:
        ing = ctx.db.get(Ingredient, ln.ingredient_id)
        row = {"ingredient_id": ln.ingredient_id, "ingredient": ing.name_en, "unit": ing.stock_uom.code, "counted_qty": ln.counted_qty}
        if not blind:
            row.update({"system_qty": ln.system_qty, "variance": (ln.counted_qty - ln.system_qty) if ln.counted_qty is not None and ln.system_qty is not None else None,
                        "variance_value": q((ln.counted_qty - ln.system_qty) * (ln.unit_cost or ZERO)) if ln.counted_qty is not None and ln.system_qty is not None else None})
        lines.append(row)
    return {"id": c.id, "count_no": c.count_no, "location_id": c.location_id, "status": c.status, "counted_by": c.counted_by, "approved_by": c.approved_by,
            "progress": f"{sum(1 for ln in c.lines if ln.counted_qty is not None)}/{len(c.lines)}", "lines": lines}


def enter_counts(ctx: Ctx, c: StockCount, counts: dict[uuid.UUID, tuple[Decimal, uuid.UUID]]) -> StockCount:
    if c.status != "Draft":
        raise Conflict("COUNT_SUBMITTED", "This count was already submitted.")
    by_ing = {ln.ingredient_id: ln for ln in c.lines}
    for ing_id, (qty, uom_id) in counts.items():
        if ing_id not in by_ing:
            raise BusinessRuleError("COUNT_LINE_UNKNOWN", "That ingredient isn't on this count sheet.")
        if qty < 0:
            raise BusinessRuleError("VALIDATION_ERROR", "Counts can't be negative.")
        by_ing[ing_id].counted_qty = inv.to_stock_qty(ctx, ctx.db.get(Ingredient, ing_id), qty, uom_id)
    return c  # autosaved draft


def submit_count(ctx: Ctx, c: StockCount) -> StockCount:
    if c.status != "Draft":
        raise Conflict("COUNT_SUBMITTED", "This count was already submitted.")
    if any(ln.counted_qty is None for ln in c.lines):
        raise BusinessRuleError("COUNT_INCOMPLETE", "Count every line before submitting.")
    for ln in c.lines:
        bal = ctx.db.get(StockBalance, (c.location_id, ln.ingredient_id))
        ln.system_qty, ln.unit_cost = (bal.quantity, bal.avg_cost) if bal else (ZERO, ZERO)
    c.status, c.submitted_at = "Submitted", utcnow()
    audit(ctx.db, ctx, "inventory.count_submit", "StockCount", c.id)
    return c


def approve_count(ctx: Ctx, c: StockCount, approve: bool) -> StockCount:
    ctx.require("inventory.approve")
    if c.status != "Submitted":
        raise Conflict("COUNT_NOT_SUBMITTED", "This count isn't waiting for approval.")
    if c.counted_by == ctx.user_id:
        raise Forbidden("You can't approve your own count.", code="SELF_APPROVAL")
    c.approved_by = ctx.user_id
    if not approve:
        c.status = "Rejected"
        return c
    for ln in c.lines:
        diff = ln.counted_qty - ln.system_qty
        if diff:
            inv.post_txn(ctx, location_id=c.location_id, ingredient=ctx.db.get(Ingredient, ln.ingredient_id), txn_type="COUNT_ADJUSTMENT", quantity=diff, unit_cost=ln.unit_cost,
                         source_type="StockCount", source_id=c.id, source_line_id=ln.id, reason=f"Count {c.count_no}", allow_negative=True)
    c.status, c.posted_at = "Posted", utcnow()
    audit(ctx.db, ctx, "inventory.count_post", "StockCount", c.id, after={"lines": len(c.lines)})
    return c


# ---------------------------------------------------------------- transfers between locations (FR-INV-007)
def transfer(ctx: Ctx, from_id: uuid.UUID, to_id: uuid.UUID, lines: list[dict]) -> StockTransfer:
    ctx.require("inventory.manage")
    if from_id == to_id:
        raise BusinessRuleError("TRANSFER_SAME_LOCATION", "Choose two different locations.")
    for lid in (from_id, to_id):
        loc = ctx.db.get(InventoryLocation, lid)
        if loc is None or loc.branch_id != ctx.branch_id:
            raise NotFound("Location")
    t = StockTransfer(branch_id=ctx.branch_id, transfer_no=f"TRF-{next_number(ctx.db, ctx.branch_id, 'TRANSFER', 'T'):06d}", from_location_id=from_id, to_location_id=to_id,
                      created_by=ctx.user_id)
    ctx.db.add(t)
    ctx.db.flush()
    for ln in lines:
        row = StockTransferLine(transfer_id=t.id, **ln)
        ctx.db.add(row)
        ctx.db.flush()
        ing = ctx.db.get(Ingredient, ln["ingredient_id"])
        qty = inv.to_stock_qty(ctx, ing, ln["quantity"], ln["uom_id"])
        out = inv.post_txn(ctx, location_id=from_id, ingredient=ing, txn_type="TRANSFER_OUT", quantity=-qty, unit_cost=None, source_type="StockTransfer", source_id=t.id,
                           source_line_id=row.id, reason=t.transfer_no)  # no negative stock (BR-040)
        inv.post_txn(ctx, location_id=to_id, ingredient=ing, txn_type="TRANSFER_IN", quantity=qty, unit_cost=out.unit_cost, source_type="StockTransfer", source_id=t.id,
                     source_line_id=row.id, reason=t.transfer_no)
    t.status, t.posted_at = "Posted", utcnow()
    ctx.db.flush()
    ctx.db.refresh(t)
    audit(ctx.db, ctx, "inventory.transfer", "StockTransfer", t.id, after={"from": from_id, "to": to_id, "lines": len(lines)})
    return t


# ---------------------------------------------------------------- batches and expiry (FR-INV-011)
def record_batch(ctx: Ctx, location_id, ingredient_id, batch_no: str | None, expiry, qty: Decimal, source_type: str, source_line_id) -> None:
    if batch_no or expiry:
        ctx.db.add(StockBatch(branch_id=ctx.branch_id, location_id=location_id, ingredient_id=ingredient_id, batch_no=batch_no or "-", expiry_date=expiry,
                              quantity_received=qty, source_type=source_type, source_line_id=source_line_id))


def expiring(ctx: Ctx, days: int) -> list[dict]:
    limit = ctx.business_date() + timedelta(days=days)
    rows = ctx.db.execute(select(StockBatch, Ingredient.name_en, InventoryLocation.name).join(Ingredient, Ingredient.id == StockBatch.ingredient_id)
                          .join(InventoryLocation, InventoryLocation.id == StockBatch.location_id)
                          .where(StockBatch.branch_id == ctx.branch_id, StockBatch.expiry_date.is_not(None), StockBatch.expiry_date <= limit)
                          .order_by(StockBatch.expiry_date)).all()
    return [{"batch_no": b.batch_no, "ingredient": n, "location": loc, "expiry_date": b.expiry_date, "quantity_received": b.quantity_received,
             "expired": b.expiry_date < ctx.business_date()} for b, n, loc in rows]


_ = MenuItem
