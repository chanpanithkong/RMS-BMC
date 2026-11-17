"""Purchasing and suppliers (SRS §6.12; BR-017, BR-018, BR-029, BR-042, BR-043)."""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.models import (GoodsReceipt, GoodsReceiptItem, Ingredient, InventoryLocation, OutboxEvent, PurchaseOrder, PurchaseOrderItem, PurchaseRequest, PurchaseRequestLine,
                        PurchaseReturn, PurchaseReturnLine, StockBalance, Supplier, SupplierInvoice, SupplierItem, SupplierPayment)
from app.services import inventory as inv
from app.services.platform import audit, get_setting, next_number, notify_permission
from app.services.recipes import record_batch
from app.utils.money import ZERO, q, q4
from app.utils.timeutil import utcnow

HUNDRED = Decimal(100)


def _get(ctx: Ctx, model, oid: uuid.UUID, lock: bool = False, branch: bool = True):
    stmt = select(model).where(model.id == oid)
    if branch:
        stmt = stmt.where(model.branch_id == ctx.branch_id)
    obj = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if obj is None:
        raise NotFound(model.__name__)
    return obj


def supplier(ctx: Ctx, sid: uuid.UUID) -> Supplier:
    s = _get(ctx, Supplier, sid, branch=False)
    if s.branch_ids and str(ctx.branch_id) not in s.branch_ids:
        raise NotFound("Supplier")  # restricted to other branches (FR-BRN-005)
    return s


def supplier_visible(ctx: Ctx):
    """SQL filter: shared suppliers plus those restricted to this branch."""
    return (func.cardinality(Supplier.branch_ids) == 0) | Supplier.branch_ids.any(str(ctx.branch_id))


# ---------------------------------------------------------------- requests (FR-PUR-002)
def create_request(ctx: Ctx, lines: list[dict], source: str, note: str | None) -> PurchaseRequest:
    if not lines:
        raise BusinessRuleError("REQUEST_EMPTY", "Nothing to request.")
    r = PurchaseRequest(branch_id=ctx.branch_id, request_no=f"PR-{next_number(ctx.db, ctx.branch_id, 'PURREQ', 'PR'):06d}", source=source, requested_by=ctx.user_id, note=note)
    ctx.db.add(r)
    ctx.db.flush()
    ctx.db.add_all([PurchaseRequestLine(request_id=r.id, **ln) for ln in lines])
    ctx.db.flush()
    ctx.db.refresh(r)
    audit(ctx.db, ctx, "purchase.request", "PurchaseRequest", r.id, after={"lines": len(lines), "source": source})
    return r


def low_stock_lines(ctx: Ctx) -> list[dict]:
    rows = ctx.db.execute(select(Ingredient, func.coalesce(func.sum(StockBalance.quantity), 0)).outerjoin(
        StockBalance, (StockBalance.ingredient_id == Ingredient.id) & (StockBalance.branch_id == ctx.branch_id)).where(Ingredient.is_active)
        .group_by(Ingredient.id)).all()
    out = []
    for ing, on_hand in rows:
        if ing.reorder_level and on_hand <= ing.reorder_level:
            qty = ing.reorder_qty or (ing.reorder_level - on_hand)
            pref = ctx.db.scalar(select(SupplierItem).where(SupplierItem.ingredient_id == ing.id).order_by(SupplierItem.is_preferred.desc()).limit(1))
            out.append({"ingredient_id": ing.id, "ingredient": ing.name_en, "on_hand": on_hand, "reorder_level": ing.reorder_level, "suggested_qty": qty,
                        "uom_id": ing.stock_uom_id, "preferred_supplier_id": pref.supplier_id if pref else None, "last_price": pref.unit_price if pref else None})
    return out


def decide_request(ctx: Ctx, r: PurchaseRequest, approve: bool) -> PurchaseRequest:
    ctx.require("purchases.approve")
    if r.status != "Submitted":
        raise Conflict("REQUEST_DECIDED", f"This request is {r.status}.")
    if r.requested_by == ctx.user_id:
        raise Forbidden("You can't approve your own request.", code="SELF_APPROVAL")
    r.status, r.decided_by = ("Approved" if approve else "Rejected"), ctx.user_id
    audit(ctx.db, ctx, f"purchase.request_{r.status.lower()}", "PurchaseRequest", r.id)
    return r


