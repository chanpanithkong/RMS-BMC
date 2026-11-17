"""Suppliers and purchasing (PUR)."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import EmailStr, Field
from sqlalchemy import func, select

from app.core.dependencies import Ctx, require
from app.core.exceptions import Conflict, Forbidden
from app.models import GoodsReceipt, PurchaseOrder, PurchaseRequest, PurchaseReturn, Supplier, SupplierInvoice, SupplierItem
from app.schemas.common import Strict
from app.services import purchasing as svc
from app.services.platform import audit

router = APIRouter(tags=["purchasing"])
SView = Annotated[Ctx, Depends(require("suppliers.view"))]
PView = Annotated[Ctx, Depends(require("purchases.view"))]


class SupplierIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    contact_person: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=6, max_length=20)
    email: EmailStr | None = None
    address: str | None = None
    tax_id: str | None = None
    payment_terms: str = "Net 30"
    currency: Literal["USD", "KHR"] = "USD"
    branch_ids: list[uuid.UUID] = Field([], description="Empty = shared by all branches (FR-BRN-005)")


class SupplierPatch(Strict):
    contact_person: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    tax_id: str | None = None
    payment_terms: str | None = None
    status: Literal["Active", "Inactive"] | None = None
    branch_ids: list[uuid.UUID] | None = None


class RequestLine(Strict):
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    uom_id: uuid.UUID


class RequestIn(Strict):
    lines: list[RequestLine] = Field(min_length=1)
    note: str | None = None


class POLine(Strict):
    ingredient_id: uuid.UUID
    qty_ordered: Decimal = Field(gt=0)
    uom_id: uuid.UUID
    unit_price: Decimal = Field(ge=0)


class POIn(Strict):
    supplier_id: uuid.UUID
    location_id: uuid.UUID
    delivery_date: date | None = None
    note: str | None = None
    lines: list[POLine] = Field(min_length=1)
    request_id: uuid.UUID | None = Field(None, description="Convert an approved purchase request")


class POLines(Strict):
    lines: list[POLine] = Field(min_length=1)


class ReasonIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


class GRLine(Strict):
    po_item_id: uuid.UUID | None = None
    ingredient_id: uuid.UUID | None = None
    qty_received: Decimal = Field(ge=0)
    qty_rejected: Decimal = Field(Decimal("0"), ge=0)
    uom_id: uuid.UUID | None = None
    unit_cost: Decimal | None = Field(None, ge=0)
    batch_no: str | None = None
    expiry_date: date | None = None


class GRIn(Strict):
    po_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    lines: list[GRLine] = Field(min_length=1)


class ReturnLine(Strict):
    gr_item_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class ReturnIn(Strict):
    gr_id: uuid.UUID
    reason: str = Field(min_length=2, max_length=300)
    lines: list[ReturnLine] = Field(min_length=1)


class InvoiceIn(Strict):
    supplier_id: uuid.UUID
    invoice_no: str = Field(min_length=1, max_length=40)
    invoice_date: date
    due_date: date
    amount: Decimal = Field(gt=0)
    gr_ids: list[uuid.UUID] = []


class SupplierPaymentIn(Strict):
    amount: Decimal = Field(gt=0)
    method: Literal["BANK_TRANSFER", "CASH", "KHQR", "CHEQUE"]
    reference: str | None = None


def sup_out(s: Supplier) -> dict:
    return {k: getattr(s, k) for k in ("id", "name", "contact_person", "phone", "email", "address", "tax_id", "payment_terms", "currency", "status", "branch_ids")}


def po_out(po: PurchaseOrder) -> dict:
    return {"id": po.id, "po_no": po.po_no, "supplier_id": po.supplier_id, "location_id": po.location_id, "status": po.status, "delivery_date": po.delivery_date,
            "total": po.total, "currency": po.currency, "created_by": po.created_by, "approved_by": po.approved_by, "version": po.version,
            "lines": [{"id": ln.id, "ingredient_id": ln.ingredient_id, "qty_ordered": ln.qty_ordered, "qty_received": ln.qty_received, "uom_id": ln.uom_id,
                       "unit_price": ln.unit_price} for ln in po.lines]}


def gr_out(g: GoodsReceipt) -> dict:
    return {"id": g.id, "gr_no": g.gr_no, "po_id": g.po_id, "supplier_id": g.supplier_id, "location_id": g.location_id, "status": g.status, "is_direct": g.is_direct,
            "exception_note": g.exception_note, "total_value": g.total_value, "received_by": g.received_by, "approved_by": g.approved_by, "posted_at": g.posted_at,
            "lines": [{"id": ln.id, "po_item_id": ln.po_item_id, "ingredient_id": ln.ingredient_id, "qty_received": ln.qty_received, "qty_rejected": ln.qty_rejected,
                       "uom_id": ln.uom_id, "unit_cost": ln.unit_cost, "batch_no": ln.batch_no, "expiry_date": ln.expiry_date} for ln in g.lines]}


def inv_out(i: SupplierInvoice) -> dict:
    return {k: getattr(i, k) for k in ("id", "supplier_id", "invoice_no", "invoice_date", "due_date", "amount", "currency", "gr_ids", "matched_value", "match_status", "status",
                                       "paid_amount")}


# ---------------------------------------------------------------- suppliers
def _branch_ids(ctx: Ctx, ids: list[uuid.UUID]) -> list[str]:
    mine = {b.id for b in ctx.user.branches}
    if set(ids) - mine:
        raise Forbidden("You can only restrict suppliers to branches you're assigned to.", code="BRANCH_FORBIDDEN")
    return sorted(str(i) for i in ids)


@router.get("/suppliers")
def suppliers(ctx: SView, q: str | None = None, status: str | None = None):
    stmt = select(Supplier).where(svc.supplier_visible(ctx))
    if q:
        stmt = stmt.where(Supplier.name.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(Supplier.status == status)
    return [sup_out(s) for s in ctx.db.scalars(stmt.order_by(Supplier.name))]


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn, ctx: Annotated[Ctx, Depends(require("suppliers.manage"))]):
    if ctx.db.scalar(select(Supplier.id).where(func.lower(Supplier.name) == body.name.lower())):
        raise Conflict("SUPPLIER_EXISTS", "A supplier with this name already exists.")
    data = body.model_dump()
    data["branch_ids"] = _branch_ids(ctx, data["branch_ids"])
    s = Supplier(**data)
    ctx.db.add(s)
    ctx.db.flush()
    audit(ctx.db, ctx, "supplier.create", "Supplier", s.id, after=body.model_dump())
    return sup_out(s)


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: uuid.UUID, body: SupplierPatch, ctx: Annotated[Ctx, Depends(require("suppliers.manage"))]):
    s = svc.supplier(ctx, supplier_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("branch_ids") is not None:
        data["branch_ids"] = _branch_ids(ctx, data["branch_ids"])
    before = {k: getattr(s, k) for k in data}
    for k, v in data.items():
        setattr(s, k, v)
    audit(ctx.db, ctx, "supplier.update", "Supplier", s.id, before=before, after=data)
    return sup_out(s)


@router.get("/suppliers/{supplier_id}/history", summary="POs, receipts, invoices, returns, prices and balance (FR-PUR-011/012)")
def history(supplier_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("suppliers.view", "purchases.view"))]):
    s = svc.supplier(ctx, supplier_id)
    db = ctx.db
    grs = db.scalars(select(GoodsReceipt).where(GoodsReceipt.supplier_id == s.id).order_by(GoodsReceipt.created_at.desc()).limit(100)).all()
    return {"supplier": sup_out(s), **svc.supplier_balance(ctx, s),
            "purchase_orders": [{"id": p.id, "po_no": p.po_no, "status": p.status, "total": p.total} for p in db.scalars(select(PurchaseOrder).where(PurchaseOrder.supplier_id == s.id).order_by(PurchaseOrder.created_at.desc()).limit(100))],
            "receipts": [{"id": g.id, "gr_no": g.gr_no, "status": g.status, "value": g.total_value} for g in grs],
            "returns": [{"id": r.id, "return_no": r.return_no, "value": r.total_value} for r in db.scalars(select(PurchaseReturn).where(PurchaseReturn.gr_id.in_([g.id for g in grs] or [None])))],
            "invoices": [inv_out(i) for i in db.scalars(select(SupplierInvoice).where(SupplierInvoice.supplier_id == s.id).order_by(SupplierInvoice.invoice_date.desc()))],
            "item_prices": [{"ingredient_id": si.ingredient_id, "unit_price": si.unit_price, "uom_id": si.uom_id} for si in db.scalars(select(SupplierItem).where(SupplierItem.supplier_id == s.id))]}


# ---------------------------------------------------------------- requests
@router.get("/reorder-suggestions", summary="Ingredients at or below reorder level with suggested quantities")
def reorder(ctx: PView):
    return svc.low_stock_lines(ctx)


@router.get("/purchase-requests")
def list_requests(ctx: PView, status: str | None = None):
    stmt = select(PurchaseRequest).where(PurchaseRequest.branch_id == ctx.branch_id)
    if status:
        stmt = stmt.where(PurchaseRequest.status == status)
    return [{"id": r.id, "request_no": r.request_no, "source": r.source, "status": r.status, "requested_by": r.requested_by, "purchase_order_id": r.purchase_order_id,
             "lines": [{"ingredient_id": ln.ingredient_id, "quantity": ln.quantity, "uom_id": ln.uom_id} for ln in r.lines]}
            for r in ctx.db.scalars(stmt.order_by(PurchaseRequest.created_at.desc()))]


@router.post("/purchase-requests", status_code=201)
def create_request(body: RequestIn, ctx: Annotated[Ctx, Depends(require("purchases.request"))]):
    r = svc.create_request(ctx, [ln.model_dump() for ln in body.lines], "Manual", body.note)
    return {"id": r.id, "request_no": r.request_no, "status": r.status}


@router.post("/purchase-requests/from-low-stock", status_code=201, summary="Request every low-stock ingredient at its reorder quantity")
def request_low_stock(ctx: Annotated[Ctx, Depends(require("purchases.request"))]):
    lines = [{"ingredient_id": x["ingredient_id"], "quantity": x["suggested_qty"], "uom_id": x["uom_id"]} for x in svc.low_stock_lines(ctx) if x["suggested_qty"] > 0]
    r = svc.create_request(ctx, lines, "LowStock", None)
    return {"id": r.id, "request_no": r.request_no, "lines": len(lines)}


@router.post("/purchase-requests/{request_id}/{decision}")
def decide_request(request_id: uuid.UUID, decision: Literal["approve", "reject"], ctx: Annotated[Ctx, Depends(require("purchases.approve"))]):
    r = svc.decide_request(ctx, svc._get(ctx, PurchaseRequest, request_id, lock=True), decision == "approve")
    return {"id": r.id, "status": r.status}


# ---------------------------------------------------------------- purchase orders
@router.get("/purchase-orders")
def list_pos(ctx: PView, status: str | None = None, supplier_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(PurchaseOrder).where(PurchaseOrder.branch_id == ctx.branch_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(PurchaseOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": [po_out(p) for p in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/purchase-orders", status_code=201)
def create_po(body: POIn, ctx: Annotated[Ctx, Depends(require("purchases.create"))]):
    return po_out(svc.create_po(ctx, body.supplier_id, body.location_id, [ln.model_dump() for ln in body.lines], body.delivery_date, body.note, body.request_id))


@router.get("/purchase-orders/{po_id}", summary="Purchase order document data (printing and PDF are not built yet)")
def get_po(po_id: uuid.UUID, ctx: PView):
    return po_out(svc._get(ctx, PurchaseOrder, po_id))


@router.put("/purchase-orders/{po_id}/lines", summary="Changing an approved PO sends it back for approval (BR-017)")
def set_lines(po_id: uuid.UUID, body: POLines, ctx: Annotated[Ctx, Depends(require("purchases.create"))]):
    return po_out(svc.update_po_lines(ctx, svc._get(ctx, PurchaseOrder, po_id, lock=True), [ln.model_dump() for ln in body.lines]))


@router.post("/purchase-orders/{po_id}/submit")
def submit(po_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("purchases.create"))]):
    return po_out(svc.submit_po(ctx, svc._get(ctx, PurchaseOrder, po_id, lock=True)))


@router.post("/purchase-orders/{po_id}/approve", summary="Creator can't approve; amount must be within the approver's po_amount limit")
def approve(po_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("purchases.approve"))]):
    return po_out(svc.approve_po(ctx, svc._get(ctx, PurchaseOrder, po_id, lock=True)))


@router.post("/purchase-orders/{po_id}/send")
def send(po_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("purchases.create"))]):
    return po_out(svc.send_po(ctx, svc._get(ctx, PurchaseOrder, po_id, lock=True)))


@router.post("/purchase-orders/{po_id}/cancel")
def cancel(po_id: uuid.UUID, body: ReasonIn, ctx: Annotated[Ctx, Depends(require("purchases.create"))]):
    return po_out(svc.cancel_po(ctx, svc._get(ctx, PurchaseOrder, po_id, lock=True), body.reason))


# ---------------------------------------------------------------- receipts, returns, invoices
@router.get("/goods-receipts")
def list_grs(ctx: PView, status: str | None = None):
    stmt = select(GoodsReceipt).where(GoodsReceipt.branch_id == ctx.branch_id)
    if status:
        stmt = stmt.where(GoodsReceipt.status == status)
    return [gr_out(g) for g in ctx.db.scalars(stmt.order_by(GoodsReceipt.created_at.desc()).limit(200))]


@router.post("/goods-receipts", status_code=201, summary="Record a receipt against a PO, or a flagged direct receipt")
def create_gr(body: GRIn, ctx: Annotated[Ctx, Depends(require("goods_receipts.post"))]):
    return gr_out(svc.create_receipt(ctx, body.po_id, body.supplier_id, body.location_id, [ln.model_dump() for ln in body.lines]))


@router.post("/goods-receipts/{gr_id}/post", summary="Posts to stock exactly once (BR-018); over tolerance goes to approval (BR-042)")
def post_gr(gr_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("goods_receipts.post"))]):
    return gr_out(svc.post_receipt(ctx, svc._get(ctx, GoodsReceipt, gr_id, lock=True)))


@router.post("/goods-receipts/{gr_id}/approve")
def approve_gr(gr_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("purchases.approve"))]):
    return gr_out(svc.approve_receipt(ctx, svc._get(ctx, GoodsReceipt, gr_id, lock=True)))


@router.post("/purchase-returns", status_code=201)
def create_return(body: ReturnIn, ctx: Annotated[Ctx, Depends(require("goods_receipts.post"))]):
    r = svc.create_return(ctx, svc._get(ctx, GoodsReceipt, body.gr_id, lock=True), [ln.model_dump() for ln in body.lines], body.reason)
    return {"id": r.id, "return_no": r.return_no, "total_value": r.total_value}


@router.get("/supplier-invoices")
def list_invoices(ctx: PView, status: str | None = None, match_status: str | None = None):
    stmt = select(SupplierInvoice).where(SupplierInvoice.branch_id == ctx.branch_id)
    if status:
        stmt = stmt.where(SupplierInvoice.status == status)
    if match_status:
        stmt = stmt.where(SupplierInvoice.match_status == match_status)
    return [inv_out(i) for i in ctx.db.scalars(stmt.order_by(SupplierInvoice.due_date))]


@router.post("/supplier-invoices", status_code=201, summary="Record and match against posted receipts (FR-PUR-010)")
def create_invoice(body: InvoiceIn, ctx: Annotated[Ctx, Depends(require("supplier_payments.create"))]):
    return inv_out(svc.create_invoice(ctx, body.model_dump()))


@router.post("/supplier-invoices/{invoice_id}/payments", status_code=201)
def pay_invoice(invoice_id: uuid.UUID, body: SupplierPaymentIn, ctx: Annotated[Ctx, Depends(require("supplier_payments.create"))]):
    i = svc._get(ctx, SupplierInvoice, invoice_id, lock=True)
    svc.pay_invoice(ctx, i, body.amount, body.method, body.reference)
    return inv_out(i)
