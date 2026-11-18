"""Orders, POS and kitchen routing (SRS §6.3–6.6; BR-001, BR-003–BR-007, BR-009, BR-026, BR-031, BR-032, BR-037, BR-052)."""
import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.orm import Session

from app.core.dependencies import Ctx
from app.core.exceptions import AppError, BusinessRuleError, Conflict, NotFound
from app.core.realtime import emit
from app.models import (Bill, KitchenStation, KitchenTicket, KitchenTicketItem, MenuItem, Modifier, Order, OrderDiscount, OrderEvent, OrderItem, OrderItemModifier,
                        RestaurantTable, TaxProfileRate)
from app.services import menu as menu_svc
from app.services.platform import audit, consume_approval, get_setting, next_number, notify_users
from app.services.pricing import ChargeRule, LineInput, calculate, discount_amount
from app.utils.money import ZERO
from app.utils.timeutil import utcnow

ACTIVE_KITCHEN = ("Sent", "InPreparation")
DELIVERED = ("Served", "Collected")


# ---------------------------------------------------------------- helpers
def get_order(ctx: Ctx, order_id: uuid.UUID, lock: bool = False) -> Order:
    stmt = select(Order).where(Order.id == order_id, Order.branch_id == ctx.branch_id)  # out-of-scope ids are 404 (BR-025)
    if lock:
        stmt = stmt.with_for_update()
    order = ctx.db.scalar(stmt)
    if order is None:
        raise NotFound("Order")
    if not ctx.can("orders.view_all") and order.server_user_id != ctx.user_id:
        raise NotFound("Order")  # own orders only by default (§4.3 WAITER "(o)")
    return order


def check_version(order: Order, expected: int | None) -> None:
    if expected is not None and expected != order.version:
        raise Conflict("VERSION_CONFLICT", "This order was changed on another device. Reload and try again.", current_version=order.version)


def ensure_editable(order: Order) -> None:
    if order.order_status in ("Completed", "Cancelled"):
        raise Conflict("ORDER_CLOSED", f"This order is {order.order_status.lower()} and can't be changed.")


def ensure_day_open(ctx: Ctx) -> None:
    closed = get_setting(ctx.db, "day_end", ctx.branch_id).get("closed_dates", [])
    if ctx.business_date().isoformat() in closed:
        raise Conflict("BUSINESS_DAY_CLOSED", "This business day is closed. Transactions belong to the next business day after the day-end time.")


def log_event(ctx: Ctx, order: Order, event_type: str, data: dict | None = None) -> None:
    from fastapi.encoders import jsonable_encoder

    ctx.db.add(OrderEvent(order_id=order.id, branch_id=order.branch_id, event_type=event_type, data=jsonable_encoder(data) if data else None, user_id=ctx.user_id))


def live_items(order: Order) -> list[OrderItem]:
    return [i for i in order.items if i.item_status != "Cancelled"]


def paid_total(db: Session, order: Order) -> Decimal:
    return db.scalar(select(func.coalesce(func.sum(Bill.paid_total - Bill.refunded_total), 0)).where(Bill.order_id == order.id, Bill.status != "Void")) or ZERO


def charge_rules(db: Session, profile_ids: set) -> dict:
    now = utcnow()
    rules: dict = defaultdict(list)
    if not profile_ids:
        return rules
    rows = db.scalars(select(TaxProfileRate).where(TaxProfileRate.profile_id.in_(profile_ids), TaxProfileRate.valid_during.op("@>")(cast(now, DateTime(timezone=True)))))
    for r in rows:
        rules[r.profile_id].append(ChargeRule(r.charge_kind, r.name, r.rate, r.base_rule, r.inclusive, tuple(r.applies_to_order_types), r.id))
    return rules


