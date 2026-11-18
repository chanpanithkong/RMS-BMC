import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import func, select

from app.core.dependencies import Ctx, require
from app.core.exceptions import Conflict, NotFound
from app.models import Ingredient, InventoryLocation, InventoryTransaction, StockBalance, StockDocument, UnitOfMeasure
from app.schemas.common import ORM, Page, Strict
from app.services import inventory as svc
from app.services.platform import audit

router = APIRouter(prefix="/inventory", tags=["inventory"])
View = Annotated[Ctx, Depends(require("inventory.view"))]
Manage = Annotated[Ctx, Depends(require("inventory.manage"))]


class UomOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    dimension: str


class IngredientIn(Strict):
    code: str = Field(min_length=1, max_length=20)
    name_en: str = Field(min_length=1, max_length=120)
    name_km: str | None = None
    category: str = Field(min_length=1, max_length=60)
    stock_uom_id: uuid.UUID
    reorder_level: Decimal = Field(Decimal("0"), ge=0)
    reorder_qty: Decimal = Field(Decimal("0"), ge=0)
    track_batch: bool = False
    track_expiry: bool = False


class IngredientPatch(Strict):
    name_en: str | None = None
    name_km: str | None = None
    category: str | None = None
    reorder_level: Decimal | None = Field(None, ge=0)
    reorder_qty: Decimal | None = Field(None, ge=0)
    is_active: bool | None = None


class IngredientOut(ORM):
    id: uuid.UUID
    code: str
    name_en: str
    name_km: str | None
    category: str
    stock_uom_id: uuid.UUID
    reorder_level: Decimal
    reorder_qty: Decimal
    track_batch: bool
    track_expiry: bool
    is_active: bool


class LocationOut(ORM):
    id: uuid.UUID
    name: str
    is_active: bool


class DocLineIn(Strict):
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(description="Positive. For adjustments, the sign is the direction.")
    uom_id: uuid.UUID
    unit_cost: Decimal | None = Field(None, ge=0)
    batch_no: str | None = None
    expiry_date: date | None = None


class DocIn(Strict):
    doc_type: Literal["Receipt", "Issue", "Adjustment", "Wastage", "Opening"]
    location_id: uuid.UUID
    reason: str | None = Field(None, max_length=300)
    lines: list[DocLineIn] = Field(min_length=1)


class DocLineOut(ORM):
    id: uuid.UUID
    ingredient_id: uuid.UUID
    quantity: Decimal
    uom_id: uuid.UUID
    unit_cost: Decimal | None


class DocOut(ORM):
    id: uuid.UUID
    doc_no: str
    doc_type: str
    location_id: uuid.UUID
    status: str
    reason: str | None
    total_value: Decimal
    created_by: uuid.UUID
    approved_by: uuid.UUID | None
    posted_at: datetime | None
    created_at: datetime | None = None
    lines: list[DocLineOut]


class DecisionIn(Strict):
    approve: bool
    note: str | None = None


class ReverseIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


class TxnOut(ORM):
    id: uuid.UUID
    business_date: date
    location_id: uuid.UUID
    ingredient_id: uuid.UUID
    txn_type: str
    quantity: Decimal
    unit_cost: Decimal
    total_cost: Decimal
    balance_after: Decimal
    source_type: str
    source_id: uuid.UUID
    reverses_txn_id: uuid.UUID | None
    reason: str | None
    posted_by: uuid.UUID
    posted_at: datetime


class BalanceOut(ORM):
    location_id: uuid.UUID
    location_name: str
    ingredient_id: uuid.UUID
    ingredient_code: str
    ingredient_name_en: str
    unit: str
    quantity: Decimal
    avg_cost: Decimal
    value: Decimal
    reorder_level: Decimal
    low: bool


@router.get("/units", response_model=list[UomOut])
def units(ctx: View):
    return ctx.db.scalars(select(UnitOfMeasure).order_by(UnitOfMeasure.dimension, UnitOfMeasure.code)).all()


@router.get("/locations", response_model=list[LocationOut])
def locations(ctx: View):
    return ctx.db.scalars(select(InventoryLocation).where(InventoryLocation.branch_id == ctx.branch_id).order_by(InventoryLocation.name)).all()


@router.get("/items", response_model=list[IngredientOut])
def list_items(ctx: View, search: str | None = None, active: bool | None = True):
    stmt = select(Ingredient)
    if search:
        stmt = stmt.where(Ingredient.name_en.ilike(f"%{search}%") | Ingredient.code.ilike(f"%{search}%") | Ingredient.name_km.ilike(f"%{search}%"))
    if active is not None:
        stmt = stmt.where(Ingredient.is_active == active)
    return ctx.db.scalars(stmt.order_by(Ingredient.code)).all()


@router.post("/items", response_model=IngredientOut, status_code=201)
def create_item(body: IngredientIn, ctx: Manage):
    if ctx.db.scalar(select(Ingredient.id).where(Ingredient.code == body.code)):
        raise Conflict("INGREDIENT_CODE_EXISTS", "An ingredient with this code already exists.")
    if ctx.db.get(UnitOfMeasure, body.stock_uom_id) is None:
        raise NotFound("Unit")
    ing = Ingredient(**body.model_dump())
    ctx.db.add(ing)
    ctx.db.flush()
    audit(ctx.db, ctx, "inventory.ingredient_create", "Ingredient", ing.id, after=body.model_dump())
    return ing


