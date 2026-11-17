"""Multi-branch (SRS §6.22 BRN): branch setup, branch menu assignment, inter-branch stock transfers, consolidated figures."""
import dataclasses
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.models import (Branch, BranchMenuItem, Ingredient, InterBranchTransfer, InterBranchTransferLine, InventoryLocation, KitchenStation, MenuItem, UserBranch)
from app.services import inventory as inv
from app.services.platform import audit, next_number, notify_permission
from app.utils.money import ZERO, q4
from app.utils.timeutil import utcnow

DEFAULT_STATIONS = [("HOT", "Hot"), ("COLD", "Cold"), ("BEV", "Beverage"), ("DESSERT", "Dessert"), ("BAR", "Bar")]
DEFAULT_LOCATIONS = ("Dry store", "Chiller", "Freezer", "Bar")


def setup_branch_basics(db, branch: Branch) -> None:
    """Kitchen stations and storage locations every branch starts with (idempotent)."""
    have_st = set(db.scalars(select(KitchenStation.code).where(KitchenStation.branch_id == branch.id)))
    for i, (code, name) in enumerate(DEFAULT_STATIONS):
        if code not in have_st:
            db.add(KitchenStation(branch_id=branch.id, code=code, name=name, is_default=i == 0, warn_minutes=10, critical_minutes=20))
    have_loc = set(db.scalars(select(InventoryLocation.name).where(InventoryLocation.branch_id == branch.id)))
    for name in DEFAULT_LOCATIONS:
        if name not in have_loc:
            db.add(InventoryLocation(branch_id=branch.id, name=name))
    db.flush()


def branch_out(b: Branch) -> dict:
    return {k: getattr(b, k) for k in ("id", "code", "name_en", "name_km", "address", "phone", "timezone", "day_end_time", "opening_hours", "is_active")}


def create_branch(ctx: Ctx, data: dict) -> Branch:
    """FR-BRN-001. The creator is assigned to the new branch; other users are assigned through /users."""
    db = ctx.db
    if db.scalar(select(Branch.id).where(Branch.restaurant_id == ctx.branch.restaurant_id, func.lower(Branch.code) == data["code"].lower())):
        raise Conflict("BRANCH_CODE_EXISTS", "A branch with this code already exists.")
    b = Branch(restaurant_id=ctx.branch.restaurant_id, **data)
    db.add(b)
    db.flush()
    setup_branch_basics(db, b)
    db.add(UserBranch(user_id=ctx.user_id, branch_id=b.id, is_default=False))
    db.flush()
    db.refresh(ctx.user)
    audit(db, ctx, "branch.create", "Branch", b.id, after=branch_out(b))
    return b


def set_menu_assignment(ctx: Ctx, item: MenuItem, assigned: bool) -> BranchMenuItem:
    """FR-BRN-003: sell or stop selling an item at the current branch (restaurant-level default is 'sold everywhere')."""
    db = ctx.db
    bmi = db.get(BranchMenuItem, (ctx.branch_id, item.id), with_for_update=True)
    if bmi is None:
        bmi = BranchMenuItem(branch_id=ctx.branch_id, menu_item_id=item.id)
        db.add(bmi)
    before = bmi.is_assigned
    bmi.is_assigned = assigned
    db.flush()
    audit(db, ctx, "menu.branch_assignment", "MenuItem", item.id, before={"assigned": before}, after={"assigned": assigned, "branch": ctx.branch.code})
    return bmi


# ---------------------------------------------------------------- inter-branch transfers (FR-BRN-006)
def _location(ctx: Ctx, location_id: uuid.UUID, branch_id: uuid.UUID) -> InventoryLocation:
    loc = ctx.db.get(InventoryLocation, location_id)
    if loc is None or loc.branch_id != branch_id or not loc.is_active:
        raise NotFound("Location")
    return loc


