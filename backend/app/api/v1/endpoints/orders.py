import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, or_, select

from app.core.dependencies import Ctx, require
from app.models import Order, OrderDiscount, OrderEvent, RestaurantTable
from app.schemas.common import Page
from app.schemas.orders import (CancelIn, DiscountIn, DiscountOut, HoldIn, ItemIn, ItemUpdate, OrderCreate, OrderEventOut, OrderOut, OrderSummary, OrderUpdate, SendOut,
                                ServeIn, TransferIn)
from app.services import orders as svc
from app.services.platform import idempotent
from app.utils.money import ZERO

router = APIRouter(prefix="/orders", tags=["orders"])
View = Annotated[Ctx, Depends(require("orders.view"))]
Create = Annotated[Ctx, Depends(require("orders.create"))]
Edit = Annotated[Ctx, Depends(require("orders.edit"))]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]
IfMatch = Annotated[int | None, Header(alias="If-Match")]


def order_out(ctx: Ctx, order: Order) -> dict:
    ctx.db.flush()
    ctx.db.refresh(order)
    table_code = ctx.db.get(RestaurantTable, order.table_id).table_code if order.table_id else None
    discounts = ctx.db.scalars(select(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.removed_at.is_(None))).all()
    paid = svc.paid_total(ctx.db, order)
    return {**{c: getattr(order, c) for c in ("id", "order_no", "business_date", "version", "order_type", "channel", "order_status", "kitchen_status", "payment_status",
                                              "table_id", "table_tag", "guest_count", "pickup_name", "customer_name", "customer_phone", "delivery_address", "server_user_id",
                                              "note", "held_label", "scheduled_at", "created_at", "completed_at", "cancelled_at", "cancel_reason")},
            "table_code": table_code, "items": order.items, "discounts": discounts,
            "totals": {"gross": order.gross_total, "discount_total": order.discount_total, "subtotal": order.subtotal, "service_charge": order.service_charge_total,
                       "tax": order.tax_total, "delivery_fee": order.delivery_fee, "rounding": order.rounding_total, "grand_total": order.grand_total, "paid": paid,
                       "balance": max(order.grand_total - paid, ZERO), "currency": order.currency}}