@router.patch("/items/{ingredient_id}", response_model=IngredientOut, summary="Master data only; on-hand quantity can't be edited (FR-INV-004)")
def update_item(ingredient_id: uuid.UUID, body: IngredientPatch, ctx: Manage):
    ing = ctx.db.get(Ingredient, ingredient_id)
    if ing is None:
        raise NotFound("Ingredient")
    data = body.model_dump(exclude_unset=True)
    before = {k: getattr(ing, k) for k in data}
    for k, v in data.items():
        setattr(ing, k, v)
    audit(ctx.db, ctx, "inventory.ingredient_update", "Ingredient", ing.id, before=before, after=data)
    return ing


@router.get("/balances", response_model=list[BalanceOut])
def balances(ctx: View, location_id: uuid.UUID | None = None, low_only: bool = False):
    stmt = (select(StockBalance, Ingredient, InventoryLocation).join(Ingredient, Ingredient.id == StockBalance.ingredient_id)
            .join(InventoryLocation, InventoryLocation.id == StockBalance.location_id).where(StockBalance.branch_id == ctx.branch_id))
    if location_id:
        stmt = stmt.where(StockBalance.location_id == location_id)
    out = []
    for b, ing, loc in ctx.db.execute(stmt.order_by(Ingredient.code)).all():
        low = b.quantity <= ing.reorder_level
        if low_only and not low:
            continue
        out.append({"location_id": loc.id, "location_name": loc.name, "ingredient_id": ing.id, "ingredient_code": ing.code, "ingredient_name_en": ing.name_en,
                    "unit": ing.stock_uom.code, "quantity": b.quantity, "avg_cost": b.avg_cost, "value": (max(b.quantity, 0) * b.avg_cost).quantize(Decimal("0.0001")),
                    "reorder_level": ing.reorder_level, "low": low})
    return out


@router.get("/transactions", response_model=Page[TxnOut], summary="Movement history with running balance (FR-INV-014)")
def transactions(ctx: View, ingredient_id: uuid.UUID | None = None, location_id: uuid.UUID | None = None, txn_type: str | None = None,
                 page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(InventoryTransaction).where(InventoryTransaction.branch_id == ctx.branch_id)
    for col, val in ((InventoryTransaction.ingredient_id, ingredient_id), (InventoryTransaction.location_id, location_id), (InventoryTransaction.txn_type, txn_type)):
        if val:
            stmt = stmt.where(col == val)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(InventoryTransaction.posted_at.desc(), InventoryTransaction.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": rows, "total": total, "page": page, "page_size": page_size}


@router.post("/transactions/{txn_id}/reverse", response_model=TxnOut, status_code=201)
def reverse(txn_id: uuid.UUID, body: ReverseIn, ctx: Manage):
    return svc.reverse(ctx, txn_id, body.reason)


@router.post("/documents", response_model=DocOut, status_code=201, summary="Draft a receipt (no PO), issue, adjustment, wastage or opening balance")
def create_document(body: DocIn, ctx: View):
    return svc.create_document(ctx, body.doc_type, body.location_id, [ln.model_dump() for ln in body.lines], body.reason)


@router.get("/documents", response_model=list[DocOut], summary="Stock documents of this branch, newest first (adjustments, wastage, issues, receipts without PO)")
def list_documents(ctx: View, doc_type: str | None = None, status: str | None = None, limit: int = Query(200, ge=1, le=500)):
    stmt = select(StockDocument).where(StockDocument.branch_id == ctx.branch_id)
    if doc_type:
        stmt = stmt.where(StockDocument.doc_type == doc_type)
    if status:
        stmt = stmt.where(StockDocument.status == status)
    return ctx.db.scalars(stmt.order_by(StockDocument.created_at.desc()).limit(limit)).all()


@router.get("/documents/{doc_id}", response_model=DocOut)
def get_document(doc_id: uuid.UUID, ctx: View):
    return svc.get_document(ctx, doc_id)


@router.post("/documents/{doc_id}/post", response_model=DocOut, summary="Post exactly once; repeating returns the posted document (BR-018)")
def post_document(doc_id: uuid.UUID, ctx: View):
    doc = svc.get_document(ctx, doc_id, lock=True)
    if doc.doc_type == "Wastage":
        ctx.require("inventory.wastage")
    else:
        ctx.require("inventory.manage")
    return svc.post_document(ctx, doc)


@router.post("/documents/{doc_id}/decision", response_model=DocOut, summary="Approve or reject an adjustment or wastage above threshold")
def decide(doc_id: uuid.UUID, body: DecisionIn, ctx: Annotated[Ctx, Depends(require("inventory.approve"))]):
    return svc.approve_document(ctx, svc.get_document(ctx, doc_id, lock=True), body.approve, body.note)
