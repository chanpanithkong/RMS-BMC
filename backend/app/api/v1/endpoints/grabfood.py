"""GrabFood partner endpoints (called by Grab) and staff actions on imported platform orders.

Configure these in the Grab developer portal as the partner endpoints, with {{api-endpoint}} = https://<your host>/api/v1/integrations
and <any-path> = grabfood:
    POST .../grabfood/oauth/token   Get partner access token webhook
    POST .../grabfood/orders        Submit order webhook
    PUT  .../grabfood/order/state   Push order state webhook
"""
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header
from pydantic import Field, model_validator
from sqlalchemy import select

from app.core.dependencies import Ctx, DbSession, require
from app.core.exceptions import Conflict, NotFound
from app.core.ratelimit import limit
from app.models import MenuItemVariant, Modifier, PlatformInbound, PlatformItemMap
from app.schemas.common import Strict
from app.services import grabfood as svc
from app.services.platform import audit

grab = APIRouter(prefix="/integrations/grabfood", tags=["GrabFood webhooks"])
router = APIRouter(tags=["delivery"])
Auth = Annotated[str | None, Header(alias="Authorization")]


class TokenIn(Strict):
    client_id: str = Field(max_length=32)
    client_secret: str = Field(max_length=32)
    grant_type: str
    scope: str | None = None


class RejectIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


class MapIn(Strict):
    external_id: str = Field(min_length=1, max_length=64)
    variant_id: uuid.UUID | None = None
    modifier_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def one(self):
        if (self.variant_id is None) == (self.modifier_id is None):
            raise ValueError("Map to exactly one of variant_id or modifier_id")
        return self


# ---------------------------------------------------------------- called by Grab
@grab.post("/oauth/token", dependencies=[Depends(limit("grab-token", 30))], summary="Get partner access token webhook (client_credentials)")
def token(body: TokenIn):
    return svc.issue_token(body.client_id, body.client_secret, body.grant_type)


@grab.post("/orders", summary="Submit order webhook. Responds 2xx once the order is stored (imported, duplicate or queued for manual entry)")
def submit_order(db: DbSession, payload: Annotated[dict[str, Any], Body()], authorization: Auth = None):
    svc.verify_bearer(authorization)
    return svc.submit_order(db, payload)


@grab.put("/order/state", summary="Push order state webhook")
def order_state(db: DbSession, payload: Annotated[dict[str, Any], Body()], authorization: Auth = None):
    svc.verify_bearer(authorization)
    return svc.push_state(db, payload)


@grab.get("/merchant/menu", summary="Get menu webhook: the branch's menu in Grab's selling-time structure")
def get_menu(db: DbSession, merchantID: str | None = None, partnerMerchantID: str | None = None, BusinessType: int | None = None,  # noqa: N803
             authorization: Auth = None):
    svc.verify_bearer(authorization)
    return svc.get_menu(db, merchantID, partnerMerchantID)


@grab.post("/menu-sync-state", summary="Menu sync state webhook (QUEUEING, PROCESSING, SUCCESS, FAILED)")
def menu_sync_state(db: DbSession, payload: Annotated[dict[str, Any], Body()], authorization: Auth = None):
    svc.verify_bearer(authorization)
    return svc.menu_sync_state(db, payload)


@grab.post("/pushIntegrationStatus", status_code=204, summary="Push integration status webhook")
def integration_status(db: DbSession, payload: Annotated[dict[str, Any], Body()], authorization: Auth = None):
    svc.verify_bearer(authorization)
    svc.integration_status(db, payload)


@grab.post("/pushGrabMenu", status_code=204, summary="Push Grab menu webhook: the existing Grab menu, kept in the webhook log for reference")
def push_grab_menu(db: DbSession, payload: Annotated[dict[str, Any], Body()], authorization: Auth = None):
    svc.verify_bearer(authorization)
    svc._log(db, "push_grab_menu", payload, "stored", None)