def get_transfer(ctx: Ctx, transfer_id: uuid.UUID, lock: bool = False) -> InterBranchTransfer:
    stmt = select(InterBranchTransfer).where(InterBranchTransfer.id == transfer_id,
                                             or_(InterBranchTransfer.from_branch_id == ctx.branch_id, InterBranchTransfer.to_branch_id == ctx.branch_id))
    t = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if t is None:
        raise NotFound("Transfer")  # other branches' transfers look like 404 (BR-025)
    return t


def dispatch(ctx: Ctx, to_branch_id: uuid.UUID, from_location_id: uuid.UUID, lines: list[dict], note: str | None) -> InterBranchTransfer:
    """Stock leaves the source branch now (TRANSFER_OUT at weighted average cost) and is in transit until received."""
    ctx.require("inventory.manage")
    db = ctx.db
    to_branch = db.get(Branch, to_branch_id)
    if to_branch is None or not to_branch.is_active or to_branch.restaurant_id != ctx.branch.restaurant_id:
        raise NotFound("Branch")
    if to_branch.id == ctx.branch_id:
        raise BusinessRuleError("TRANSFER_SAME_BRANCH", "Use a location transfer to move stock within this branch.")
    _location(ctx, from_location_id, ctx.branch_id)
    t = InterBranchTransfer(transfer_no=f"IBT-{ctx.branch.code}-{next_number(db, ctx.branch_id, 'IBT', 'IBT'):06d}", from_branch_id=ctx.branch_id,
                            from_location_id=from_location_id, to_branch_id=to_branch.id, note=note, dispatched_by=ctx.user_id, dispatched_at=utcnow())
    db.add(t)
    db.flush()
    seen = set()
    for ln in lines:
        if ln["ingredient_id"] in seen:
            raise BusinessRuleError("DUPLICATE_LINE", "Each ingredient can appear once per transfer.")
        seen.add(ln["ingredient_id"])
        ing = db.get(Ingredient, ln["ingredient_id"])
        if ing is None:
            raise NotFound("Ingredient")
        qty = inv.to_stock_qty(ctx, ing, ln["quantity"], ln["uom_id"])
        row = InterBranchTransferLine(transfer_id=t.id, ingredient_id=ing.id, qty_dispatched=qty, unit_cost=ZERO)
        db.add(row)
        db.flush()
        out = inv.post_txn(ctx, location_id=from_location_id, ingredient=ing, txn_type="TRANSFER_OUT", quantity=-qty, unit_cost=None,
                           source_type="InterBranchTransfer", source_id=t.id, source_line_id=row.id, reason=f"{t.transfer_no} to {to_branch.code}")  # no negative stock
        row.unit_cost = out.unit_cost
    db.flush()
    db.refresh(t)
    notify_permission(db, to_branch.id, "inventory.manage", "Stock", f"Transfer {t.transfer_no} is on its way",
                      f"{len(t.lines)} item(s) from {ctx.branch.name_en}. Receive it when it arrives.", "/inventory")
    audit(db, ctx, "inventory.branch_transfer_dispatch", "InterBranchTransfer", t.id,
          after={"to_branch": to_branch.code, "lines": [{"ingredient_id": x.ingredient_id, "qty": x.qty_dispatched, "unit_cost": x.unit_cost} for x in t.lines]})
    return t


