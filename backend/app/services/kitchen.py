"""Kitchen display (SRS §6.6, §12.7; BR-007)."""
import uuid

from sqlalchemy import select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, NotFound
from app.core.realtime import emit
from app.models import KitchenTicket, KitchenTicketItem, Order, OrderItem
from app.services.orders import ensure_editable, log_event, maybe_complete, notify_ready, refresh_statuses, serve
from app.services.platform import audit
from app.utils.timeutil import utcnow

# BR-007: forward only, plus recall Ready -> InPreparation.
ITEM_TRANSITIONS = {
    "Sent": {"InPreparation", "Ready"},
    "InPreparation": {"Ready"},
    "Ready": {"InPreparation", "Served", "Collected"},
}


def get_ticket(ctx: Ctx, ticket_id: uuid.UUID) -> KitchenTicket:
    t = ctx.db.scalar(select(KitchenTicket).where(KitchenTicket.id == ticket_id, KitchenTicket.branch_id == ctx.branch_id))
    if t is None:
        raise NotFound("Kitchen ticket")
    return t


def ticket_items(ctx: Ctx, ticket: KitchenTicket) -> list[OrderItem]:
    ids = [ti.order_item_id for ti in ticket.items]
    return list(ctx.db.scalars(select(OrderItem).where(OrderItem.id.in_(ids)).with_for_update())) if ids else []


def _lock_order(ctx: Ctx, order_id: uuid.UUID) -> Order:
    return ctx.db.scalar(select(Order).where(Order.id == order_id).with_for_update())


def set_item_status(ctx: Ctx, item_id: uuid.UUID, status: str, version: int | None) -> OrderItem:
    db = ctx.db
    item = db.scalar(select(OrderItem).where(OrderItem.id == item_id, OrderItem.branch_id == ctx.branch_id))
    if item is None:
        raise NotFound("Order item")
    order = _lock_order(ctx, item.order_id)
    db.refresh(item, with_for_update=True)
    ensure_editable(order)
    if version is not None and version != item.version:
        # Concurrent bump from two screens: first update wins; the second sees the current state (BR-007).
        raise Conflict("VERSION_CONFLICT", "This item was updated on another screen.", current_status=item.item_status, current_version=item.version)
    if status in ("Served", "Collected"):
        if not (ctx.can("orders.edit") or ctx.can("kitchen.operate")):
            ctx.require("orders.edit")
    else:
        ctx.require("kitchen.operate")
    if status not in ITEM_TRANSITIONS.get(item.item_status, set()):
        raise Conflict("INVALID_STATUS_TRANSITION", f"An item can't move from {item.item_status} to {status}.")
    now = utcnow()
    was = item.item_status
    item.item_status = status
    if status == "InPreparation":
        item.started_at = item.started_at or now
        if was == "Ready":
            item.ready_at = None
    elif status == "Ready":
        item.started_at, item.ready_at = item.started_at or now, now
    else:
        item.served_at = now
    db.flush()
    refresh_statuses(ctx, order)
    log_event(ctx, order, "item_status", {"item_id": item.id, "from": was, "to": status})
    emit(db, f"station:{ctx.branch_id}:{item.station_code}", "kitchen.item.status", {"order_item_id": str(item.id), "status": status})
    emit(db, f"branch:{ctx.branch_id}", "order.updated", {"order_id": str(order.id), "kitchen_status": order.kitchen_status})
    if status == "Ready" and all(i.item_status not in ("Sent", "InPreparation") for i in order.items if i.station_code == item.station_code and i.item_status != "Cancelled"):
        notify_ready(ctx, order, item.station_code)
    if status in ("Served", "Collected"):
        maybe_complete(ctx, order)
    return item


def bump(ctx: Ctx, ticket_id: uuid.UUID) -> KitchenTicket:
    ctx.require("kitchen.operate")
    db = ctx.db
    ticket = get_ticket(ctx, ticket_id)
    order = _lock_order(ctx, ticket.order_id)
    ensure_editable(order)
    now = utcnow()
    changed = 0
    for i in ticket_items(ctx, ticket):
        if i.item_status in ("Sent", "InPreparation"):
            i.item_status, i.started_at, i.ready_at = "Ready", i.started_at or now, now
            changed += 1
    if not changed and ticket.bumped_at:
        raise Conflict("TICKET_ALREADY_BUMPED", "This ticket was already bumped.")
    ticket.bumped_at = now
    db.flush()
    db.refresh(order)
    refresh_statuses(ctx, order)
    log_event(ctx, order, "ticket_bumped", {"ticket_id": ticket.id, "station": ticket.station_code})
    emit(db, f"station:{ctx.branch_id}:{ticket.station_code}", "kitchen.ticket.bumped", {"ticket_id": str(ticket.id)})
    emit(db, f"branch:{ctx.branch_id}", "order.updated", {"order_id": str(order.id), "kitchen_status": order.kitchen_status})
    notify_ready(ctx, order, ticket.station_code)
    return ticket