def calculation(db: Session, order: Order):
    items = live_items(order)
    discounts = {d.order_item_id: d for d in db.scalars(select(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.removed_at.is_(None)))}
    lines = [LineInput(str(i.id), i.unit_price_snapshot, i.modifiers_total, i.quantity, i.tax_profile_id_snapshot,
                       discounts[i.id].kind if i.id in discounts else None, discounts[i.id].value if i.id in discounts else None) for i in items]
    od = discounts.get(None)
    fee_rules = []
    if order.order_type == "Delivery" and order.delivery_fee > 0:
        from app.models import Delivery, DeliveryZone

        profile = db.scalar(select(DeliveryZone.tax_profile_id).join(Delivery, Delivery.zone_id == DeliveryZone.id).where(Delivery.order_id == order.id))
        fee_rules = charge_rules(db, {profile}).get(profile, []) if profile else []
    return calculate(lines, order.order_type, charge_rules(db, {i.tax_profile_id_snapshot for i in items}), od.kind if od else None, od.value if od else None,
                     order.delivery_fee, fee_rules=fee_rules)


def recalc(ctx: Ctx, order: Order) -> None:
    """Server-side totals (C-02, BR-008). Client-supplied totals are never used. Automatic promotions are re-evaluated first (FR-PROMO-005)."""
    from app.services import promotions

    promotions.reconcile(ctx, order)
    if order.order_type == "Delivery":
        from app.services import delivery

        delivery.refresh_fee(ctx, order)  # zone fee rules follow the food subtotal (FR-DLV-003)
    result = calculation(ctx.db, order)
    by_key = {r.key: r for r in result.lines}
    for i in order.items:
        r = by_key.get(str(i.id))
        i.line_gross, i.line_discount, i.line_net = (r.gross, r.item_discount + r.order_discount, r.net) if r else (ZERO, ZERO, ZERO)
    order.gross_total, order.discount_total, order.subtotal = result.gross_total, result.discount_total, result.subtotal
    order.service_charge_total, order.tax_total, order.grand_total = result.service_charge_total, result.tax_total, result.total
    order.delivery_fee = result.delivery_fee
    if order.channel == "Platform":
        from app.models import PlatformOrder
        from app.services import delivery

        po = ctx.db.scalar(select(PlatformOrder).where(PlatformOrder.order_id == order.id))
        if po is not None:
            delivery.update_commission(ctx, po, order)  # a rate-based commission follows the order total (BR-044)
    refresh_statuses(ctx, order)


def refresh_statuses(ctx: Ctx, order: Order) -> None:
    was_kitchen = order.kitchen_status
    items = live_items(order)
    if not items or all(i.item_status == "Pending" for i in items):
        order.kitchen_status = "NotSent"
    elif all(i.item_status in DELIVERED for i in items):
        order.kitchen_status = "Served"
    elif all(i.item_status not in ("Pending",) + ACTIVE_KITCHEN for i in items):
        order.kitchen_status = "Ready"
    else:
        order.kitchen_status = "InProgress"
    if order.kitchen_status == "Ready" and was_kitchen != "Ready" and order.channel == "Online" and order.order_type == "Takeaway":
        from app.services import sms

        sms.order_update(ctx.db, order, "ready")  # once per order (dedupe key)
    if order.kitchen_status == "Ready" and was_kitchen != "Ready" and order.channel == "Platform":
        from app.services import grabfood

        grabfood.on_ready(ctx.db, order)  # tell Grab the food is ready (once)
    paid = paid_total(ctx.db, order)
    refunded = ctx.db.scalar(select(func.coalesce(func.sum(Bill.refunded_total), 0)).where(Bill.order_id == order.id, Bill.status != "Void")) or ZERO
    if refunded > 0:
        order.payment_status = "Refunded" if paid <= 0 else "PartiallyRefunded"
    elif order.grand_total > 0 and paid >= order.grand_total:
        order.payment_status = "Paid"
    else:
        order.payment_status = "PartiallyPaid" if paid > 0 else "Unpaid"


def maybe_complete(ctx: Ctx, order: Order) -> None:
    """BR-031 / FR-ORD-012: all non-cancelled items delivered and fully paid."""
    items = live_items(order)
    if order.order_status != "Open" or not items:
        return
    if all(i.item_status in DELIVERED for i in items) and order.payment_status == "Paid":
        order.order_status, order.completed_at = "Completed", utcnow()
        log_event(ctx, order, "completed")
        from app.services import loyalty

        loyalty.earn(ctx, order)  # FR-PROMO-011: points on completion, once
        if order.table_id:
            table = ctx.db.get(RestaurantTable, order.table_id, with_for_update=True)
            others = ctx.db.scalar(select(func.count()).select_from(Order).where(Order.table_id == table.id, Order.order_status == "Open", Order.id != order.id))
            if not others:
                set_table_state(ctx, table, "Cleaning", force=True)
        emit(ctx.db, f"branch:{ctx.branch_id}", "order.completed", {"order_id": str(order.id), "order_no": order.order_no})