# ---------------------------------------------------------------- purchase orders (BR-017)
def _set_lines(ctx: Ctx, po: PurchaseOrder, lines: list[dict]) -> None:
    for old in list(po.lines):
        ctx.db.delete(old)
    ctx.db.flush()
    total = ZERO
    for ln in lines:
        ing = ctx.db.get(Ingredient, ln["ingredient_id"])
        if ing is None:
            raise NotFound("Ingredient")
        inv.to_stock_qty(ctx, ing, Decimal("1"), ln["uom_id"])  # unit must convert to the stock unit
        ctx.db.add(PurchaseOrderItem(po_id=po.id, **ln))
        total += ln["qty_ordered"] * ln["unit_price"]
    po.total = q(total)
    ctx.db.flush()
    ctx.db.refresh(po)


def create_po(ctx: Ctx, supplier_id: uuid.UUID, location_id: uuid.UUID, lines: list[dict], delivery_date: date | None, note: str | None, request_id: uuid.UUID | None = None) -> PurchaseOrder:
    s = supplier(ctx, supplier_id)
    if s.status != "Active":
        raise Conflict("SUPPLIER_INACTIVE", "This supplier is inactive.")
    loc = ctx.db.get(InventoryLocation, location_id)
    if loc is None or loc.branch_id != ctx.branch_id:
        raise NotFound("Location")
    po = PurchaseOrder(branch_id=ctx.branch_id, po_no=f"PO-{next_number(ctx.db, ctx.branch_id, 'PO', 'PO'):06d}", supplier_id=s.id, location_id=location_id,
                       delivery_date=delivery_date, note=note, created_by=ctx.user_id, currency=s.currency)
    ctx.db.add(po)
    ctx.db.flush()
    _set_lines(ctx, po, lines)
    if request_id:
        r = _get(ctx, PurchaseRequest, request_id, lock=True)
        if r.status != "Approved":
            raise Conflict("REQUEST_NOT_APPROVED", "Only approved requests can become purchase orders.")
        r.status, r.purchase_order_id = "Converted", po.id
    audit(ctx.db, ctx, "purchase.po_create", "PurchaseOrder", po.id, after={"po_no": po.po_no, "supplier": s.name, "total": po.total})
    return po


def update_po_lines(ctx: Ctx, po: PurchaseOrder, lines: list[dict]) -> PurchaseOrder:
    if po.status not in ("Draft", "Submitted", "Approved"):
        raise Conflict("PO_LOCKED", f"A {po.status} purchase order can't be changed.")
    before = po.total
    was_approved = po.status == "Approved"
    _set_lines(ctx, po, lines)
    if was_approved:  # BR-017: changing an approved PO sends it back for approval
        po.status, po.approved_by, po.approved_at = "Submitted", None, None
    audit(ctx.db, ctx, "purchase.po_update", "PurchaseOrder", po.id, before={"total": before}, after={"total": po.total, "status": po.status})
    return po


def submit_po(ctx: Ctx, po: PurchaseOrder) -> PurchaseOrder:
    if po.status != "Draft":
        raise Conflict("PO_NOT_DRAFT", f"This purchase order is {po.status}.")
    if not po.lines:
        raise BusinessRuleError("PO_EMPTY", "Add at least one line.")
    po.status, po.submitted_at = "Submitted", utcnow()
    notify_permission(ctx.db, ctx.branch_id, "purchases.approve", "Approval", f"{po.po_no} awaiting approval", f"Total {po.total} {po.currency}", "/purchasing?tab=orders")
    audit(ctx.db, ctx, "purchase.po_submit", "PurchaseOrder", po.id)
    return po


def approve_po(ctx: Ctx, po: PurchaseOrder) -> PurchaseOrder:
    ctx.require("purchases.approve")
    if po.status != "Submitted":
        raise Conflict("PO_NOT_SUBMITTED", f"This purchase order is {po.status}.")
    if po.created_by == ctx.user_id:
        raise Forbidden("The creator can't approve this purchase order.", code="SELF_APPROVAL")  # BR-017, BR-029
    if po.total > ctx.limit("po_amount"):
        raise Forbidden(f"This purchase order exceeds your approval limit of {ctx.limit('po_amount')}.", code="APPROVER_LIMIT_EXCEEDED")
    po.status, po.approved_by, po.approved_at = "Approved", ctx.user_id, utcnow()
    audit(ctx.db, ctx, "purchase.po_approve", "PurchaseOrder", po.id, after={"total": po.total})
    return po


