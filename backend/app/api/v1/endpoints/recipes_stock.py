"""Recipes and food cost (RCP) and advanced inventory: counts, transfers, batches, menu-item wastage (INV)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import select

from app.core.dependencies import Ctx, require
from app.core.exceptions import NotFound
from app.models import Recipe, RecipeVersion, StockCount
from app.schemas.common import Strict
from app.services import recipes as svc
from app.services.platform import get_setting

recipes = APIRouter(prefix="/recipes", tags=["recipes"])
stock = APIRouter(prefix="/inventory", tags=["inventory"])
RView = Annotated[Ctx, Depends(require("recipes.view"))]
RManage = Annotated[Ctx, Depends(require("recipes.manage"))]


class LineIn(Strict):
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    uom_id: uuid.UUID
    prep_loss_pct: Decimal = Field(Decimal("0"), ge=0, le=90)
    cook_loss_pct: Decimal = Field(Decimal("0"), ge=0, le=90)


class RecipeIn(Strict):
    variant_id: uuid.UUID | None = None
    modifier_id: uuid.UUID | None = None


class VersionIn(Strict):
    yield_qty: Decimal = Field(Decimal("1"), gt=0, description="Portions this recipe makes")
    method_text: str | None = None
    lines: list[LineIn] = Field(min_length=1)


class VersionPatch(Strict):
    yield_qty: Decimal | None = Field(None, gt=0)
    method_text: str | None = None
    lines: list[LineIn] | None = None


class PublishIn(Strict):
    effective_from: datetime | None = Field(None, description="Default now. Use a future time to schedule a change (AT-RCP-04).")


def version_out(v: RecipeVersion) -> dict:
    return {"id": v.id, "version_no": v.version_no, "status": v.status, "effective_from": v.effective_from, "yield_qty": v.yield_qty, "method_text": v.method_text,
            "published_by": v.published_by, "published_at": v.published_at, "created_by": v.created_by,
            "lines": [{"ingredient_id": ln.ingredient_id, "quantity": ln.quantity, "uom_id": ln.uom_id, "prep_loss_pct": ln.prep_loss_pct, "cook_loss_pct": ln.cook_loss_pct}
                      for ln in v.lines]}


def recipe_out(ctx: Ctx, r: Recipe) -> dict:
    active = svc.active_version(ctx.db, r.id)
    return {"id": r.id, "name": r.name, "variant_id": r.variant_id, "modifier_id": r.modifier_id, "active_version_id": active.id if active else None,
            "versions": [version_out(v) for v in r.versions]}


def _version(ctx: Ctx, version_id: uuid.UUID) -> RecipeVersion:
    v = ctx.db.get(RecipeVersion, version_id)
    if v is None:
        raise NotFound("Recipe version")
    return v


@recipes.get("")
def list_recipes(ctx: RView):
    return [recipe_out(ctx, r) for r in ctx.db.scalars(select(Recipe).order_by(Recipe.name))]


@recipes.post("", status_code=201, summary="Create the recipe for a menu item variant or a modifier")
def create(body: RecipeIn, ctx: RManage):
    return recipe_out(ctx, svc.create_recipe(ctx, body.variant_id, body.modifier_id))


@recipes.get("/unmapped-items", summary="Items sold without a recipe in effect (FR-RCP-010)")
def unmapped(ctx: RView, days: int = Query(30, ge=1, le=366)):
    return svc.unmapped_items(ctx, days)


@recipes.get("/{recipe_id}")
def get(recipe_id: uuid.UUID, ctx: RView):
    return recipe_out(ctx, svc.get_recipe(ctx, recipe_id))


@recipes.post("/{recipe_id}/versions", status_code=201, summary="New draft version; incompatible units return UNIT_INCOMPATIBLE (BR-015)")
def add_version(recipe_id: uuid.UUID, body: VersionIn, ctx: RManage):
    return version_out(svc.add_version(ctx, svc.get_recipe(ctx, recipe_id), body.yield_qty, [ln.model_dump() for ln in body.lines], body.method_text))


@recipes.patch("/versions/{version_id}", summary="Edit a draft; published versions are immutable")
def patch_version(version_id: uuid.UUID, body: VersionPatch, ctx: RManage):
    lines = [ln.model_dump() for ln in body.lines] if body.lines is not None else None
    return version_out(svc.update_draft(ctx, _version(ctx, version_id), body.yield_qty, lines, body.method_text))


@recipes.post("/versions/{version_id}/publish")
def publish(version_id: uuid.UUID, body: PublishIn, ctx: RManage):
    return version_out(svc.publish(ctx, _version(ctx, version_id), body.effective_from))


@recipes.get("/versions/{version_id}/cost", summary="Cost per portion of any version")
def version_cost(version_id: uuid.UUID, ctx: RView):
    return svc.version_cost(ctx, _version(ctx, version_id))


@recipes.get("/{recipe_id}/cost", summary="Food cost % and gross margin of the version in effect (FR-RCP-007/008)")
def cost(recipe_id: uuid.UUID, ctx: RView):
    return svc.food_cost(ctx, svc.get_recipe(ctx, recipe_id))


# ---------------------------------------------------------------- advanced inventory
class CountCreate(Strict):
    location_id: uuid.UUID
    ingredient_ids: list[uuid.UUID] | None = None


class CountEntry(Strict):
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(ge=0)
    uom_id: uuid.UUID


class CountEntries(Strict):
    lines: list[CountEntry] = Field(min_length=1)


class DecisionIn(Strict):
    approve: bool


class TransferLine(Strict):
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    uom_id: uuid.UUID


class TransferIn(Strict):
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    lines: list[TransferLine] = Field(min_length=1)


class MenuWasteIn(Strict):
    variant_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    reason: str = Field(min_length=2, max_length=200)


def _count(ctx: Ctx, count_id: uuid.UUID) -> StockCount:
    c = ctx.db.scalar(select(StockCount).where(StockCount.id == count_id, StockCount.branch_id == ctx.branch_id).with_for_update())
    if c is None:
        raise NotFound("Stock count")
    return c


@stock.post("/counts", status_code=201, summary="Start a count sheet (blind: system quantities hidden until submitted)")
def create_count(body: CountCreate, ctx: Annotated[Ctx, Depends(require("inventory.view"))]):
    return svc.count_out(ctx, svc.create_count(ctx, body.location_id, body.ingredient_ids))


@stock.get("/counts/{count_id}")
def get_count(count_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("inventory.view"))]):
    return svc.count_out(ctx, _count(ctx, count_id))


@stock.put("/counts/{count_id}/lines", summary="Enter or correct counted quantities (draft is saved on every call)")
def enter(count_id: uuid.UUID, body: CountEntries, ctx: Annotated[Ctx, Depends(require("inventory.manage"))]):
    return svc.count_out(ctx, svc.enter_counts(ctx, _count(ctx, count_id), {ln.ingredient_id: (ln.quantity, ln.uom_id) for ln in body.lines}))


@stock.post("/counts/{count_id}/submit")
def submit(count_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("inventory.manage"))]):
    return svc.count_out(ctx, svc.submit_count(ctx, _count(ctx, count_id)))


@stock.post("/counts/{count_id}/decision", summary="Approve to post COUNT_ADJUSTMENT variances (AT-INV-03)")
def decide(count_id: uuid.UUID, body: DecisionIn, ctx: Annotated[Ctx, Depends(require("inventory.approve"))]):
    return svc.count_out(ctx, svc.approve_count(ctx, _count(ctx, count_id), body.approve))


@stock.post("/transfers", status_code=201, summary="Move stock between locations of this branch (FR-INV-007)")
def transfer(body: TransferIn, ctx: Annotated[Ctx, Depends(require("inventory.manage"))]):
    t = svc.transfer(ctx, body.from_location_id, body.to_location_id, [ln.model_dump() for ln in body.lines])
    return {"id": t.id, "transfer_no": t.transfer_no, "status": t.status, "lines": len(t.lines)}


@stock.get("/expiring", summary="Batches expiring within N days (default from inventory settings)")
def expiring(ctx: Annotated[Ctx, Depends(require("inventory.view"))], days: int | None = Query(None, ge=0, le=365)):
    return svc.expiring(ctx, days if days is not None else int(get_setting(ctx.db, "inventory", ctx.branch_id).get("expiry_warning_days", 3)))


@stock.post("/menu-wastage", status_code=201, summary="Record wasted menu items; converted to ingredients by the active recipe (FR-INV-009)")
def menu_wastage(body: MenuWasteIn, ctx: Annotated[Ctx, Depends(require("inventory.wastage"))]):
    txns = svc.menu_item_wastage(ctx, body.variant_id, body.quantity, body.reason)
    return {"transactions": [{"ingredient_id": t.ingredient_id, "quantity": t.quantity} for t in txns]}
