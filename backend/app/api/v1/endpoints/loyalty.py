"""Loyalty points (FR-PROMO-011, FR-CUST-008)."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select

from app.api.v1.endpoints.orders import order_out
from app.core.dependencies import Ctx, require
from app.core.exceptions import BusinessRuleError, NotFound
from app.models import OrderDiscount
from app.schemas.common import Strict
from app.schemas.orders import OrderOut
from app.services import loyalty as svc
from app.services import orders as order_svc

router = APIRouter(tags=["loyalty"])


class RedeemIn(Strict):
    points: int = Field(gt=0, description="A multiple of the redemption step (100 by default)")


class AdjustIn(Strict):
    points: int = Field(description="Positive to add (expires like earned points), negative to remove")
    reason: str = Field(min_length=3, max_length=300)


@router.get("/customers/{customer_id}/loyalty", summary="Balance, redeemable value, points expiring soon and history")
def get_loyalty(customer_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("customers.view"))]):
    return svc.summary(ctx, customer_id)


@router.post("/customers/{customer_id}/loyalty/adjust", summary="Manual correction with a reason (promotions.manage); audited")
def adjust(customer_id: uuid.UUID, body: AdjustIn, ctx: Annotated[Ctx, Depends(require("promotions.manage"))]):
    if body.points == 0:
        raise BusinessRuleError("VALIDATION_ERROR", "Points can't be zero.")
    svc.adjust(ctx, customer_id, body.points, body.reason)
    return svc.summary(ctx, customer_id)


@router.post("/orders/{order_id}/loyalty-redemption", response_model=OrderOut, summary="Redeem points as money off the order (100 points = 1.00 USD)")
def redeem(order_id: uuid.UUID, body: RedeemIn, ctx: Annotated[Ctx, Depends(require("orders.edit"))]):
    order = order_svc.get_order(ctx, order_id, lock=True)
    svc.redeem(ctx, order, body.points)
    return order_out(ctx, order)


@router.delete("/orders/{order_id}/loyalty-redemption", response_model=OrderOut, summary="Remove the redemption; the points go back to the customer")
def unredeem(order_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("orders.edit"))]):
    order = order_svc.get_order(ctx, order_id, lock=True)
    d = next((x for x in ctx.db.scalars(select(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.removed_at.is_(None)))
              if svc.redemption_for(ctx.db, x.id)), None)
    if d is None:
        raise NotFound("Loyalty redemption")
    order_svc.remove_discount(ctx, order, d.id)
    return order_out(ctx, order)