def send_po(ctx: Ctx, po: PurchaseOrder) -> PurchaseOrder:
    if po.status != "Approved":
        raise Conflict("PO_NOT_APPROVED", "Only approved purchase orders can be sent.")
    po.status, po.sent_at = "Sent", utcnow()
    s = supplier(ctx, po.supplier_id)
    if s.email:
        from app.models import UnitOfMeasure

        names = dict(ctx.db.execute(select(Ingredient.id, Ingredient.name_en).where(Ingredient.id.in_([ln.ingredient_id for ln in po.lines]))).all())
        units = dict(ctx.db.execute(select(UnitOfMeasure.id, UnitOfMeasure.code).where(UnitOfMeasure.id.in_([ln.uom_id for ln in po.lines]))).all())
        ctx.db.add(OutboxEvent(branch_id=ctx.branch_id, event_type="email.purchase_order", topic="email",
                               payload={"po_id": str(po.id), "po_no": po.po_no, "email": s.email, "supplier": s.name, "total": str(po.total), "currency": po.currency,
                                        "delivery_date": po.delivery_date.isoformat() if po.delivery_date else None, "branch": ctx.branch.name_en,
                                        "lines": [{"item": names.get(ln.ingredient_id), "quantity": str(ln.qty_ordered), "unit": units.get(ln.uom_id),
                                                   "unit_price": str(ln.unit_price)} for ln in po.lines]}))
    audit(ctx.db, ctx, "purchase.po_send", "PurchaseOrder", po.id)
    return po


def cancel_po(ctx: Ctx, po: PurchaseOrder, reason: str) -> PurchaseOrder:
    if po.status in ("PartiallyReceived", "Received", "Closed", "Cancelled"):
        raise Conflict("PO_LOCKED", f"A {po.status} purchase order can't be cancelled.")
    po.status, po.cancel_reason = "Cancelled", reason
    audit(ctx.db, ctx, "purchase.po_cancel", "PurchaseOrder", po.id, reason=reason)
    return po


# ---------------------------------------------------------------- goods receipts (BR-018, BR-042)
def create_receipt(ctx: Ctx, po_id: uuid.UUID | None, supplier_id: uuid.UUID | None, location_id: uuid.UUID | None, lines: list[dict]) -> GoodsReceipt:
    db = ctx.db
    po = None
    if po_id:
        po = _get(ctx, PurchaseOrder, po_id, lock=True)
        if po.status not in ("Approved", "Sent", "PartiallyReceived"):
            raise Conflict("PO_NOT_RECEIVABLE", f"A {po.status} purchase order can't be received.")
        supplier_id, location_id = po.supplier_id, location_id or po.location_id
    elif not supplier_id or not location_id:
        raise BusinessRuleError("VALIDATION_ERROR", "A direct receipt needs a supplier and a location.")
    is_direct = po is None
    if is_direct:
        ctx.require("purchases.create")
    gr = GoodsReceipt(branch_id=ctx.branch_id, gr_no=f"GR-{next_number(db, ctx.branch_id, 'GR', 'GR'):06d}", po_id=po_id, supplier_id=supplier_id, location_id=location_id,
                      is_direct=is_direct, exception_note="Direct receipt without PO, needs retrospective approval" if is_direct else None, received_by=ctx.user_id)
    db.add(gr)
    db.flush()
    po_items = {pi.id: pi for pi in po.lines} if po else {}
    total = ZERO
    for ln in lines:
        if ln.get("po_item_id") and ln["po_item_id"] not in po_items:
            raise BusinessRuleError("PO_LINE_UNKNOWN", "A receipt line doesn't belong to this purchase order.")
        if ln.get("po_item_id"):
            pi = po_items[ln["po_item_id"]]
            if ln.get("ingredient_id") is None:
                ln["ingredient_id"] = pi.ingredient_id
            elif ln["ingredient_id"] != pi.ingredient_id:
                raise BusinessRuleError("PO_LINE_MISMATCH", "The ingredient doesn't match the purchase order line.")
            if ln.get("uom_id") is None:
                ln["uom_id"] = pi.uom_id
            if ln.get("unit_cost") is None:
                ln["unit_cost"] = pi.unit_price
        elif ln.get("ingredient_id") is None or ln.get("uom_id") is None or ln.get("unit_cost") is None:
            raise BusinessRuleError("VALIDATION_ERROR", "Lines without a PO line need an ingredient, unit and unit cost.")
        db.add(GoodsReceiptItem(gr_id=gr.id, **{k: v for k, v in ln.items() if v is not None}))
        total += Decimal(str(ln["qty_received"])) * Decimal(str(ln["unit_cost"]))
    gr.total_value = q(total)
    db.flush()
    db.refresh(gr)
    audit(db, ctx, "purchase.gr_create", "GoodsReceipt", gr.id, after={"po": po.po_no if po else None, "value": gr.total_value, "direct": is_direct})
    return gr