# ---------------------------------------------------------------- tables state machine (BR-027, §6.4)
TABLE_TRANSITIONS = {
    "Available": {"Reserved", "Seated"},
    "Reserved": {"Available", "Seated"},
    "Seated": {"Ordering", "Cleaning", "Available"},
    "Ordering": {"Served", "AwaitingPayment", "Cleaning"},
    "Served": {"Ordering", "AwaitingPayment", "Cleaning"},
    "AwaitingPayment": {"Ordering", "Cleaning"},
    "Cleaning": {"Available"},
}


def set_table_state(ctx: Ctx, table: RestaurantTable, new: str, force: bool = False) -> None:
    if table.service_state == new:
        return
    if new not in TABLE_TRANSITIONS.get(table.service_state, set()):
        if not force:
            raise Conflict("INVALID_STATUS_TRANSITION", f"A table can't go from {table.service_state} to {new}.")
    old = table.service_state
    table.service_state = new
    if new in ("Available", "Cleaning"):
        table.guest_count, table.server_user_id, table.seated_at = 0, None, None
        if new == "Available":
            table.current_group_id = None
    emit(ctx.db, f"tables:{ctx.branch_id}", "table.state", {"table_id": str(table.id), "table_code": table.table_code, "from": old, "to": new})


# ---------------------------------------------------------------- create and items
def create_order(ctx: Ctx, data: dict) -> Order:
    ensure_day_open(ctx)
    db = ctx.db
    bdate = ctx.business_date()
    table = None
    if data.get("table_id"):
        table = db.scalar(select(RestaurantTable).where(RestaurantTable.id == data["table_id"], RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.is_active).with_for_update())
        if table is None:
            raise NotFound("Table")
        if table.is_out_of_service:
            raise Conflict("TABLE_OUT_OF_SERVICE", f"Table {table.table_code} is out of service.")
    seq = next_number(db, ctx.branch_id, "ORDER", bdate.isoformat())
    order = Order(branch_id=ctx.branch_id, business_date=bdate, order_no=f"{seq:04d}", order_type=data["order_type"], channel=data.get("channel", "POS"),
                  table_id=table.id if table else None, table_tag=data.get("table_tag"), customer_name=data.get("customer_name"), customer_phone=data.get("customer_phone"),
                  pickup_name=data.get("pickup_name"), delivery_address=data.get("delivery_address"), guest_count=data.get("guest_count"),
                  server_user_id=ctx.user_id, note=data.get("note"), idempotency_key=data.get("idempotency_key"), scheduled_at=data.get("scheduled_at"))
    db.add(order)
    db.flush()
    if table is not None:
        if table.service_state in ("Available", "Reserved"):
            set_table_state(ctx, table, "Seated")
            table.seated_at, table.guest_count, table.server_user_id = utcnow(), data.get("guest_count") or 1, ctx.user_id
    log_event(ctx, order, "created", {"order_type": order.order_type, "table": table.table_code if table else None})
    for item in data.get("items", []):
        add_item(ctx, order, item)
    if order.order_type == "Delivery" and order.channel != "Platform":
        from app.services import delivery

        if not data.get("delivery"):
            raise BusinessRuleError("DELIVERY_DETAILS_REQUIRED", "Delivery orders need a zone, address and phone number (BR-052).",
                                    details=[{"field": "delivery", "issue": "required"}])
        delivery.attach(ctx, order, data["delivery"])
    recalc(ctx, order)
    audit(db, ctx, "order.create", "Order", order.id, after={"order_no": order.order_no, "type": order.order_type, "table_id": order.table_id})
    emit(db, f"branch:{ctx.branch_id}", "order.created", {"order_id": str(order.id), "order_no": order.order_no})
    return order


