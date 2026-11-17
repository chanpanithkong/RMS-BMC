"""Inventory ledger (SRS §6.10, §10.9; BR-015, BR-016, BR-018, BR-019, BR-022, BR-040)."""
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.models import Ingredient, InventoryLocation, InventoryTransaction, StockBalance, StockDocument, StockDocumentLine, UnitConversion, UnitOfMeasure
from app.services.platform import audit, next_number, notify_permission
from app.utils.money import ZERO, q4
from app.utils.timeutil import utcnow

DOC_TXN = {"Receipt": "RECEIPT", "Issue": "ISSUE", "Wastage": "WASTE", "Adjustment": "ADJUSTMENT", "Opening": "OPENING"}
NEEDS_APPROVAL_ABOVE_THRESHOLD = {"Adjustment", "Wastage"}


def to_stock_qty(ctx: Ctx, ingredient: Ingredient, qty: Decimal, uom_id: uuid.UUID) -> Decimal:
    """BR-015: same dimension by fixed factors; across dimensions only through an ingredient conversion."""
    if uom_id == ingredient.stock_uom_id:
        return q4(qty)
    src = ctx.db.get(UnitOfMeasure, uom_id)
    dst = ingredient.stock_uom
    if src is None:
        raise NotFound("Unit")
    if src.dimension == dst.dimension:
        return q4(qty * src.factor_to_base / dst.factor_to_base)
    conv = ctx.db.scalar(select(UnitConversion).where(UnitConversion.ingredient_id == ingredient.id, UnitConversion.from_uom_id == uom_id, UnitConversion.to_uom_id == dst.id))
    if conv is None:
        raise BusinessRuleError("UNIT_INCOMPATIBLE", f"{src.code} can't be converted to {dst.code} for {ingredient.name_en}.")
    return q4(qty * conv.factor)


def _balance(ctx: Ctx, location_id: uuid.UUID, ingredient_id: uuid.UUID) -> StockBalance:
    bal = ctx.db.get(StockBalance, (location_id, ingredient_id), with_for_update=True)
    if bal is None:
        bal = StockBalance(location_id=location_id, ingredient_id=ingredient_id, branch_id=ctx.branch_id, quantity=ZERO, avg_cost=ZERO)
        ctx.db.add(bal)
        ctx.db.flush()
    return bal


def post_txn(ctx: Ctx, *, location_id, ingredient: Ingredient, txn_type: str, quantity: Decimal, unit_cost: Decimal | None, source_type: str, source_id, source_line_id,
             reason: str | None, reverses: uuid.UUID | None = None, allow_negative: bool = False) -> InventoryTransaction:
    """The only way stock changes (BR-016). Balance row is locked and updated in the same transaction."""
    bal = _balance(ctx, location_id, ingredient.id)
    new_qty = bal.quantity + quantity
    if new_qty < 0 and not allow_negative:
        raise BusinessRuleError("INSUFFICIENT_STOCK", f"Only {bal.quantity} {ingredient.stock_uom.code} of {ingredient.name_en} on hand.")  # BR-040
    cost = unit_cost if unit_cost is not None else bal.avg_cost
    if quantity > 0 and txn_type in ("RECEIPT", "OPENING", "TRANSFER_IN") and new_qty > 0:
        bal.avg_cost = ((max(bal.quantity, ZERO) * bal.avg_cost + quantity * cost) / (max(bal.quantity, ZERO) + quantity)).quantize(Decimal("0.000001"))  # WAC (A-16)
    bal.quantity = new_qty
    txn = InventoryTransaction(branch_id=ctx.branch_id, business_date=ctx.business_date(), location_id=location_id, ingredient_id=ingredient.id, txn_type=txn_type,
                               quantity=quantity, unit_cost=cost, total_cost=q4(quantity * cost), balance_after=new_qty, source_type=source_type, source_id=source_id,
                               source_line_id=source_line_id, reverses_txn_id=reverses, reason=reason, posted_by=ctx.user_id)
    ctx.db.add(txn)
    ctx.db.flush()
    if ingredient.reorder_level and bal.quantity <= ingredient.reorder_level < bal.quantity - quantity:
        notify_permission(ctx.db, ctx.branch_id, "inventory.manage", "Stock", f"Low stock: {ingredient.name_en}",
                          f"On hand {q4(bal.quantity)} {ingredient.stock_uom.code}, reorder level {ingredient.reorder_level}.", "/inventory")  # FR-INV-013
    return txn