# ---------------------------------------------------------------- staff
@router.post("/platform-orders/{order_id}/accept", summary="Accept an imported platform order: records the platform payment, sends to the kitchen and tells Grab")
def accept(order_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("orders.edit"))]):
    po = svc.accept(ctx, svc.get_po(ctx, order_id))
    return {"order_id": po.order_id, "platform_ref": po.platform_ref, "acceptance": po.acceptance}


@router.post("/platform-orders/{order_id}/reject", summary="Reject an imported platform order with a reason; cancels it and tells Grab")
def reject(order_id: uuid.UUID, body: RejectIn, ctx: Annotated[Ctx, Depends(require("orders.cancel"))]):
    po = svc.reject(ctx, svc.get_po(ctx, order_id), body.reason)
    return {"order_id": po.order_id, "platform_ref": po.platform_ref, "acceptance": po.acceptance}


@router.get("/platform-item-maps", summary="Platform menu IDs mapped to RMS variants and modifiers (unmapped IDs that are RMS UUIDs work directly)")
def maps(ctx: Annotated[Ctx, Depends(require("menu.view"))], platform: str = svc.PLATFORM):
    return [{"id": m.id, "platform": m.platform, "external_id": m.external_id, "variant_id": m.variant_id, "modifier_id": m.modifier_id}
            for m in ctx.db.scalars(select(PlatformItemMap).where(PlatformItemMap.platform == platform).order_by(PlatformItemMap.external_id))]


@router.post("/platform-item-maps", status_code=201)
def add_map(body: MapIn, ctx: Annotated[Ctx, Depends(require("menu.manage"))], platform: str = svc.PLATFORM):
    if body.variant_id and ctx.db.get(MenuItemVariant, body.variant_id) is None:
        raise NotFound("Variant")
    if body.modifier_id and ctx.db.get(Modifier, body.modifier_id) is None:
        raise NotFound("Modifier")
    if ctx.db.scalar(select(PlatformItemMap.id).where(PlatformItemMap.platform == platform, PlatformItemMap.external_id == body.external_id)):
        raise Conflict("MAPPING_EXISTS", "This platform ID is already mapped.")
    m = PlatformItemMap(platform=platform, **body.model_dump())
    ctx.db.add(m)
    ctx.db.flush()
    audit(ctx.db, ctx, "platform.item_map", "PlatformItemMap", m.id, after=body.model_dump())
    return {"id": m.id, "platform": platform, **body.model_dump()}


@router.get("/integrations/grabfood/inbound", summary="Webhooks received from Grab, newest first, with what RMS did with each")
def inbound(ctx: Annotated[Ctx, Depends(require("delivery.view"))], outcome: str | None = None):
    stmt = select(PlatformInbound).where(PlatformInbound.platform == svc.PLATFORM, (PlatformInbound.branch_id == ctx.branch_id) | PlatformInbound.branch_id.is_(None))
    if outcome:
        stmt = stmt.where(PlatformInbound.outcome == outcome)
    return [{"id": x.id, "kind": x.kind, "order": x.external_order_id, "outcome": x.outcome, "detail": x.detail, "received_at": x.received_at, "payload": x.payload}
            for x in ctx.db.scalars(stmt.order_by(PlatformInbound.received_at.desc()).limit(200))]


@router.get("/integrations/grabfood/menu/preview", summary="The menu Grab will receive for this branch (prices in KHR minor units, tax-inclusive)")
def menu_preview(ctx: Annotated[Ctx, Depends(require("menu.view"))]):
    from app.services.platform import get_setting

    return svc.build_menu(ctx.db, ctx.branch, get_setting(ctx.db, "grabfood", ctx.branch_id).get("merchant_id"))


@router.post("/integrations/grabfood/menu/sync", status_code=202, summary="Ask Grab to pull the full menu (Grab recommends once a day, off-peak)")
def menu_sync(ctx: Annotated[Ctx, Depends(require("menu.manage"))]):
    return svc.request_full_sync(ctx)
