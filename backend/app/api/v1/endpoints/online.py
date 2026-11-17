"""Online ordering and QR table ordering (ONL). Routes under /public need no sign-in and are rate limited."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import EmailStr, Field, model_validator
from sqlalchemy import select

from app.core.dependencies import Ctx, DbSession, require
from app.core.exceptions import NotFound
from app.core.ratelimit import limit
from app.models import DeliveryZone, OnlineOrder, Order, RestaurantTable
from app.schemas.common import Strict
from app.schemas.orders import ItemIn
from app.services import online as svc
from app.services.platform import idempotent

public = APIRouter(prefix="/public", tags=["public online ordering"])
router = APIRouter(tags=["online ordering"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]


class PublicDeliveryIn(Strict):
    zone_id: uuid.UUID
    address: str = Field(min_length=3, max_length=500)
    landmark: str | None = Field(None, max_length=300)
    latitude: Decimal | None = Field(None, ge=-90, le=90)
    longitude: Decimal | None = Field(None, ge=-180, le=180)


class CartIn(Strict):
    fulfilment: Literal["Pickup", "Delivery"]
    name: str = Field(min_length=1, max_length=60)
    phone: str = Field(min_length=6, max_length=20)
    email: EmailStr | None = None
    scheduled_at: datetime | None = Field(None, description="Empty = as soon as possible")
    delivery: PublicDeliveryIn | None = None
    promo_code: str | None = Field(None, max_length=30)
    note: str | None = Field(None, max_length=300)
    items: list[ItemIn] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def delivery_needed(self):
        if self.fulfilment == "Delivery" and self.delivery is None:
            raise ValueError("Delivery orders need a zone and address")
        return self


class CheckoutIn(CartIn):
    payment: Literal["Online", "PayLater"] = "PayLater"
    expected_total: Decimal | None = Field(None, description="The total the customer saw; a different server total returns 409 PRICE_CHANGED (BR-046)")


class QrOrderIn(Strict):
    guest_count: int | None = Field(None, ge=1, le=50)
    note: str | None = Field(None, max_length=300)
    items: list[ItemIn] = Field(min_length=1, max_length=30)


class RejectIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


class PauseIn(Strict):
    paused: bool


def _data(body) -> dict:
    d = body.model_dump()
    d["items"] = [i.model_dump() for i in body.items]
    return d


# ---------------------------------------------------------------- public
@public.get("/branches/{code}/menu", dependencies=[Depends(limit("menu", 120))], summary="Published online menu with prices and modifiers (FR-ONL-001)")
def menu(code: str, db: DbSession):
    branch, _ = svc.public_branch(db, code)
    return svc.public_menu(svc.system_ctx(db, branch), "Online")


@public.get("/branches/{code}/delivery-zones", dependencies=[Depends(limit("menu", 120))])
def zones(code: str, db: DbSession):
    branch, _ = svc.public_branch(db, code)
    return [{"id": z.id, "name": z.name, "fee": z.fee, "free_over": z.free_over, "min_order": z.min_order, "estimated_minutes": z.estimated_minutes}
            for z in db.scalars(select(DeliveryZone).where(DeliveryZone.branch_id == branch.id, DeliveryZone.is_active).order_by(DeliveryZone.name))]


@public.post("/branches/{code}/quote", dependencies=[Depends(limit("checkout"))], summary="Price a cart exactly as checkout would; nothing is saved")
def quote(code: str, body: CartIn, db: DbSession):
    branch, s = svc.public_branch(db, code)
    return svc.quote(db, branch, s, _data(body))


@public.post("/branches/{code}/orders", status_code=201, dependencies=[Depends(limit("checkout", 20))],
             summary="Place an order (Idempotency-Key required). Returns the tracking link and, for online payment, the hosted payment page")
def checkout(code: str, body: CheckoutIn, db: DbSession, idempotency_key: IdemKey = None):
    branch, s = svc.public_branch(db, code)
    return idempotent(db, f"online:{branch.id}", idempotency_key, body.model_dump(), lambda: svc.checkout(db, branch, s, _data(body)), 201)


@public.get("/track/{token}", dependencies=[Depends(limit("track", 120))], summary="Order status by signed, expiring link (FR-ONL-009)")
def track(token: str, db: DbSession):
    return svc.track(db, token)


@public.post("/payments/{provider}/callback", dependencies=[Depends(limit("callback", 300))], summary="Signed server-to-server payment notification (FR-ONL-007)")
async def payment_callback(provider: str, request: Request, db: DbSession, x_signature: Annotated[str | None, Header()] = None):
    return svc.payment_callback(db, provider, await request.body(), x_signature)


@public.get("/qr/{token}", dependencies=[Depends(limit("menu", 120))], summary="Table QR code: table and its menu (FR-ONL-013)")
def qr_menu(token: str, db: DbSession):
    table, branch, s = svc.qr_table(db, token)
    return {"table": table.table_code, "staff_confirmation": s.get("require_staff_confirmation", True), **svc.public_menu(svc.system_ctx(db, branch), "QR")}


@public.post("/qr/{token}/orders", status_code=201, dependencies=[Depends(limit("checkout", 20))], summary="Order at the table (Idempotency-Key required)")
def qr_order(token: str, body: QrOrderIn, db: DbSession, idempotency_key: IdemKey = None):
    return idempotent(db, f"qr:{token[:16]}", idempotency_key, body.model_dump(), lambda: svc.qr_order(db, token, _data(body)), 201)


# ---------------------------------------------------------------- staff
def online_out(db, oo: OnlineOrder, order: Order) -> dict:
    return {"id": oo.id, "order_id": order.id, "order_no": order.order_no, "source": oo.source, "fulfilment": oo.fulfilment, "status": oo.status,
            "tracking_status": svc.tracking_status(db, order, oo), "customer_name": order.customer_name, "customer_phone": order.customer_phone,
            "scheduled_at": order.scheduled_at, "payment_mode": oo.payment_mode, "payment_status": oo.payment_status, "total": order.grand_total,
            "created_at": oo.created_at, "accepted_by": oo.accepted_by, "reject_reason": oo.reject_reason}


@router.get("/online-orders", summary="Incoming online and QR orders (FR-ONL-011)")
def list_online(ctx: Annotated[Ctx, Depends(require("orders.view"))], status: str | None = "Received"):
    stmt = select(OnlineOrder, Order).join(Order, Order.id == OnlineOrder.order_id).where(OnlineOrder.branch_id == ctx.branch_id)
    if status:
        stmt = stmt.where(OnlineOrder.status == status)
    return [online_out(ctx.db, oo, o) for oo, o in ctx.db.execute(stmt.order_by(OnlineOrder.created_at))]


@router.post("/online-orders/{online_id}/accept", summary="Accept and send to the kitchen; online-paid orders wait for the payment")
def accept(online_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("orders.edit"))]):
    oo = svc.accept(ctx, svc.get_online(ctx, online_id))
    return online_out(ctx.db, oo, ctx.db.get(Order, oo.order_id))


@router.post("/online-orders/{online_id}/reject", summary="Reject with a reason; cancels the order (refund first if it was paid)")
def reject(online_id: uuid.UUID, body: RejectIn, ctx: Annotated[Ctx, Depends(require("orders.cancel"))]):
    oo = svc.reject(ctx, svc.get_online(ctx, online_id), body.reason)
    return online_out(ctx.db, oo, ctx.db.get(Order, oo.order_id))


@router.put("/online-ordering/pause", summary="Pause or resume online ordering at this branch (FR-ONL-014)")
def pause(body: PauseIn, ctx: Annotated[Ctx, Depends(require("settings.manage"))]):
    return svc.set_paused(ctx, body.paused)


@router.post("/tables/{table_id}/qr-code", status_code=201, summary="Issue or rotate the table's QR token; shown once. Encode the returned path in the printed code")
def qr_code(table_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("tables.manage"))]):
    t = ctx.db.scalar(select(RestaurantTable).where(RestaurantTable.id == table_id, RestaurantTable.branch_id == ctx.branch_id, RestaurantTable.is_active).with_for_update())
    if t is None:
        raise NotFound("Table")
    token = svc.issue_qr(ctx, t)
    return {"table": t.table_code, "token": token, "path": f"/qr/{token}"}
