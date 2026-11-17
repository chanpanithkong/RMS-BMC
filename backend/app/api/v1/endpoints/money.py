"""Bills, payments, refunds (BILL) and cashier sessions (STAFF)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.core.dependencies import Ctx, require
from app.core.exceptions import NotFound
from app.models import Bill, CashierSession, Payment, Receipt, Refund
from app.schemas.common import ORM, Page, Strict
from app.services import billing as svc
from app.services import cash as csvc
from app.services import orders as osvc
from app.services.platform import idempotent

bills = APIRouter(tags=["billing"])
cash = APIRouter(prefix="/cashier-sessions", tags=["cashier sessions"])
PView = Annotated[Ctx, Depends(require("payments.view"))]
PCreate = Annotated[Ctx, Depends(require("payments.create"))]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]


class BillLineOut(ORM):
    order_item_id: uuid.UUID
    quantity_share: Decimal
    amount_gross: Decimal
    amount_discount: Decimal
    amount_net: Decimal


class BillChargeOut(ORM):
    charge_type: str
    name: str
    rate: Decimal | None
    base_amount: Decimal
    amount: Decimal


class BillOut(ORM):
    id: uuid.UUID
    order_id: uuid.UUID
    bill_no: str
    business_date: date
    split_index: int
    split_count: int
    status: str
    gross_total: Decimal
    discount_total: Decimal
    subtotal: Decimal
    service_charge_total: Decimal
    tax_total: Decimal
    delivery_fee: Decimal
    rounding_total: Decimal
    total: Decimal
    paid_total: Decimal
    refunded_total: Decimal
    balance: Decimal
    currency: str
    printed_count: int
    finalised_at: datetime | None
    receipt_no: str | None = None
    lines: list[BillLineOut]
    charges: list[BillChargeOut]


class BillRequest(Strict):
    mode: Literal["single", "equal", "items", "seats"] = "single"
    parts: int = Field(1, ge=1, le=20)
    assignment: dict[uuid.UUID, int] | None = Field(None, description="items mode: order_item_id -> bill index (0-based)")

    @model_validator(mode="after")
    def _check(self):
        if self.mode == "equal" and self.parts < 2:
            raise ValueError("equal split needs at least 2 parts")
        return self


class PaymentIn(Strict):
    bill_id: uuid.UUID
    method: str = Field(description="Payment method code, e.g. CASH_USD, CASH_KHR, KHQR, BANK_TRANSFER, CARD")
    currency: Literal["USD", "KHR"]
    amount_tendered: Decimal | None = Field(None, gt=0, description="Required for cash; defaults to the balance for other methods")
    change_currency: Literal["USD", "KHR"] | None = None
    reference: str | None = Field(None, max_length=80)
    approval_code: str | None = Field(None, max_length=30)
    card_last4: str | None = Field(None, pattern=r"^\d{4}$", description="Masked last four digits only; never the card number (A-17)")


class PaymentOut(BaseModel):
    payment_id: uuid.UUID
    status: str
    method: str
    currency: str
    amount_tendered: Decimal
    amount_applied: Decimal
    rate: Decimal | None
    amount_base: Decimal
    rounding_base: Decimal
    rounding: dict | None
    change: dict | None
    bill: dict
    receipt_no: str | None
    created_at: datetime | None


class VoidIn(Strict):
    reason: str = Field(min_length=2, max_length=300)
    approval_id: uuid.UUID | None = None


class RefundIn(Strict):
    payment_id: uuid.UUID
    amount: Decimal = Field(gt=0, description="Base currency (USD) amount to refund")
    reason: str = Field(min_length=2, max_length=300)


class RefundDecision(Strict):
    note: str | None = Field(None, max_length=300)


class RefundOut(ORM):
    id: uuid.UUID
    refund_no: str
    payment_id: uuid.UUID
    bill_id: uuid.UUID
    amount_base: Decimal
    currency: str
    amount: Decimal
    method_code: str
    reason: str
    status: str
    requested_by: uuid.UUID
    approved_by: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None


def bill_out(db, b: Bill) -> dict:
    receipt = db.scalar(select(Receipt).where(Receipt.bill_id == b.id))
    return {**BillOut.model_validate(b).model_dump(), "receipt_no": receipt.receipt_no if receipt else None}


@bills.post("/orders/{order_id}/bills", response_model=list[BillOut], status_code=201, summary="Generate the bill, or split it (items, seats, equal shares)")
def make_bills(order_id: uuid.UUID, body: BillRequest, ctx: PCreate):
    order = osvc.get_order(ctx, order_id, lock=True)
    osvc.ensure_editable(order)
    return [bill_out(ctx.db, b) for b in svc.generate_bills(ctx, order, body.mode, body.parts, body.assignment)]


@bills.get("/orders/{order_id}/bills", response_model=list[BillOut])
def order_bills(order_id: uuid.UUID, ctx: PView):
    order = osvc.get_order(ctx, order_id)
    return [bill_out(ctx.db, b) for b in svc.active_bills(ctx.db, order.id)]


@bills.get("/bills/{bill_id}", response_model=BillOut)
def get_bill(bill_id: uuid.UUID, ctx: PView):
    return bill_out(ctx.db, svc.get_bill(ctx, bill_id))


@bills.post("/bills/{bill_id}/print", response_model=BillOut, summary="Print or show the bill; the table becomes Awaiting Payment")
def print_bill(bill_id: uuid.UUID, ctx: PCreate):
    return bill_out(ctx.db, svc.print_bill(ctx, svc.get_bill(ctx, bill_id, lock=True)))


@bills.post("/bills/{bill_id}/receipt/reprint", summary="Reprint marked COPY (BR-049)")
def reprint(bill_id: uuid.UUID, ctx: PCreate):
    r = svc.reprint_receipt(ctx, svc.get_bill(ctx, bill_id))
    return {"receipt_no": r.receipt_no, "copy": r.reprint_count, "label": f"COPY {r.reprint_count}"}


@bills.post("/payments", response_model=PaymentOut, status_code=201, summary="Record a payment (Idempotency-Key required). Change and rounding are computed by the server.")
def create_payment(body: PaymentIn, ctx: PCreate, idempotency_key: IdemKey = None):
    def run():
        return PaymentOut.model_validate(svc.create_payment(ctx, {**body.model_dump(), "idempotency_key": idempotency_key})).model_dump()

    if body.method.startswith("CASH") and body.amount_tendered is None:
        from app.core.exceptions import BusinessRuleError

        raise BusinessRuleError("VALIDATION_ERROR", "Enter the amount tendered.", details=[{"field": "amount_tendered", "issue": "required for cash"}])
    return idempotent(ctx.db, f"payment:{ctx.branch_id}", idempotency_key, body.model_dump(), run, 201)


@bills.get("/payments", response_model=Page[dict], summary="Payments by business day, method, session or status")
def list_payments(ctx: PView, business_date: date | None = None, method: str | None = None, status: str | None = None, cashier_session_id: uuid.UUID | None = None,
                  page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(Payment).where(Payment.branch_id == ctx.branch_id)
    for col, val in ((Payment.business_date, business_date), (Payment.method_code, method), (Payment.status, status), (Payment.cashier_session_id, cashier_session_id)):
        if val is not None:
            stmt = stmt.where(col == val)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": [PaymentOut.model_validate(svc.payment_out(ctx.db, p, ctx.db.get(Bill, p.bill_id))).model_dump(mode="json") for p in rows],
            "total": total, "page": page, "page_size": page_size}


@bills.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: uuid.UUID, ctx: PView):
    p = ctx.db.scalar(select(Payment).where(Payment.id == payment_id, Payment.branch_id == ctx.branch_id))
    if p is None:
        raise NotFound("Payment")
    return svc.payment_out(ctx.db, p, ctx.db.get(Bill, p.bill_id))


@bills.post("/payments/{payment_id}/void", summary="Void an unfinalised payment in the same session, with approval (FR-BILL-015)")
def void_payment(payment_id: uuid.UUID, body: VoidIn, ctx: PCreate):
    p = svc.void_payment(ctx, payment_id, body.reason, body.approval_id)
    return {"payment_id": p.id, "status": p.status}


@bills.post("/refunds", response_model=RefundOut, status_code=201, summary="Request a refund against a payment (BR-012). Idempotency-Key required.")
def request_refund(body: RefundIn, ctx: Annotated[Ctx, Depends(require("refunds.request"))], idempotency_key: IdemKey = None):
    def run():
        return RefundOut.model_validate(svc.request_refund(ctx, body.payment_id, body.amount, body.reason, idempotency_key)).model_dump()

    return idempotent(ctx.db, f"refund:{ctx.branch_id}", idempotency_key, body.model_dump(), run, 201)


@bills.post("/refunds/{refund_id}/approve", response_model=RefundOut)
def approve_refund(refund_id: uuid.UUID, body: RefundDecision, ctx: Annotated[Ctx, Depends(require("refunds.approve"))]):
    return svc.decide_refund(ctx, refund_id, True, body.note)


@bills.post("/refunds/{refund_id}/reject", response_model=RefundOut)
def reject_refund(refund_id: uuid.UUID, body: RefundDecision, ctx: Annotated[Ctx, Depends(require("refunds.approve"))]):
    return svc.decide_refund(ctx, refund_id, False, body.note)


@bills.get("/refunds", response_model=list[RefundOut])
def list_refunds(ctx: PView, status: str | None = None):
    stmt = select(Refund).where(Refund.branch_id == ctx.branch_id)
    if status:
        stmt = stmt.where(Refund.status == status)
    return ctx.db.scalars(stmt.order_by(Refund.created_at.desc()).limit(200)).all()


# ---------------------------------------------------------------- cashier sessions
class FloatsIn(Strict):
    floats: dict[Literal["USD", "KHR"], Decimal] = Field(description="Opening float per currency")
    witness_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _non_negative(self):
        if any(v < 0 for v in self.floats.values()):
            raise ValueError("floats can't be negative")
        return self


class MovementIn(Strict):
    kind: Literal["PaidOut", "PaidIn", "Drop"]
    currency: Literal["USD", "KHR"]
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=2, max_length=300)


class CountIn(Strict):
    counts: dict[Literal["USD", "KHR"], Decimal]
    denominations: dict[str, dict[str, int]] | None = None

    @model_validator(mode="after")
    def _non_negative(self):
        if any(v < 0 for v in self.counts.values()):
            raise ValueError("counts can't be negative")
        return self


class ReasonIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


class SessionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    business_date: date
    status: str
    opened_at: datetime
    closed_at: datetime | None
    approved_by: uuid.UUID | None
    variance_reason: str | None
    floats: dict[str, Decimal]
    results: list[dict] | None


def session_out(s: CashierSession) -> dict:
    return {**{c: getattr(s, c) for c in ("id", "user_id", "business_date", "status", "opened_at", "closed_at", "approved_by", "variance_reason")},
            "floats": {f.currency: f.amount for f in s.floats}, "results": csvc.result_rows(s) if s.status != "Open" else None}


@cash.post("", response_model=SessionOut, status_code=201, summary="Open your cashier session with an opening float")
def open_session(body: FloatsIn, ctx: Annotated[Ctx, Depends(require("cash.operate"))]):
    return session_out(csvc.open_session(ctx, body.floats, body.witness_id))


@cash.get("/current", response_model=SessionOut | None)
def current(ctx: Annotated[Ctx, Depends(require("notifications.view"))]):
    s = svc.open_session_for(ctx.db, ctx.branch_id, ctx.user_id)
    return session_out(s) if s else None


@cash.get("", response_model=list[SessionOut])
def list_sessions(ctx: Annotated[Ctx, Depends(require("cash.view"))], status: str | None = None, business_date: date | None = None):
    stmt = select(CashierSession).where(CashierSession.branch_id == ctx.branch_id)
    if status:
        stmt = stmt.where(CashierSession.status == status)
    if business_date:
        stmt = stmt.where(CashierSession.business_date == business_date)
    return [session_out(s) for s in ctx.db.scalars(stmt.order_by(CashierSession.opened_at.desc()).limit(200))]


@cash.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("notifications.view"))]):
    return session_out(csvc.get_session(ctx, session_id))


@cash.post("/{session_id}/cash-movements", status_code=201)
def movement(session_id: uuid.UUID, body: MovementIn, ctx: Annotated[Ctx, Depends(require("cash.operate"))]):
    m = csvc.add_movement(ctx, csvc.get_session(ctx, session_id, lock=True), body.kind, body.currency, body.amount, body.reason)
    return {"id": m.id, "kind": m.kind, "currency": m.currency, "amount": m.amount}


@cash.post("/{session_id}/close", response_model=SessionOut, summary="Submit the blind count; expected and variance are revealed after (FR-STAFF-009)")
def close(session_id: uuid.UUID, body: CountIn, ctx: Annotated[Ctx, Depends(require("cash.operate"))]):
    return session_out(csvc.close_session(ctx, csvc.get_session(ctx, session_id, lock=True), body.counts, body.denominations))


@cash.post("/{session_id}/approve-variance", response_model=SessionOut)
def approve_variance(session_id: uuid.UUID, body: ReasonIn, ctx: Annotated[Ctx, Depends(require("cash.approve"))]):
    return session_out(csvc.approve_variance(ctx, csvc.get_session(ctx, session_id, lock=True), body.reason))


@cash.post("/{session_id}/force-close", response_model=SessionOut)
def force_close(session_id: uuid.UUID, body: ReasonIn, ctx: Annotated[Ctx, Depends(require("cash.approve"))]):
    return session_out(csvc.force_close(ctx, csvc.get_session(ctx, session_id, lock=True), body.reason))


@cash.get("/{session_id}/report", summary="X report (open) or Z report (closed)")
def report(session_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("notifications.view"))]):
    return csvc.session_report(ctx, csvc.get_session(ctx, session_id))