def create_document(ctx: Ctx, doc_type: str, location_id: uuid.UUID, lines: list[dict], reason: str | None) -> StockDocument:
    db = ctx.db
    loc = db.get(InventoryLocation, location_id)
    if loc is None or loc.branch_id != ctx.branch_id:
        raise NotFound("Location")
    if doc_type in ("Adjustment", "Wastage", "Issue") and not reason:
        raise BusinessRuleError("REASON_REQUIRED", "A reason is required.", details=[{"field": "reason", "issue": "required"}])
    if doc_type == "Wastage":
        ctx.require("inventory.wastage")
    else:
        ctx.require("inventory.manage")
    doc = StockDocument(branch_id=ctx.branch_id, doc_type=doc_type, location_id=location_id, reason=reason, created_by=ctx.user_id,
                        doc_no=f"{doc_type[:3].upper()}-{next_number(db, ctx.branch_id, 'STOCKDOC', 'S'):06d}")
    db.add(doc)
    db.flush()
    value = ZERO
    for ln in lines:
        ing = db.get(Ingredient, ln["ingredient_id"])
        if ing is None or not ing.is_active:
            raise NotFound("Ingredient")
        qty = Decimal(str(ln["quantity"]))
        if doc_type != "Adjustment" and qty <= 0:
            raise BusinessRuleError("VALIDATION_ERROR", "Quantity must be above zero.", details=[{"field": "lines.quantity", "issue": "must be > 0"}])
        stock_qty = to_stock_qty(ctx, ing, abs(qty), ln["uom_id"])
        bal = db.get(StockBalance, (location_id, ing.id))
        cost = Decimal(str(ln["unit_cost"])) if ln.get("unit_cost") is not None else (bal.avg_cost if bal else ZERO)
        value += stock_qty * cost
        db.add(StockDocumentLine(document_id=doc.id, ingredient_id=ing.id, quantity=qty, uom_id=ln["uom_id"], unit_cost=ln.get("unit_cost"),
                                 batch_no=ln.get("batch_no"), expiry_date=ln.get("expiry_date")))
    doc.total_value = q4(value)
    db.flush()
    db.refresh(doc)
    audit(db, ctx, "inventory.document_create", "StockDocument", doc.id, after={"type": doc_type, "lines": len(lines), "value": doc.total_value}, reason=reason)
    return doc


def get_document(ctx: Ctx, doc_id: uuid.UUID, lock: bool = False) -> StockDocument:
    stmt = select(StockDocument).where(StockDocument.id == doc_id, StockDocument.branch_id == ctx.branch_id)
    doc = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if doc is None:
        raise NotFound("Stock document")
    return doc


def post_document(ctx: Ctx, doc: StockDocument) -> StockDocument:
    """Posting is idempotent: a Posted document returns as-is with no new transactions (BR-018, AT-INV-01)."""
    if doc.status == "Posted":
        return doc
    if doc.status == "Rejected":
        raise Conflict("DOCUMENT_REJECTED", "This document was rejected.")
    if doc.doc_type in NEEDS_APPROVAL_ABOVE_THRESHOLD and doc.status == "Draft" and doc.total_value > ctx.limit("adjustment_value"):
        doc.status = "PendingApproval"  # BR-016, BR-019
        notify_permission(ctx.db, ctx.branch_id, "inventory.approve", "Approval", f"{doc.doc_type} awaiting approval", f"{doc.doc_no}: value {doc.total_value}", "/inventory?tab=counts")
        audit(ctx.db, ctx, "inventory.document_pending", "StockDocument", doc.id, after={"value": doc.total_value})
        return doc
    if doc.status == "PendingApproval":
        raise Conflict("APPROVAL_PENDING", "This document is waiting for approval.")
    _post(ctx, doc)
    return doc