def receive(ctx: Ctx, t: InterBranchTransfer, to_location_id: uuid.UUID, received: dict) -> InterBranchTransfer:
    """At the destination branch. Missing or short quantities need a reason; the shortfall is reported as a variance."""
    ctx.require("inventory.manage")
    db = ctx.db
    if t.to_branch_id != ctx.branch_id:
        raise Forbidden("Only the receiving branch can receive this transfer.", code="WRONG_BRANCH")
    if t.status != "InTransit":
        raise Conflict("TRANSFER_NOT_IN_TRANSIT", f"This transfer is {t.status.lower()}.")
    _location(ctx, to_location_id, ctx.branch_id)
    by_line = {x.id: x for x in t.lines}
    unknown = set(received) - set(by_line)
    if unknown:
        raise BusinessRuleError("TRANSFER_LINE_UNKNOWN", "A line doesn't belong to this transfer.")
    variances = []
    for ln in t.lines:
        qty, reason = received.get(ln.id, (ln.qty_dispatched, None))
        if qty > ln.qty_dispatched:
            raise BusinessRuleError("RECEIVED_EXCEEDS_DISPATCHED", "You can't receive more than was dispatched.", details=[{"field": str(ln.id), "issue": "over dispatched"}])
        if qty < ln.qty_dispatched and not reason:
            raise BusinessRuleError("VARIANCE_REASON_REQUIRED", "Give a reason for each short or missing quantity.", details=[{"field": str(ln.id), "issue": "reason required"}])
        ln.qty_received, ln.variance_reason = qty, reason if qty < ln.qty_dispatched else None
        if qty > 0:
            ing = db.get(Ingredient, ln.ingredient_id)
            inv.post_txn(ctx, location_id=to_location_id, ingredient=ing, txn_type="TRANSFER_IN", quantity=qty, unit_cost=ln.unit_cost, source_type="InterBranchTransfer",
                         source_id=t.id, source_line_id=ln.id, reason=f"{t.transfer_no} from branch")
        if qty < ln.qty_dispatched:
            variances.append({"ingredient_id": ln.ingredient_id, "short_qty": ln.qty_dispatched - qty, "value": q4((ln.qty_dispatched - qty) * ln.unit_cost), "reason": reason})
    t.status, t.to_location_id, t.received_by, t.received_at = "Received", to_location_id, ctx.user_id, utcnow()
    db.flush()
    if variances:
        value = sum((v["value"] for v in variances), ZERO)
        for b in (t.from_branch_id, t.to_branch_id):
            notify_permission(db, b, "inventory.approve", "Stock", f"Transfer {t.transfer_no} arrived short", f"{len(variances)} line(s), value {value:.2f}.", "/inventory")
    audit(db, ctx, "inventory.branch_transfer_receive", "InterBranchTransfer", t.id, after={"location_id": to_location_id, "variances": variances})
    return t


def cancel(ctx: Ctx, t: InterBranchTransfer, reason: str) -> InterBranchTransfer:
    """Source branch only, while in transit: stock goes back to the source location at the dispatch cost."""
    ctx.require("inventory.manage")
    if t.from_branch_id != ctx.branch_id:
        raise Forbidden("Only the sending branch can cancel this transfer.", code="WRONG_BRANCH")
    if t.status != "InTransit":
        raise Conflict("TRANSFER_NOT_IN_TRANSIT", f"This transfer is {t.status.lower()}.")
    for ln in t.lines:
        inv.post_txn(ctx, location_id=t.from_location_id, ingredient=ctx.db.get(Ingredient, ln.ingredient_id), txn_type="TRANSFER_IN", quantity=ln.qty_dispatched,
                     unit_cost=ln.unit_cost, source_type="InterBranchTransfer", source_id=t.id, source_line_id=ln.id, reason=f"{t.transfer_no} cancelled")
    t.status, t.cancel_reason = "Cancelled", reason
    ctx.db.flush()
    audit(ctx.db, ctx, "inventory.branch_transfer_cancel", "InterBranchTransfer", t.id, reason=reason)
    return t


def transfer_out(t: InterBranchTransfer) -> dict:
    return {k: getattr(t, k) for k in ("id", "transfer_no", "from_branch_id", "from_location_id", "to_branch_id", "to_location_id", "status", "note", "dispatched_by",
                                       "dispatched_at", "received_by", "received_at", "cancel_reason")} | {
        "lines": [{"id": x.id, "ingredient_id": x.ingredient_id, "qty_dispatched": x.qty_dispatched, "unit_cost": x.unit_cost, "qty_received": x.qty_received,
                   "variance_qty": (x.qty_dispatched - x.qty_received) if x.qty_received is not None else None, "variance_reason": x.variance_reason} for x in t.lines]}


