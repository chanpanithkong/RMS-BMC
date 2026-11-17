"""Promotions, promotion codes and their use on orders (PROMO)."""
import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import Field, model_validator
from sqlalchemy import func, select

from app.api.v1.endpoints.orders import order_out
from app.core.dependencies import Ctx, require
from app.core.exceptions import Conflict, NotFound
from app.models import Promotion, PromotionCode, PromotionRedemption
from app.schemas.common import Strict
from app.schemas.orders import OrderOut
from app.services import orders as order_svc
from app.services import promotions as svc
from app.services.platform import audit

router = APIRouter(tags=["promotions"])
View = Annotated[Ctx, Depends(require("promotions.view"))]
Manage = Annotated[Ctx, Depends(require("promotions.manage"))]
FIELDS = ("name", "promo_type", "scope", "value", "target_ids", "buy_qty", "get_qty", "valid_from", "valid_to", "days_of_week", "time_from", "time_to", "order_types",
          "classifications", "branch_ids", "priority", "combinable", "auto_apply", "is_active")


class PromotionIn(Strict):
    name: str = Field(min_length=2, max_length=120)
    promo_type: Literal["Percent", "Amount", "FixedPrice", "BuyXGetY"]
    scope: Literal["Order", "Item", "Category"]
    value: Decimal = Field(Decimal("0"), ge=0, description="Percent, amount off (per unit for items), or the fixed unit price")
    target_ids: list[uuid.UUID] = Field([], description="Menu item ids (scope Item) or category ids (scope Category)")
    buy_qty: int | None = Field(None, ge=1)
    get_qty: int | None = Field(None, ge=1)
    valid_from: datetime
    valid_to: datetime | None = None
    days_of_week: list[int] = Field([], description="0 = Monday; empty = every day")
    time_from: time | None = None
    time_to: time | None = None
    order_types: list[Literal["DineIn", "Takeaway", "Delivery"]] = []
    classifications: list[Literal["Regular", "VIP", "Corporate"]] = []
    branch_ids: list[uuid.UUID] = []
    priority: int = Field(0, ge=0, le=1000)
    combinable: bool = False
    auto_apply: bool = Field(True, description="False = applies only with a promotion code")
    is_active: bool = True

    @model_validator(mode="after")
    def rules(self):
        if self.scope == "Order" and self.promo_type not in ("Percent", "Amount"):
            raise ValueError("Order-level promotions are Percent or Amount")
        if self.scope != "Order" and not self.target_ids:
            raise ValueError("Item and category promotions need target_ids")
        if self.promo_type == "BuyXGetY" and not (self.buy_qty and self.get_qty):
            raise ValueError("Buy X get Y needs buy_qty and get_qty")
        if self.promo_type != "BuyXGetY" and self.value <= 0:
            raise ValueError("value must be greater than 0")
        if self.promo_type == "Percent" and self.value > 100:
            raise ValueError("A percentage can't exceed 100")
        if (self.time_from is None) != (self.time_to is None):
            raise ValueError("Give both time_from and time_to, or neither")
        if self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        if any(d < 0 or d > 6 for d in self.days_of_week):
            raise ValueError("days_of_week are 0 (Monday) to 6 (Sunday)")
        return self


class PromotionPatch(Strict):
    name: str | None = Field(None, min_length=2, max_length=120)
    valid_to: datetime | None = None
    priority: int | None = Field(None, ge=0, le=1000)
    combinable: bool | None = None
    is_active: bool | None = None


class CodeIn(Strict):
    code: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    max_uses: int | None = Field(None, ge=1, description="1 = single use; empty = unlimited")
    max_uses_per_customer: int | None = Field(None, ge=1)


class RedeemIn(Strict):
    code: str = Field(min_length=1, max_length=30)


def promo_out(p: Promotion) -> dict:
    return {"id": p.id, **{k: getattr(p, k) for k in FIELDS}}


def code_out(c: PromotionCode) -> dict:
    return {k: getattr(c, k) for k in ("id", "promotion_id", "code", "max_uses", "max_uses_per_customer", "uses", "is_active")}


def _promo(ctx: Ctx, promotion_id: uuid.UUID) -> Promotion:
    p = ctx.db.get(Promotion, promotion_id)
    if p is None:
        raise NotFound("Promotion")
    return p


@router.get("/promotions")
def list_promotions(ctx: View, active: bool | None = None):
    stmt = select(Promotion)
    if active is not None:
        stmt = stmt.where(Promotion.is_active.is_(active))
    return [promo_out(p) for p in ctx.db.scalars(stmt.order_by(Promotion.priority.desc(), Promotion.name))]