def add_item(ctx: Ctx, order: Order, data: dict) -> OrderItem:
    """Snapshot name, variant, modifiers, price, tax profile and station at add time (BR-026)."""
    ensure_editable(order)
    db = ctx.db
    variant, item = menu_svc.variant_or_404(db, data["variant_id"])
    reason = menu_svc.availability(db, ctx.branch_id, item)
    if reason:
        raise BusinessRuleError("ITEM_UNAVAILABLE", f"{item.name_en} can't be sold right now: {reason}.", details=[{"field": "variant_id", "issue": reason}])
    list_code = None
    if order.channel in ("Online", "QR"):
        # FR-ONL-001: only items published to the channel, at the online price list when one is configured
        allowed = ("Online",) if order.channel == "Online" else ("QR", "Online")
        if not set(item.channels or []) & set(allowed):
            raise BusinessRuleError("ITEM_UNAVAILABLE", f"{item.name_en} isn't sold online.", details=[{"field": "variant_id", "issue": "not on this channel"}])
        list_code = get_setting(db, "online", ctx.branch_id).get("price_list")
    price = menu_svc.current_price(db, variant.id, ctx.branch_id, menu_svc.price_list_id(db, list_code, ctx.branch_id))
    if price is None:
        raise BusinessRuleError("PRICE_MISSING", f"{item.name_en} ({variant.name_en}) has no current price.")
    modifiers = validate_modifiers(db, item, data.get("modifiers") or [])
    note = data.get("note")
    oi = OrderItem(order_id=order.id, branch_id=order.branch_id, menu_item_id=item.id, variant_id=variant.id, item_name_en_snapshot=item.name_en,
                   item_name_km_snapshot=item.name_km, variant_name_snapshot=variant.name_en, category_name_snapshot=item.category.name_en,
                   unit_price_snapshot=price.price, modifiers_total=sum((m.price_delta for m in modifiers), ZERO), tax_profile_id_snapshot=item.tax_profile_id,
                   station_code=item.station_code, quantity=Decimal(str(data["quantity"])), seat_no=data.get("seat_no"), note=note,
                   is_allergy=bool(note and "allerg" in note.lower()), added_by=ctx.user_id, replaces_item_id=data.get("replaces_item_id"))
    db.add(oi)
    db.flush()
    for m in modifiers:
        db.add(OrderItemModifier(order_item_id=oi.id, modifier_id=m.id, group_id=m.group_id, name_snapshot=m.name_en, price_delta_snapshot=m.price_delta))
    db.flush()
    db.refresh(order)
    log_event(ctx, order, "item_added", {"item_id": oi.id, "name": item.name_en, "quantity": oi.quantity})
    if order.table_id:
        table = db.get(RestaurantTable, order.table_id)
        if table.service_state in ("Seated", "Served", "AwaitingPayment"):
            set_table_state(ctx, table, "Ordering")
    return oi


def validate_modifiers(db: Session, item: MenuItem, selected: list[dict]) -> list[Modifier]:
    """BR-004 / FR-POS-003: min/max per group, modifiers must belong to the item's groups."""
    groups = menu_svc.item_groups(db, item.id)
    allowed = {m.id: m for g in groups for m in g.modifiers if m.is_active}
    chosen: list[Modifier] = []
    for s in selected:
        mid = uuid.UUID(str(s["modifier_id"]))
        if mid not in allowed:
            raise BusinessRuleError("MODIFIER_INVALID", "A modifier doesn't belong to this item.", details=[{"field": "modifiers", "issue": str(mid)}])
        chosen.append(allowed[mid])
    counts = defaultdict(int)
    for m in chosen:
        counts[m.group_id] += 1
    missing = []
    for g in groups:
        if counts[g.id] < g.min_select:
            missing.append(g.name_en)
        if counts[g.id] > g.max_select:
            raise BusinessRuleError("MODIFIER_LIMIT", f"Choose at most {g.max_select} from {g.name_en}.", details=[{"field": "modifiers", "issue": g.name_en}])
    if missing:
        raise BusinessRuleError("MODIFIER_REQUIRED", f"Choose a required option: {', '.join(missing)}.", details=[{"field": "modifiers", "issue": f"required: {n}"} for n in missing])
    return chosen


def find_item(order: Order, item_id: uuid.UUID) -> OrderItem:
    for i in order.items:
        if i.id == item_id:
            return i
    raise NotFound("Order item")