@router.get("", response_model=Page[OrderSummary], summary="Search by number, date, table, customer, type, status, server and amount range")
def list_orders(ctx: View, q: str | None = None, business_date: date | None = None, status: str | None = None, order_type: str | None = None,
                table_id: uuid.UUID | None = None, server_user_id: uuid.UUID | None = None, min_total: str | None = None, max_total: str | None = None,
                held: bool | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(Order, RestaurantTable.table_code).outerjoin(RestaurantTable, RestaurantTable.id == Order.table_id).where(Order.branch_id == ctx.branch_id)
    if not ctx.can("orders.view_all"):
        stmt = stmt.where(Order.server_user_id == ctx.user_id)
    if q:
        stmt = stmt.where(or_(Order.order_no.ilike(f"%{q}%"), Order.customer_name.ilike(f"%{q}%"), Order.customer_phone.ilike(f"%{q}%"), Order.pickup_name.ilike(f"%{q}%"),
                              RestaurantTable.table_code.ilike(q)))
    for col, val in ((Order.business_date, business_date), (Order.order_status, status), (Order.order_type, order_type), (Order.table_id, table_id), (Order.server_user_id, server_user_id)):
        if val is not None:
            stmt = stmt.where(col == val)
    if min_total:
        stmt = stmt.where(Order.grand_total >= min_total)
    if max_total:
        stmt = stmt.where(Order.grand_total <= max_total)
    if held is not None:
        stmt = stmt.where(Order.held_label.is_not(None) if held else Order.held_label.is_(None))
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.execute(stmt.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    data = [{**{c: getattr(o, c) for c in OrderSummary.model_fields if c != "table_code"}, "table_code": code} for o, code in rows]
    return {"data": data, "total": total, "page": page, "page_size": page_size}


@router.post("", response_model=OrderOut, status_code=201, summary="Create an order (Idempotency-Key required, BR-030)")
def create_order(body: OrderCreate, ctx: Create, idempotency_key: IdemKey = None):
    def run():
        order = svc.create_order(ctx, {**body.model_dump(), "items": [i.model_dump() for i in body.items], "idempotency_key": idempotency_key})
        return OrderOut.model_validate(order_out(ctx, order)).model_dump()

    return idempotent(ctx.db, f"order.create:{ctx.branch_id}", idempotency_key, body.model_dump(), run, 201)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: uuid.UUID, ctx: View):
    return order_out(ctx, svc.get_order(ctx, order_id))


@router.patch("/{order_id}", response_model=OrderOut)
def update_order(order_id: uuid.UUID, body: OrderUpdate, ctx: Edit, if_match: IfMatch = None):
    order = svc.get_order(ctx, order_id, lock=True)
    data = body.model_dump(exclude_unset=True)
    svc.check_version(order, data.pop("version", None) or if_match)
    svc.ensure_editable(order)
    for k, v in data.items():
        setattr(order, k, v)
    svc.log_event(ctx, order, "updated", data)
    return order_out(ctx, order)


@router.post("/{order_id}/items", response_model=OrderOut, status_code=201)
def add_items(order_id: uuid.UUID, body: list[ItemIn], ctx: Create, if_match: IfMatch = None):
    order = svc.get_order(ctx, order_id, lock=True)
    svc.check_version(order, if_match)
    for item in body:
        svc.add_item(ctx, order, item.model_dump())
    svc.recalc(ctx, order)
    return order_out(ctx, order)


@router.patch("/{order_id}/items/{item_id}", response_model=OrderOut, summary="Pending items only (BR-005)")
def update_item(order_id: uuid.UUID, item_id: uuid.UUID, body: ItemUpdate, ctx: Edit, if_match: IfMatch = None):
    order = svc.get_order(ctx, order_id, lock=True)
    svc.check_version(order, if_match)
    svc.update_pending_item(ctx, order, svc.find_item(order, item_id), body.model_dump(exclude_unset=True))
    svc.recalc(ctx, order)
    return order_out(ctx, order)


@router.post("/{order_id}/send", response_model=SendOut, summary="Send new items to the kitchen (Idempotency-Key required)")
def send(order_id: uuid.UUID, ctx: Edit, idempotency_key: IdemKey = None, if_match: IfMatch = None):
    def run():
        order = svc.get_order(ctx, order_id, lock=True)
        svc.check_version(order, if_match)
        return svc.send(ctx, order)

    return idempotent(ctx.db, f"order.send:{order_id}", idempotency_key, {"order_id": str(order_id)}, run)


@router.post("/{order_id}/items/{item_id}/cancel", response_model=OrderOut, summary="Void an item; prepared items need an approval_id (BR-006)")
def cancel_item(order_id: uuid.UUID, item_id: uuid.UUID, body: CancelIn, ctx: Edit):
    order = svc.get_order(ctx, order_id, lock=True)
    svc.cancel_item(ctx, order, svc.find_item(order, item_id), body.reason, body.approval_id)
    return order_out(ctx, order)


@router.post("/{order_id}/cancel", response_model=OrderOut, summary="Cancel the whole order; blocked while payments exist (FR-ORD-010)")
def cancel_order(order_id: uuid.UUID, body: CancelIn, ctx: Edit):
    order = svc.get_order(ctx, order_id, lock=True)
    svc.cancel_order(ctx, order, body.reason, body.approval_id)
    return order_out(ctx, order)


@router.post("/{order_id}/hold", response_model=OrderOut)
def hold(order_id: uuid.UUID, body: HoldIn, ctx: Edit):
    order = svc.get_order(ctx, order_id, lock=True)
    svc.ensure_editable(order)
    order.held_label = body.label
    svc.log_event(ctx, order, "held", {"label": body.label})
    return order_out(ctx, order)


@router.post("/{order_id}/resume", response_model=OrderOut)
def resume(order_id: uuid.UUID, ctx: Edit):
    order = svc.get_order(ctx, order_id, lock=True)
    order.held_label = None
    svc.log_event(ctx, order, "resumed")
    return order_out(ctx, order)


@router.post("/{order_id}/discounts", response_model=OrderOut, summary="Manual discount within your limit, or with approval_id (BR-009)")
def add_discount(order_id: uuid.UUID, body: DiscountIn, ctx: Edit):
    order = svc.get_order(ctx, order_id, lock=True)
    svc.apply_discount(ctx, order, body.order_item_id, body.kind, body.value, body.reason, body.approval_id)
    return order_out(ctx, order)


@router.delete("/{order_id}/discounts/{discount_id}", response_model=OrderOut)
def remove_discount(order_id: uuid.UUID, discount_id: uuid.UUID, ctx: Edit):
    order = svc.get_order(ctx, order_id, lock=True)
    svc.remove_discount(ctx, order, discount_id)
    return order_out(ctx, order)


@router.post("/{order_id}/transfer", response_model=OrderOut, summary="Move the party and order to another table (FR-TBL-008)")
def transfer(order_id: uuid.UUID, body: TransferIn, ctx: Edit):
    order = svc.get_order(ctx, order_id, lock=True)
    svc.transfer(ctx, order, body.table_id)
    return order_out(ctx, order)


@router.post("/{order_id}/serve", response_model=OrderOut, summary="Mark ready items served (dine-in) or collected")
def serve(order_id: uuid.UUID, body: ServeIn, ctx: Edit):
    order = svc.get_order(ctx, order_id, lock=True)
    svc.serve(ctx, order, body.order_item_ids)
    return order_out(ctx, order)


@router.get("/{order_id}/timeline", response_model=list[OrderEventOut], summary="Every event on the order (FR-ORD-014)")
def timeline(order_id: uuid.UUID, ctx: View):
    order = svc.get_order(ctx, order_id)
    return ctx.db.scalars(select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.occurred_at)).all()


_ = DiscountOut