def _tolerance_breaches(ctx: Ctx, gr: GoodsReceipt) -> list[str]:
    if not gr.po_id:
        return ["direct receipt"]
    s = get_setting(ctx.db, "purchasing", ctx.branch_id)
    qty_tol = Decimal(str(s["receipt_tolerance_pct"])) / HUNDRED
    issues = []
    for ln in gr.lines:
        if not ln.po_item_id:
            continue
        pi = ctx.db.get(PurchaseOrderItem, ln.po_item_id)
        if pi.qty_received + ln.qty_received > pi.qty_ordered * (1 + qty_tol):
            ing = ctx.db.get(Ingredient, ln.ingredient_id)
            issues.append(f"{ing.name_en}: {pi.qty_received + ln.qty_received} received against {pi.qty_ordered} ordered (+{s['receipt_tolerance_pct']}% allowed)")
    return issues


def _price_flags(ctx: Ctx, gr: GoodsReceipt) -> list[str]:
    tol = Decimal(str(get_setting(ctx.db, "purchasing", ctx.branch_id)["price_tolerance_pct"])) / HUNDRED
    flags = []
    for ln in gr.lines:
        if ln.po_item_id:
            pi = ctx.db.get(PurchaseOrderItem, ln.po_item_id)
            if pi.unit_price and abs(ln.unit_cost - pi.unit_price) > pi.unit_price * tol:
                flags.append(f"price {ln.unit_cost} vs PO {pi.unit_price}")
    return flags


def post_receipt(ctx: Ctx, gr: GoodsReceipt) -> GoodsReceipt:
    """Idempotent: a Posted receipt returns unchanged (AT-PUR-02). Over-tolerance goes to approval (AT-PUR-03)."""
    if gr.status == "Posted":
        return gr
    if gr.status == "Reversed":
        raise Conflict("GR_REVERSED", "This receipt was reversed.")
    if gr.status == "PendingApproval":
        raise Conflict("APPROVAL_PENDING", "This receipt is waiting for approval.")
    s = get_setting(ctx.db, "purchasing", ctx.branch_id)
    if s.get("separate_receiver") and gr.po_id and ctx.db.get(PurchaseOrder, gr.po_id).created_by == ctx.user_id:
        raise Forbidden("The PO creator can't post its receipt in this branch.", code="SEPARATION_OF_DUTIES")
    breaches = _tolerance_breaches(ctx, gr)
    if breaches:
        gr.status = "PendingApproval"
        gr.exception_note = "; ".join(breaches)
        notify_permission(ctx.db, ctx.branch_id, "purchases.approve", "Approval", f"{gr.gr_no} needs approval", gr.exception_note, "/purchasing?tab=receipts")
        audit(ctx.db, ctx, "purchase.gr_pending", "GoodsReceipt", gr.id, after={"issues": breaches})
        return gr
    _post(ctx, gr)
    return gr


def approve_receipt(ctx: Ctx, gr: GoodsReceipt) -> GoodsReceipt:
    ctx.require("purchases.approve")
    if gr.status != "PendingApproval":
        raise Conflict("NOT_PENDING", "This receipt isn't waiting for approval.")
    if gr.received_by == ctx.user_id:
        raise Forbidden("You can't approve your own receipt.", code="SELF_APPROVAL")
    gr.approved_by = ctx.user_id
    _post(ctx, gr)
    return gr