def update_pending_item(ctx: Ctx, order: Order, item: OrderItem, data: dict) -> None:
    """BR-005: only Pending items change in place."""
    ensure_editable(order)
    if item.item_status != "Pending":
        raise Conflict("ITEM_NOT_PENDING", "This item was already sent to the kitchen. Cancel it and add a new item instead.")
    before = {k: getattr(item, k) for k in data}
    for k, v in data.items():
        setattr(item, k, v)
    if "note" in data:
        item.is_allergy = bool(item.note and "allerg" in item.note.lower())
    log_event(ctx, order, "item_updated", {"item_id": item.id, "before": before, "after": data})


# ---------------------------------------------------------------- send to kitchen (FR-POS-008, FR-KDS-001)
def send(ctx: Ctx, order: Order) -> dict:
    ensure_editable(order)
    ensure_day_open(ctx)
    db = ctx.db
    pending = [i for i in order.items if i.item_status == "Pending"]
    if not pending:
        raise BusinessRuleError("NOTHING_TO_SEND", "There are no new items to send.")
    rules = get_setting(db, "orders", ctx.branch_id)
    # BR-052 order type data
    if order.order_type == "DineIn" and rules.get("require_table_for_dine_in", True) and not (order.table_id or order.table_tag):
        raise BusinessRuleError("TABLE_REQUIRED", "Choose a table (or enter a table tag) for dine-in orders.", details=[{"field": "table_id", "issue": "required"}])
    if order.order_type == "Takeaway" and not (order.pickup_name or order.customer_name):
        raise BusinessRuleError("PICKUP_NAME_REQUIRED", "Enter a pickup name or number.", details=[{"field": "pickup_name", "issue": "required"}])
    if order.order_type == "Delivery" and not (order.customer_phone and order.delivery_address):
        raise BusinessRuleError("DELIVERY_DETAILS_REQUIRED", "Delivery orders need a phone number and address.")
    if order.order_type == "Delivery":
        from app.services import delivery

        delivery.check_minimum(ctx, order)
    # FR-POS-017 pay-first
    staff_accepted = False
    if order.channel in ("Online", "QR"):
        from app.models import OnlineOrder

        staff_accepted = db.scalar(select(OnlineOrder.status).where(OnlineOrder.order_id == order.id)) == "Accepted"  # accepted online orders may pay at pickup
    if order.order_type in rules.get("pay_first_order_types", []) and order.payment_status != "Paid" and not staff_accepted:
        raise AppError("PAYMENT_REQUIRED_FIRST", f"{order.order_type} orders are paid before they go to the kitchen.", 409)
    # BR-003 re-check availability at submission
    for i in pending:
        item = db.get(MenuItem, i.menu_item_id)
        if reason := menu_svc.availability(db, ctx.branch_id, item):
            raise BusinessRuleError("ITEM_UNAVAILABLE", f"{i.item_name_en_snapshot} became unavailable ({reason}). Remove or replace it.", details=[{"field": "items", "issue": str(i.id)}])
    now = utcnow()
    stations = {s.code: s for s in db.scalars(select(KitchenStation).where(KitchenStation.branch_id == ctx.branch_id, KitchenStation.is_active))}
    first_send = not any(i.item_status != "Pending" for i in live_items(order))
    by_station: dict[str, list[OrderItem]] = defaultdict(list)
    for i in pending:
        i.sent_at = now
        if i.station_code and i.station_code in stations:
            i.item_status = "Sent"
            by_station[i.station_code].append(i)
        else:
            i.item_status = "Ready"  # no kitchen routing (§6.5)
            i.ready_at = now
    tickets = []
    for code, items in by_station.items():
        ticket = KitchenTicket(branch_id=ctx.branch_id, business_date=order.business_date, order_id=order.id, station_code=code,
                               ticket_no=next_number(db, ctx.branch_id, "TICKET", order.business_date.isoformat()), ticket_type="New" if first_send else "Addition")
        db.add(ticket)
        db.flush()
        db.add_all([KitchenTicketItem(ticket_id=ticket.id, order_item_id=i.id, quantity=i.quantity, action="Add") for i in items])
        tickets.append(ticket)
        emit(db, f"station:{ctx.branch_id}:{code}", "kitchen.ticket.created", {"ticket_id": str(ticket.id), "order_id": str(order.id), "order_no": order.order_no})
    order.order_status = "Open"
    order.held_label = None
    db.flush()
    db.refresh(order)
    refresh_statuses(ctx, order)
    if order.table_id:
        table = db.get(RestaurantTable, order.table_id)
        if table.service_state != "Ordering" and "Ordering" in TABLE_TRANSITIONS.get(table.service_state, set()):
            set_table_state(ctx, table, "Ordering")
    from app.services.recipes import post_consumption

    consumed = post_consumption(ctx, pending)  # BR-014 / A-15: ingredients consumed when sent
    log_event(ctx, order, "sent", {"items": len(pending), "tickets": [t.ticket_no for t in tickets], "consumption_rows": consumed})
    audit(db, ctx, "order.send", "Order", order.id, after={"items": [str(i.id) for i in pending], "tickets": [str(t.id) for t in tickets]})
    emit(db, f"branch:{ctx.branch_id}", "order.updated", {"order_id": str(order.id), "kitchen_status": order.kitchen_status})
    return {"order_id": order.id, "tickets": [{"ticket_id": t.id, "ticket_no": t.ticket_no, "station_code": t.station_code, "items": len(by_station[t.station_code])} for t in tickets]}