# ---------------------------------------------------------------- consolidated figures (FR-BRN-008, FR-BRN-009, RPT-06)
def permitted_branches(ctx: Ctx, branch_ids: list[uuid.UUID] | None) -> list[Branch]:
    """Cross-branch reading needs report.cross_branch, and only covers branches the user is assigned to (BR-025)."""
    if not ctx.can("report.cross_branch"):
        raise Forbidden("Consolidated reports need the cross-branch report permission.", code="REPORT_FORBIDDEN")
    mine = [b for b in ctx.user.branches if b.is_active]
    if branch_ids:
        wanted = set(branch_ids)
        if wanted - {b.id for b in mine}:
            raise Forbidden("You don't have access to one of those branches.", code="BRANCH_FORBIDDEN")
        mine = [b for b in mine if b.id in wanted]
    return sorted(mine, key=lambda b: b.code)


def as_branch(ctx: Ctx, b: Branch) -> Ctx:
    return dataclasses.replace(ctx, branch=b)


def comparison(ctx: Ctx, start: date, end: date, branch_ids: list[uuid.UUID] | None) -> dict:
    """Per-branch sales measures (RPT-01 definitions) with a consolidated total, plus cost indicators and labour hours."""
    from sqlalchemy import and_

    from app.models import Attendance, Order
    from app.services import reports, reports_advanced

    rows = []
    for b in permitted_branches(ctx, branch_ids):
        bctx = as_branch(ctx, b)
        s = reports.sales(bctx, start, end)
        orders = reports.order_counts(bctx, start, end, s["net_sales"])
        costs = reports_advanced.cost_indicators(bctx, start, end, s["net_sales"])
        tz_start = datetime.combine(start, time.min, ZoneInfo(b.timezone))
        tz_end = datetime.combine(end, time.max, ZoneInfo(b.timezone))
        shifts = ctx.db.execute(select(Attendance.clock_in, Attendance.clock_out).where(Attendance.branch_id == b.id, Attendance.clock_out.is_not(None),
                                                                                       Attendance.clock_in.between(tz_start, tz_end))).all()
        hours = sum(((o - i).total_seconds() for i, o in shifts), 0.0) / 3600
        covers = ctx.db.scalar(select(func.coalesce(func.sum(Order.guest_count), 0)).where(and_(Order.branch_id == b.id, Order.order_status == "Completed",
                                                                                                Order.business_date.between(start, end))))
        rows.append({"branch_id": b.id, "branch": b.code, "name": b.name_en, **s, "orders": orders["completed"], "cancelled_orders": orders["cancelled"],
                     "average_order_value": orders.get("average_order_value", ZERO), "covers": covers,
                     "food_cost_percent": costs["theoretical_food_cost_percent"], "theoretical_food_cost": costs["theoretical_food_cost"],
                     "approved_expenses": costs["approved_expenses"], "labour_hours": Decimal(str(round(hours, 2)))})
    keys = ("gross_sales", "discounts", "refunds", "net_sales", "service_charges", "taxes", "delivery_fees", "theoretical_food_cost", "approved_expenses", "labour_hours")
    total = {k: sum((r[k] for r in rows), ZERO) for k in keys}
    total["orders"] = sum(r["orders"] for r in rows)
    total["covers"] = sum(r["covers"] for r in rows)
    total["average_order_value"] = (total["net_sales"] / total["orders"]).quantize(Decimal("0.01")) if total["orders"] else ZERO
    total["food_cost_percent"] = (total["theoretical_food_cost"] * 100 / total["net_sales"]).quantize(Decimal("0.01")) if total["net_sales"] else ZERO
    return {"rows": rows, "total": total}