def _post(ctx: Ctx, gr: GoodsReceipt) -> None:
    flags = _price_flags(ctx, gr)
    if flags:
        gr.exception_note = "; ".join(filter(None, [gr.exception_note, *flags]))
    for ln in gr.lines:
        if ln.qty_received <= 0:
            continue
        ing = ctx.db.get(Ingredient, ln.ingredient_id)
        stock_qty = inv.to_stock_qty(ctx, ing, ln.qty_received, ln.uom_id)
        cost_per_stock_unit = (ln.unit_cost * ln.qty_received / stock_qty).quantize(Decimal("0.000001"))
        inv.post_txn(ctx, location_id=gr.location_id, ingredient=ing, txn_type="RECEIPT", quantity=stock_qty, unit_cost=cost_per_stock_unit, source_type="GoodsReceipt",
                     source_id=gr.id, source_line_id=ln.id, reason=gr.gr_no)
        record_batch(ctx, gr.location_id, ing.id, ln.batch_no, ln.expiry_date, stock_qty, "GoodsReceipt", ln.id)
        if ln.po_item_id:
            ctx.db.get(PurchaseOrderItem, ln.po_item_id).qty_received += ln.qty_received
        si = ctx.db.scalar(select(SupplierItem).where(SupplierItem.supplier_id == gr.supplier_id, SupplierItem.ingredient_id == ing.id))
        if si is None:
            ctx.db.add(SupplierItem(supplier_id=gr.supplier_id, ingredient_id=ing.id, unit_price=ln.unit_cost, uom_id=ln.uom_id))
        else:
            si.unit_price, si.uom_id = ln.unit_cost, ln.uom_id
    gr.status, gr.posted_by, gr.posted_at = "Posted", ctx.user_id, utcnow()
    if gr.po_id:
        po = ctx.db.get(PurchaseOrder, gr.po_id)
        ctx.db.flush()
        ctx.db.refresh(po)
        po.status = "Received" if all(pi.qty_received >= pi.qty_ordered for pi in po.lines) else "PartiallyReceived"
    audit(ctx.db, ctx, "purchase.gr_post", "GoodsReceipt", gr.id, after={"value": gr.total_value, "approved_by": gr.approved_by, "flags": flags})


# ---------------------------------------------------------------- returns
def create_return(ctx: Ctx, gr: GoodsReceipt, lines: list[dict], reason: str) -> PurchaseReturn:
    if gr.status != "Posted":
        raise Conflict("GR_NOT_POSTED", "Only posted receipts can be returned.")
    ret = PurchaseReturn(branch_id=ctx.branch_id, return_no=f"RET-{next_number(ctx.db, ctx.branch_id, 'PURRET', 'R'):06d}", gr_id=gr.id, reason=reason, created_by=ctx.user_id)
    ctx.db.add(ret)
    ctx.db.flush()
    items = {i.id: i for i in gr.lines}
    value = ZERO
    for ln in lines:
        gi = items.get(ln["gr_item_id"])
        if gi is None:
            raise BusinessRuleError("RETURN_LINE_UNKNOWN", "A return line isn't on this receipt.")
        already = ctx.db.scalar(select(func.coalesce(func.sum(PurchaseReturnLine.quantity), 0)).where(PurchaseReturnLine.gr_item_id == gi.id)) or ZERO
        if already + ln["quantity"] > gi.qty_received:
            raise BusinessRuleError("RETURN_EXCEEDS_RECEIPT", "You can't return more than was received.")
        row = PurchaseReturnLine(return_id=ret.id, gr_item_id=gi.id, quantity=ln["quantity"])
        ctx.db.add(row)
        ctx.db.flush()
        ing = ctx.db.get(Ingredient, gi.ingredient_id)
        stock_qty = inv.to_stock_qty(ctx, ing, ln["quantity"], gi.uom_id)
        inv.post_txn(ctx, location_id=gr.location_id, ingredient=ing, txn_type="RETURN_TO_SUPPLIER", quantity=-stock_qty, unit_cost=(gi.unit_cost * ln["quantity"] / stock_qty),
                     source_type="PurchaseReturn", source_id=ret.id, source_line_id=row.id, reason=reason)
        value += ln["quantity"] * gi.unit_cost
    ret.total_value = q(value)
    ctx.db.flush()
    ctx.db.refresh(ret)
    audit(ctx.db, ctx, "purchase.return", "PurchaseReturn", ret.id, after={"gr": gr.gr_no, "value": ret.total_value}, reason=reason)
    return ret