# ---------------------------------------------------------------- cancellation (BR-006, FR-ORD-009/010)
def cancel_item(ctx: Ctx, order: Order, item: OrderItem, reason: str, approval_id: uuid.UUID | None) -> None:
    ensure_editable(order)
    db = ctx.db
    if item.item_status == "Cancelled":
        raise Conflict("ALREADY_CANCELLED", "This item is already cancelled.")
    status = item.item_status
    if status == "Pending":
        void_type, approver = None, None
    elif status == "Sent":
        ctx.require("orders.cancel")
        void_type, approver = "BeforePreparation", None
    else:
        # In preparation, ready or served: approval by someone else (BR-006, BR-029)
        void_type = "AfterPreparation"
        approver = consume_approval(ctx, approval_id, "void", item.line_net, item.id)
    item.item_status, item.void_type, item.void_reason, item.void_approved_by, item.cancelled_at = "Cancelled", void_type, reason, approver, utcnow()
    if void_type == "BeforePreparation":
        from app.services.recipes import reverse_consumption

        reverse_consumption(ctx, item, f"Cancelled before preparation: {reason}")  # BR-014
    if status != "Pending":
        ticket = KitchenTicket(branch_id=ctx.branch_id, business_date=order.business_date, order_id=order.id, station_code=item.station_code or "NONE",
                               ticket_no=next_number(db, ctx.branch_id, "TICKET", order.business_date.isoformat()), ticket_type="Void")
        db.add(ticket)
        db.flush()
        db.add(KitchenTicketItem(ticket_id=ticket.id, order_item_id=item.id, quantity=item.quantity, action="Void"))
        if item.station_code:
            emit(db, f"station:{ctx.branch_id}:{item.station_code}", "kitchen.item.cancelled", {"order_item_id": str(item.id), "order_no": order.order_no,
                                                                                               "prepared": void_type == "AfterPreparation"})
    db.flush()
    recalc(ctx, order)
    paid = paid_total(db, order)
    if paid > order.grand_total:
        raise Conflict("REFUND_REQUIRED", "Payments already exceed the new total. Refund first, then cancel the item.")
    log_event(ctx, order, "item_cancelled", {"item_id": item.id, "status_was": status, "void_type": void_type, "reason": reason})
    audit(db, ctx, "order.item_void", "OrderItem", item.id, before={"status": status}, after={"status": "Cancelled", "void_type": void_type, "approved_by": approver}, reason=reason)


