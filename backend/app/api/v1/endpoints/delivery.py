"""Delivery, takeaway ready board and third-party platform orders (DLV)."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field, model_validator
from sqlalchemy import select

from app.api.v1.endpoints.orders import order_out
from app.core.dependencies import Ctx, get_ctx, require
from app.core.exceptions import Conflict, NotFound
from app.models import Delivery, DeliveryZone, Order, PlatformOrder, PlatformSettlement, TaxProfile
from app.schemas.common import Strict
from app.schemas.orders import ItemIn, OrderOut
from app.services import delivery as svc
from app.services import orders as order_svc
from app.services.platform import audit
from app.services.reports import _range

router = APIRouter(tags=["delivery"])
DView = Annotated[Ctx, Depends(require("delivery.view"))]
DManage = Annotated[Ctx, Depends(require("delivery.manage"))]
Any = Annotated[Ctx, Depends(get_ctx)]


class ZoneIn(Strict):
    name: str = Field(min_length=1, max_length=60)
    fee: Decimal = Field(ge=0)
    free_over: Decimal | None = Field(None, gt=0, description="Food subtotal at or above which delivery is free")
    min_order: Decimal | None = Field(None, gt=0)
    tax_profile_id: uuid.UUID | None = Field(None, description="The fee's own tax profile (BR-044); empty = fee not taxed")
    estimated_minutes: int | None = Field(None, ge=5, le=240)
    is_active: bool = True


class ZonePatch(Strict):
    fee: Decimal | None = Field(None, ge=0)
    free_over: Decimal | None = Field(None, gt=0)
    min_order: Decimal | None = Field(None, gt=0)
    tax_profile_id: uuid.UUID | None = None
    estimated_minutes: int | None = Field(None, ge=5, le=240)
    is_active: bool | None = None


class AssignIn(Strict):
    rider_id: uuid.UUID


class DeliveredIn(Strict):
    recipient_name: str | None = Field(None, max_length=120)


class ReasonIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


class FeeIn(Strict):
    fee: Decimal = Field(ge=0)
    reason: str = Field(min_length=2, max_length=300)


class PlatformOrderIn(Strict):
    platform: str = Field(min_length=2, max_length=30)
    platform_ref: str = Field(min_length=1, max_length=60)
    pickup_name: str | None = Field(None, max_length=60)
    customer_name: str | None = Field(None, max_length=120)
    commission_rate: Decimal | None = Field(None, ge=0, le=1, description="0.25 = 25 % of the order total")
    commission_amount: Decimal | None = Field(None, ge=0)
    note: str | None = Field(None, max_length=500)
    items: list[ItemIn] = Field(min_length=1)

    @model_validator(mode="after")
    def one_commission(self):
        if (self.commission_rate is None) == (self.commission_amount is None):
            raise ValueError("Give commission_rate or commission_amount, from the platform statement")
        return self


class SettlementLineIn(Strict):
    platform_ref: str = Field(min_length=1, max_length=60)
    gross: Decimal = Field(ge=0)
    commission: Decimal = Field(ge=0)
    net: Decimal


class SettlementIn(Strict):
    platform: str = Field(min_length=2, max_length=30)
    statement_ref: str = Field(min_length=1, max_length=60)
    period_from: date
    period_to: date
    amount_paid: Decimal
    lines: list[SettlementLineIn] = Field(min_length=1)

    @model_validator(mode="after")
    def period(self):
        if self.period_to < self.period_from:
            raise ValueError("period_to must be on or after period_from")
        return self


def zone_out(z: DeliveryZone) -> dict:
    return {k: getattr(z, k) for k in ("id", "name", "fee", "free_over", "min_order", "tax_profile_id", "estimated_minutes", "is_active")}


def _delivery(ctx: Ctx, delivery_id: uuid.UUID, lock: bool = True) -> Delivery:
    stmt = select(Delivery).where(Delivery.id == delivery_id, Delivery.branch_id == ctx.branch_id)
    d = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if d is None or not (ctx.can("delivery.view") or (ctx.can("delivery.operate") and d.rider_user_id == ctx.user_id)):
        raise NotFound("Delivery")
    return d


# ---------------------------------------------------------------- zones
@router.get("/delivery-zones")
def zones(ctx: DView):
    return [zone_out(z) for z in ctx.db.scalars(select(DeliveryZone).where(DeliveryZone.branch_id == ctx.branch_id).order_by(DeliveryZone.name))]


@router.post("/delivery-zones", status_code=201, summary="Zone fee rules are financial settings (settings.manage)")
def create_zone(body: ZoneIn, ctx: Annotated[Ctx, Depends(require("settings.manage"))]):
    if body.tax_profile_id and ctx.db.get(TaxProfile, body.tax_profile_id) is None:
        raise NotFound("Tax profile")
    z = DeliveryZone(branch_id=ctx.branch_id, **body.model_dump())
    ctx.db.add(z)
    ctx.db.flush()
    audit(ctx.db, ctx, "delivery.zone_create", "DeliveryZone", z.id, after=zone_out(z))
    return zone_out(z)


@router.patch("/delivery-zones/{zone_id}")
def update_zone(zone_id: uuid.UUID, body: ZonePatch, ctx: Annotated[Ctx, Depends(require("settings.manage"))]):
    z = svc.zone(ctx, zone_id)
    data = body.model_dump(exclude_unset=True)
    before = {k: getattr(z, k) for k in data}
    for k, v in data.items():
        setattr(z, k, v)
    audit(ctx.db, ctx, "delivery.zone_update", "DeliveryZone", z.id, before=before, after=data)
    return zone_out(z)


# ---------------------------------------------------------------- deliveries
@router.get("/deliveries", summary="Delivery board for the branch")
def list_deliveries(ctx: DView, status: str | None = None):
    stmt = select(Delivery, Order).join(Order, Order.id == Delivery.order_id).where(Delivery.branch_id == ctx.branch_id)
    stmt = stmt.where(Delivery.status == status) if status else stmt.where(Delivery.status.not_in(("Delivered", "Cancelled")))
    return [svc.delivery_out(ctx, d, o) for d, o in ctx.db.execute(stmt.order_by(Delivery.created_at))]


@router.get("/deliveries/mine", summary="Rider view: my active deliveries, with address, phone and amount to collect")
def mine(ctx: Annotated[Ctx, Depends(require("delivery.operate"))]):
    stmt = select(Delivery, Order).join(Order, Order.id == Delivery.order_id).where(Delivery.branch_id == ctx.branch_id, Delivery.rider_user_id == ctx.user_id,
                                                                                   Delivery.status.in_(("Assigned", "OutForDelivery")))
    return [svc.delivery_out(ctx, d, o) for d, o in ctx.db.execute(stmt.order_by(Delivery.assigned_at))]


@router.get("/deliveries/performance", summary="Orders, prep and delivery times, late and failed by rider, zone and platform (FR-DLV-011)")
def performance(ctx: DView, date_from: date | None = None, date_to: date | None = None):
    start, end = _range(date_from, date_to, ctx)
    return svc.performance(ctx, start, end)


@router.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: uuid.UUID, ctx: Any):
    return svc.delivery_out(ctx, _delivery(ctx, delivery_id, lock=False))


@router.post("/deliveries/{delivery_id}/assign")
def assign(delivery_id: uuid.UUID, body: AssignIn, ctx: DManage):
    return svc.delivery_out(ctx, svc.assign(ctx, _delivery(ctx, delivery_id), body.rider_id))


@router.post("/deliveries/{delivery_id}/out", summary="Rider leaves; all items must be ready")
def out(delivery_id: uuid.UUID, ctx: Any):
    return svc.delivery_out(ctx, svc.out_for_delivery(ctx, _delivery(ctx, delivery_id)))


@router.post("/deliveries/{delivery_id}/delivered", summary="Rider confirms delivery (optionally the recipient's name)")
def delivered(delivery_id: uuid.UUID, body: DeliveredIn, ctx: Any):
    return svc.delivery_out(ctx, svc.delivered(ctx, _delivery(ctx, delivery_id), body.recipient_name))


@router.post("/deliveries/{delivery_id}/failed", summary="Delivery failed; a manager re-delivers or cancels the order (refund and wastage rules apply)")
def failed(delivery_id: uuid.UUID, body: ReasonIn, ctx: Any):
    return svc.delivery_out(ctx, svc.failed(ctx, _delivery(ctx, delivery_id), body.reason))


@router.post("/deliveries/{delivery_id}/redeliver")
def redeliver(delivery_id: uuid.UUID, ctx: DManage):
    return svc.delivery_out(ctx, svc.redeliver(ctx, _delivery(ctx, delivery_id)))


@router.put("/orders/{order_id}/delivery-fee", response_model=OrderOut, summary="Manual fee override with reason (delivery.fee_override)")
def override_fee(order_id: uuid.UUID, body: FeeIn, ctx: Annotated[Ctx, Depends(require("delivery.fee_override"))]):
    order = order_svc.get_order(ctx, order_id, lock=True)
    svc.override_fee(ctx, order, body.fee, body.reason)
    return order_out(ctx, order)


@router.get("/ready-board", summary="Takeaway orders ready for collection (FR-DLV-006)")
def ready_board(ctx: Annotated[Ctx, Depends(require("orders.view"))]):
    return svc.ready_board(ctx)


# ---------------------------------------------------------------- platform orders and settlements
@router.post("/platform-orders", status_code=201, summary="Record a third-party platform order; the reference is unique per platform (BR-044, BR-030)")
def platform_order(body: PlatformOrderIn, ctx: Annotated[Ctx, Depends(require("delivery.manage", "orders.create"))]):
    if ctx.db.scalar(select(PlatformOrder.id).where(PlatformOrder.platform.ilike(body.platform), PlatformOrder.platform_ref == body.platform_ref)):
        raise Conflict("PLATFORM_REF_EXISTS", "This platform order is already recorded.")
    order = order_svc.create_order(ctx, {"order_type": "Takeaway", "channel": "Platform", "pickup_name": body.pickup_name or f"{body.platform} {body.platform_ref}"[:60],
                                         "customer_name": body.customer_name, "note": body.note, "items": [i.model_dump() for i in body.items]})
    po = svc.record_platform_order(ctx, order, body.platform, body.platform_ref, body.commission_rate, body.commission_amount)
    return {"order": OrderOut.model_validate(order_out(ctx, order)).model_dump(), "platform": body.platform, "platform_ref": po.platform_ref,
            "commission_amount": po.commission_amount, "settlement_status": po.settlement_status}


@router.get("/platform-orders")
def platform_orders(ctx: DView, platform: str | None = None, settlement_status: str | None = None):
    stmt = select(PlatformOrder, Order).join(Order, Order.id == PlatformOrder.order_id).where(PlatformOrder.branch_id == ctx.branch_id)
    if platform:
        stmt = stmt.where(PlatformOrder.platform.ilike(platform))
    if settlement_status:
        stmt = stmt.where(PlatformOrder.settlement_status == settlement_status)
    return [{"order_id": o.id, "order_no": o.order_no, "business_date": o.business_date, "status": o.order_status, "platform": p.platform, "platform_ref": p.platform_ref,
             "order_total": o.grand_total, "commission_rate": p.commission_rate, "commission_amount": p.commission_amount, "net_expected": o.grand_total - p.commission_amount,
             "settlement_status": p.settlement_status} for p, o in ctx.db.execute(stmt.order_by(Order.created_at))]


@router.post("/platform-settlements", status_code=201, summary="Record a payout statement and reconcile it (FR-DLV-010)")
def settle(body: SettlementIn, ctx: Annotated[Ctx, Depends(require("platform.reconcile"))]):
    s = svc.settle(ctx, body.model_dump())
    return svc.reconcile(ctx, s)


@router.get("/platform-settlements/{settlement_id}/reconciliation")
def reconciliation(settlement_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("platform.reconcile"))]):
    s = ctx.db.get(PlatformSettlement, settlement_id)
    if s is None or s.branch_id != ctx.branch_id:
        raise NotFound("Settlement")
    return svc.reconcile(ctx, s)