@router.post("/promotions", status_code=201)
def create_promotion(body: PromotionIn, ctx: Manage):
    data = body.model_dump()
    data["target_ids"] = [str(x) for x in data["target_ids"]]
    data["branch_ids"] = [str(x) for x in data["branch_ids"]]
    p = Promotion(**data, created_by=ctx.user_id)
    ctx.db.add(p)
    ctx.db.flush()
    audit(ctx.db, ctx, "promotion.create", "Promotion", p.id, after=promo_out(p))
    return promo_out(p)


@router.get("/promotions/{promotion_id}")
def get_promotion(promotion_id: uuid.UUID, ctx: View):
    p = _promo(ctx, promotion_id)
    uses = ctx.db.scalar(select(func.count()).select_from(PromotionRedemption).where(PromotionRedemption.promotion_id == p.id, PromotionRedemption.cancelled_at.is_(None)))
    codes = [code_out(c) for c in ctx.db.scalars(select(PromotionCode).where(PromotionCode.promotion_id == p.id).order_by(PromotionCode.code))]
    return {**promo_out(p), "codes": codes if ctx.can("promotions.manage") else [], "redemptions": uses}


@router.patch("/promotions/{promotion_id}", summary="Rules are fixed once created; end or deactivate and create a new promotion to change them")
def update_promotion(promotion_id: uuid.UUID, body: PromotionPatch, ctx: Manage):
    p = _promo(ctx, promotion_id)
    data = body.model_dump(exclude_unset=True)
    before = {k: getattr(p, k) for k in data}
    for k, v in data.items():
        setattr(p, k, v)
    audit(ctx.db, ctx, "promotion.update", "Promotion", p.id, before=before, after=data)
    return promo_out(p)


@router.post("/promotions/{promotion_id}/codes", status_code=201, summary="Codes are case-insensitive and unique")
def create_code(promotion_id: uuid.UUID, body: CodeIn, ctx: Manage):
    p = _promo(ctx, promotion_id)
    if ctx.db.scalar(select(PromotionCode.id).where(func.lower(PromotionCode.code) == body.code.lower())):
        raise Conflict("PROMO_CODE_EXISTS", "This code is already in use.")
    c = PromotionCode(promotion_id=p.id, **body.model_dump())
    ctx.db.add(c)
    ctx.db.flush()
    audit(ctx.db, ctx, "promotion.code_create", "Promotion", p.id, after=code_out(c))
    return code_out(c)


@router.patch("/promotion-codes/{code_id}/deactivate")
def deactivate_code(code_id: uuid.UUID, ctx: Manage):
    c = ctx.db.get(PromotionCode, code_id)
    if c is None:
        raise NotFound("Promotion code")
    c.is_active = False
    audit(ctx.db, ctx, "promotion.code_deactivate", "Promotion", c.promotion_id, after={"code": c.code})
    return code_out(c)


# ---------------------------------------------------------------- on orders
@router.get("/orders/{order_id}/promotions", summary="Applied and not-applied promotions with reasons (FR-PROMO-005)")
def order_promotions(order_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("orders.view"))]):
    order = order_svc.get_order(ctx, order_id)
    codes = [{"redemption_id": r.id, "promotion_id": r.promotion_id, "code": c.code}
             for r, c in ctx.db.execute(select(PromotionRedemption, PromotionCode).join(PromotionCode, PromotionCode.id == PromotionRedemption.code_id)
                                        .where(PromotionRedemption.order_id == order.id, PromotionRedemption.cancelled_at.is_(None)))]
    return {**svc.summary(ctx, order), "codes": codes}


@router.post("/orders/{order_id}/promo-codes", response_model=OrderOut, summary="Redeem a code; uses are counted under a row lock (BR-038, AT-PROMO-03)")
def redeem(order_id: uuid.UUID, body: RedeemIn, ctx: Annotated[Ctx, Depends(require("orders.edit"))]):
    order = order_svc.get_order(ctx, order_id, lock=True)
    svc.apply_code(ctx, order, body.code)
    return order_out(ctx, order)


@router.delete("/orders/{order_id}/promo-codes/{redemption_id}", response_model=OrderOut)
def unredeem(order_id: uuid.UUID, redemption_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("orders.edit"))]):
    order = order_svc.get_order(ctx, order_id, lock=True)
    svc.remove_code(ctx, order, redemption_id)
    return order_out(ctx, order)