# ---------------------------------------------------------------- invoices and payments (BR-043)
def create_invoice(ctx: Ctx, data: dict) -> SupplierInvoice:
    s = supplier(ctx, data["supplier_id"])
    if ctx.db.scalar(select(SupplierInvoice.id).where(SupplierInvoice.supplier_id == s.id, SupplierInvoice.invoice_no == data["invoice_no"])):
        raise Conflict("INVOICE_EXISTS", "This supplier already has an invoice with that number.")
    grs = [_get(ctx, GoodsReceipt, g) for g in data.get("gr_ids", [])]
    if any(g.supplier_id != s.id or g.status != "Posted" for g in grs):
        raise BusinessRuleError("INVOICE_GR_INVALID", "Invoices can only match posted receipts from the same supplier.")
    returns = ctx.db.scalar(select(func.coalesce(func.sum(PurchaseReturn.total_value), 0)).where(PurchaseReturn.gr_id.in_([g.id for g in grs] or [None]))) or ZERO
    matched = sum((g.total_value for g in grs), ZERO) - returns
    tol = Decimal(str(get_setting(ctx.db, "purchasing", ctx.branch_id)["invoice_tolerance"]))
    status = "ForReview" if not grs else ("Matched" if abs(data["amount"] - matched) <= tol else "Difference")
    inv_row = SupplierInvoice(branch_id=ctx.branch_id, supplier_id=s.id, invoice_no=data["invoice_no"], invoice_date=data["invoice_date"], due_date=data["due_date"],
                              amount=data["amount"], currency=s.currency, gr_ids=[str(g.id) for g in grs], matched_value=q(matched), match_status=status, created_by=ctx.user_id)
    ctx.db.add(inv_row)
    ctx.db.flush()
    audit(ctx.db, ctx, "purchase.invoice", "SupplierInvoice", inv_row.id, after={"invoice_no": inv_row.invoice_no, "amount": inv_row.amount, "match": status})
    return inv_row


def pay_invoice(ctx: Ctx, invoice: SupplierInvoice, amount: Decimal, method: str, reference: str | None) -> SupplierPayment:
    if amount > invoice.amount - invoice.paid_amount:
        raise BusinessRuleError("PAYMENT_EXCEEDS_BALANCE", f"The invoice balance is {invoice.amount - invoice.paid_amount}.")  # BR-043
    if invoice.match_status != "Matched" and not ctx.can("purchases.approve"):
        raise Forbidden("Unmatched invoices need a manager to release payment.", code="INVOICE_NOT_MATCHED")
    p = SupplierPayment(invoice_id=invoice.id, amount=amount, method=method, reference=reference, paid_by=ctx.user_id)
    ctx.db.add(p)
    invoice.paid_amount += amount
    invoice.status = "Paid" if invoice.paid_amount >= invoice.amount else "PartiallyPaid"
    ctx.db.flush()
    audit(ctx.db, ctx, "purchase.supplier_payment", "SupplierInvoice", invoice.id, after={"amount": amount, "method": method})
    return p


def supplier_balance(ctx: Ctx, s: Supplier) -> dict:
    """FR-PUR-011: balance and ageing by days past due."""
    today = ctx.business_date()
    buckets = {"current": ZERO, "1_30": ZERO, "31_60": ZERO, "61_90": ZERO, "over_90": ZERO}
    for i in ctx.db.scalars(select(SupplierInvoice).where(SupplierInvoice.supplier_id == s.id, SupplierInvoice.status != "Paid")):
        due = i.amount - i.paid_amount
        late = (today - i.due_date).days
        key = "current" if late <= 0 else "1_30" if late <= 30 else "31_60" if late <= 60 else "61_90" if late <= 90 else "over_90"
        buckets[key] += due
    return {"supplier_id": s.id, "balance": q(sum(buckets.values(), ZERO)), "ageing": {k: q(v) for k, v in buckets.items()}}


_ = q4