def approve_document(ctx: Ctx, doc: StockDocument, approve: bool, note: str | None) -> StockDocument:
    ctx.require("inventory.approve")
    if doc.status != "PendingApproval":
        raise Conflict("NOT_PENDING", "This document isn't waiting for approval.")
    if doc.created_by == ctx.user_id:
        raise Forbidden("You can't approve your own document.", code="SELF_APPROVAL")  # BR-029
    if doc.total_value > ctx.limit("adjustment_value"):
        raise Forbidden("This exceeds your approval limit.", code="APPROVER_LIMIT_EXCEEDED")
    doc.approved_by = ctx.user_id
    if not approve:
        doc.status = "Rejected"
        audit(ctx.db, ctx, "inventory.document_reject", "StockDocument", doc.id, reason=note)
        return doc
    _post(ctx, doc)
    return doc


def _post(ctx: Ctx, doc: StockDocument) -> None:
    sign = -1 if doc.doc_type in ("Issue", "Wastage") else 1
    txn_type = DOC_TXN[doc.doc_type]
    for ln in doc.lines:
        ing = ctx.db.get(Ingredient, ln.ingredient_id)
        qty = to_stock_qty(ctx, ing, abs(ln.quantity), ln.uom_id) * (sign if doc.doc_type != "Adjustment" else (1 if ln.quantity > 0 else -1))
        post_txn(ctx, location_id=doc.location_id, ingredient=ing, txn_type=txn_type, quantity=qty, unit_cost=ln.unit_cost, source_type=f"StockDocument:{doc.doc_type}",
                 source_id=doc.id, source_line_id=ln.id, reason=doc.reason)
        if doc.doc_type in ("Receipt", "Opening"):
            from app.services.recipes import record_batch

            record_batch(ctx, doc.location_id, ing.id, ln.batch_no, ln.expiry_date, qty, "StockDocument", ln.id)
    doc.status, doc.posted_by, doc.posted_at = "Posted", ctx.user_id, utcnow()
    audit(ctx.db, ctx, "inventory.document_post", "StockDocument", doc.id, after={"type": doc.doc_type, "value": doc.total_value, "approved_by": doc.approved_by}, reason=doc.reason)


def reverse(ctx: Ctx, txn_id: uuid.UUID, reason: str) -> InventoryTransaction:
    """FR-INV-015: opposite-sign REVERSAL referencing the original; the original is never edited."""
    ctx.require("inventory.manage")
    db = ctx.db
    orig = db.scalar(select(InventoryTransaction).where(InventoryTransaction.id == txn_id, InventoryTransaction.branch_id == ctx.branch_id))
    if orig is None:
        raise NotFound("Inventory transaction")
    if orig.txn_type == "REVERSAL":
        raise Conflict("CANNOT_REVERSE_REVERSAL", "Post a new correcting transaction instead of reversing a reversal.")
    if db.scalar(select(InventoryTransaction.id).where(InventoryTransaction.reverses_txn_id == orig.id)):
        raise Conflict("ALREADY_REVERSED", "This transaction was already reversed.")
    ing = db.get(Ingredient, orig.ingredient_id)
    txn = post_txn(ctx, location_id=orig.location_id, ingredient=ing, txn_type="REVERSAL", quantity=-orig.quantity, unit_cost=orig.unit_cost, source_type="Reversal",
                   source_id=orig.id, source_line_id=orig.id, reason=reason, reverses=orig.id)
    audit(db, ctx, "inventory.reverse", "InventoryTransaction", orig.id, after={"reversal_id": txn.id, "quantity": txn.quantity}, reason=reason)
    return txn