def cancel_order(ctx: Ctx, order: Order, reason: str, approval_id: uuid.UUID | None) -> None:
    ensure_editable(order)
    db = ctx.db
    if paid_total(db, order) > 0:
        raise Conflict("REFUND_REQUIRED", "This order has payments. Refund them before cancelling the order.")
    prepared = [i for i in live_items(order) if i.item_status not in ("Pending", "Sent")]
    approver = consume_approval(ctx, approval_id, "void", sum((i.line_net for i in prepared), ZERO), order.id) if prepared else None
    if any(i.item_status == "Sent" for i in live_items(order)):
        ctx.require("orders.cancel")
    for i in live_items(order):
        was = i.item_status
        i.void_type = None if was == "Pending" else ("BeforePreparation" if was == "Sent" else "AfterPreparation")
        i.item_status, i.void_reason, i.cancelled_at, i.void_approved_by = "Cancelled", reason, utcnow(), approver if was not in ("Pending", "Sent") else None
        if was == "Sent":
            from app.services.recipes import reverse_consumption

            reverse_consumption(ctx, i, f"Order cancelled: {reason}")
        if i.station_code and was in ACTIVE_KITCHEN + ("Ready",):
            emit(db, f"station:{ctx.branch_id}:{i.station_code}", "kitchen.item.cancelled", {"order_item_id": str(i.id), "order_no": order.order_no})
    for b in db.scalars(select(Bill).where(Bill.order_id == order.id, Bill.status == "Open")):
        b.status = "Void"
    order.order_status, order.cancelled_at, order.cancel_reason = "Cancelled", utcnow(), reason
    from app.services import loyalty

    loyalty.on_order_cancelled(ctx, order)  # redeemed points go back
    if order.order_type == "Delivery":
        from app.services import delivery

        delivery.on_order_cancelled(ctx, order)
    db.flush()
    recalc(ctx, order)
    if order.table_id:
        table = db.get(RestaurantTable, order.table_id, with_for_update=True)
        set_table_state(ctx, table, "Cleaning", force=True)
    log_event(ctx, order, "cancelled", {"reason": reason})
    audit(db, ctx, "order.cancel", "Order", order.id, after={"status": "Cancelled", "approved_by": approver}, reason=reason)


# ---------------------------------------------------------------- discounts (BR-009, BR-037, FR-POS-007)
def apply_discount(ctx: Ctx, order: Order, item_id: uuid.UUID | None, kind: str, value: Decimal, reason: str, approval_id: uuid.UUID | None) -> OrderDiscount:
    ensure_editable(order)
    ctx.require("discounts.apply")
    db = ctx.db
    if paid_total(db, order) > 0:
        raise Conflict("ORDER_PARTLY_PAID", "Discounts can't change after payment has started.")
    if kind == "Percent" and value > 100:
        raise BusinessRuleError("VALIDATION_ERROR", "A percentage can't exceed 100.", details=[{"field": "value", "issue": "max 100"}])
    if item_id:
        item = find_item(order, item_id)
        if item.item_status == "Cancelled":
            raise Conflict("ITEM_CANCELLED", "This item is cancelled.")
        base = item.line_gross
    else:
        calc = calculation(db, order)
        base = calc.gross_total - calc.item_discount_total  # BR-037: order discount applies after item discounts
    amount = discount_amount(kind, value, base)
    if kind == "Amount" and value > base:
        raise BusinessRuleError("DISCOUNT_EXCEEDS_AMOUNT", "The discount is larger than the amount it applies to.")
    pct = (value if kind == "Percent" else (amount * 100 / base if base else ZERO)).quantize(Decimal("0.01"))
    existing = db.scalar(select(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.removed_at.is_(None),
                                                     OrderDiscount.order_item_id == item_id if item_id else OrderDiscount.order_item_id.is_(None)).with_for_update())
    if existing and existing.kind == kind and existing.value == value:
        raise Conflict("DISCOUNT_ALREADY_APPLIED", "This discount is already applied.")  # FR-PROMO-010
    if existing is not None:
        from app.services.loyalty import redemption_for

        if redemption_for(db, existing.id):
            raise Conflict("LOYALTY_REDEMPTION_APPLIED", "Points are redeemed on this order. Remove the redemption first.")
    approver = None
    if pct > ctx.limit("discount_pct") or amount > ctx.limit("discount_amount"):
        approver = consume_approval(ctx, approval_id, "discount", pct, order.id)
    if existing:
        existing.removed_at = utcnow()
        db.flush()
    d = OrderDiscount(order_id=order.id, order_item_id=item_id, kind=kind, value=value, reason=reason, requested_by=ctx.user_id, approved_by=approver)
    db.add(d)
    db.flush()
    recalc(ctx, order)
    log_event(ctx, order, "discount_applied", {"item_id": item_id, "kind": kind, "value": value, "amount": amount, "approved_by": approver})
    audit(db, ctx, "discount.apply", "Order", order.id, after={"item_id": item_id, "kind": kind, "value": value, "percent": pct, "requested_by": ctx.user_id, "approved_by": approver}, reason=reason)
    return d