def recall(ctx: Ctx, ticket_id: uuid.UUID) -> KitchenTicket:
    ctx.require("kitchen.operate")
    ticket = get_ticket(ctx, ticket_id)
    order = _lock_order(ctx, ticket.order_id)
    ensure_editable(order)
    items = [i for i in ticket_items(ctx, ticket) if i.item_status == "Ready"]
    if not items:
        raise Conflict("NOTHING_TO_RECALL", "No ready items on this ticket.")
    for i in items:
        i.item_status, i.ready_at = "InPreparation", None
    ticket.bumped_at = None
    ctx.db.flush()
    ctx.db.refresh(order)
    refresh_statuses(ctx, order)
    log_event(ctx, order, "ticket_recalled", {"ticket_id": ticket.id})
    emit(ctx.db, f"station:{ctx.branch_id}:{ticket.station_code}", "kitchen.ticket.recalled", {"ticket_id": str(ticket.id)})
    return ticket


def set_priority(ctx: Ctx, ticket_id: uuid.UUID, priority: int) -> KitchenTicket:
    ctx.require("kitchen.manage")
    ticket = get_ticket(ctx, ticket_id)
    ticket.priority = priority
    audit(ctx.db, ctx, "kitchen.priority", "KitchenTicket", ticket.id, after={"priority": priority})
    emit(ctx.db, f"station:{ctx.branch_id}:{ticket.station_code}", "kitchen.ticket.priority", {"ticket_id": str(ticket.id), "priority": priority})
    return ticket


def waste_outcome(ctx: Ctx, item_id: uuid.UUID, outcome: str) -> OrderItem:
    """FR-KDS-014. Ingredient wastage posting from recipes arrives with the recipes module (Phase 2)."""
    ctx.require("kitchen.operate")
    item = ctx.db.scalar(select(OrderItem).where(OrderItem.id == item_id, OrderItem.branch_id == ctx.branch_id))
    if item is None:
        raise NotFound("Order item")
    if item.item_status != "Cancelled" or item.void_type != "AfterPreparation":
        raise BusinessRuleError("NOT_PREPARED_CANCELLATION", "Only prepared items that were cancelled need a waste outcome.")
    if item.waste_outcome:
        raise Conflict("OUTCOME_RECORDED", "An outcome was already recorded for this item.")
    item.waste_outcome = outcome
    if outcome == "Reusable":
        from app.services.recipes import reverse_consumption

        reverse_consumption(ctx, item, "Prepared item reused")  # wastage keeps the consumption as waste
    audit(ctx.db, ctx, "kitchen.waste_outcome", "OrderItem", item.id, after={"outcome": outcome})
    return item


def open_tickets(ctx: Ctx, station_code: str) -> list[dict]:
    """Full state for (re)synchronising a station screen (§12.7, NFR-REL-006)."""
    db = ctx.db
    tickets = db.scalars(select(KitchenTicket).where(KitchenTicket.branch_id == ctx.branch_id, KitchenTicket.station_code == station_code,
                                                     KitchenTicket.ticket_type.in_(("New", "Addition"))).order_by(KitchenTicket.priority.desc(), KitchenTicket.created_at)).all()
    now = utcnow()
    out = []
    for t in tickets:
        items = ticket_items_readonly(ctx, t)
        if not any(i.item_status in ("Sent", "InPreparation") for i in items) and t.bumped_at:
            continue
        if not any(i.item_status in ("Sent", "InPreparation", "Ready") for i in items):
            continue
        order = db.get(Order, t.order_id)
        if order.order_status != "Open":
            continue
        out.append({"ticket": t, "order": order, "items": items, "age_seconds": int((now - t.created_at).total_seconds())})
    return out


def ticket_items_readonly(ctx: Ctx, ticket: KitchenTicket) -> list[OrderItem]:
    ids = [ti.order_item_id for ti in ticket.items]
    return list(ctx.db.scalars(select(OrderItem).where(OrderItem.id.in_(ids)).order_by(OrderItem.created_at))) if ids else []


_ = (KitchenTicketItem, serve)