def remove_discount(ctx: Ctx, order: Order, discount_id: uuid.UUID) -> None:
    ensure_editable(order)
    d = ctx.db.get(OrderDiscount, discount_id)
    if d is None or d.order_id != order.id or d.removed_at:
        raise NotFound("Discount")
    if paid_total(ctx.db, order) > 0:
        raise Conflict("ORDER_PARTLY_PAID", "Discounts can't change after payment has started.")
    from app.services import loyalty

    loyalty.reverse_redemption(ctx, d, "Redemption removed")
    d.removed_at = utcnow()
    ctx.db.flush()
    recalc(ctx, order)
    audit(ctx.db, ctx, "discount.remove", "Order", order.id, before={"discount_id": d.id, "kind": d.kind, "value": d.value})


# ---------------------------------------------------------------- transfer, hold, serve
def transfer(ctx: Ctx, order: Order, table_id: uuid.UUID) -> None:
    """FR-TBL-008 / FR-POS-011, AT-TBL-03."""
    ensure_editable(order)
    ctx.require("orders.transfer")
    db = ctx.db
    ids = sorted(x for x in (order.table_id, table_id) if x)
    tables = {t.id: t for t in db.scalars(select(RestaurantTable).where(RestaurantTable.id.in_(ids), RestaurantTable.branch_id == ctx.branch_id).order_by(RestaurantTable.id).with_for_update())}
    target = tables.get(table_id)
    if target is None or not target.is_active:
        raise NotFound("Table")
    if target.is_out_of_service or target.service_state not in ("Available", "Reserved"):
        raise Conflict("TABLE_NOT_AVAILABLE", f"Table {target.table_code} isn't available.")
    total_before = order.grand_total
    source = tables.get(order.table_id) if order.table_id else None
    target.service_state, target.guest_count = source.service_state if source else "Seated", (source.guest_count if source else order.guest_count or 1)
    target.server_user_id, target.seated_at = (source.server_user_id, source.seated_at) if source else (ctx.user_id, utcnow())
    emit(db, f"tables:{ctx.branch_id}", "table.state", {"table_id": str(target.id), "to": target.service_state})
    if source:
        set_table_state(ctx, source, "Cleaning", force=True)
    order.table_id = target.id
    db.flush()
    assert order.grand_total == total_before  # BR-032
    log_event(ctx, order, "transferred", {"from": source.table_code if source else None, "to": target.table_code})
    audit(db, ctx, "order.transfer", "Order", order.id, before={"table": source.table_code if source else None}, after={"table": target.table_code})


def serve(ctx: Ctx, order: Order, item_ids: list[uuid.UUID] | None) -> None:
    ensure_editable(order)
    now = utcnow()
    done = "Served" if order.order_type == "DineIn" else "Collected"
    for i in live_items(order):
        if i.item_status == "Ready" and (not item_ids or i.id in item_ids):
            i.item_status, i.served_at = done, now
    ctx.db.flush()
    refresh_statuses(ctx, order)
    if order.table_id and order.kitchen_status == "Served":
        table = ctx.db.get(RestaurantTable, order.table_id)
        if "Served" in TABLE_TRANSITIONS.get(table.service_state, set()):
            set_table_state(ctx, table, "Served")
    log_event(ctx, order, "served", {"items": item_ids})
    maybe_complete(ctx, order)


def notify_ready(ctx: Ctx, order: Order, station_code: str) -> None:
    """FR-KDS-009: tell the waiter (or the counter for takeaway)."""
    where = f"table {ctx.db.get(RestaurantTable, order.table_id).table_code}" if order.table_id else (order.pickup_name or "pickup")
    notify_users(ctx.db, [order.server_user_id], ctx.branch_id, "Kitchen", f"Order {order.order_no} ready", f"{station_code} items are ready for {where}.", f"/orders/{order.id}",
                 {"order_id": str(order.id)})

