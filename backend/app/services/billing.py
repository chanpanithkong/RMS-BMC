"""Bills, payments, refunds and receipts (SRS §6.9, §12.9; BR-008, BR-011, BR-012, BR-022, BR-024, BR-032–BR-035, BR-039, BR-049)."""
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import Ctx
from app.core.exceptions import AppError, BusinessRuleError, Conflict, Forbidden, NotFound
from app.core.realtime import emit
from app.models import (AppliedDiscount, Bill, BillCharge, BillLine, CashierSession, ExchangeRate, Order, OrderDiscount, Payment, PaymentAllocation, PaymentMethod, Receipt,
                        Refund, RestaurantTable)
from app.services import orders as osvc
from app.services.platform import audit, consume_approval, get_setting, next_number
from app.utils.money import ZERO, q, q4, round_to_increment
from app.utils.timeutil import utcnow

BASE = "USD"


# ---------------------------------------------------------------- bills
def get_bill(ctx: Ctx, bill_id: uuid.UUID, lock: bool = False) -> Bill:
    stmt = select(Bill).where(Bill.id == bill_id, Bill.branch_id == ctx.branch_id)
    bill = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if bill is None:
        raise NotFound("Bill")
    return bill


def active_bills(db: Session, order_id: uuid.UUID) -> list[Bill]:
    return list(db.scalars(select(Bill).where(Bill.order_id == order_id, Bill.status != "Void").order_by(Bill.split_index)))


def _weights_for(order: Order, mode: str, parts: int, assignment: dict[uuid.UUID, int] | None) -> list[dict]:
    """Fraction of each live item on each bill. Totals across bills always equal the order (BR-032)."""
    items = osvc.live_items(order)
    if mode == "single":
        return [{i.id: Decimal(1) for i in items}]
    if mode == "equal":
        return [{i.id: Decimal(1) / parts for i in items} for _ in range(parts)]
    if mode == "items":
        if not assignment or set(assignment) != {i.id for i in items}:
            raise BusinessRuleError("SPLIT_ASSIGNMENT_INCOMPLETE", "Assign every item to a bill.")
        parts = max(assignment.values()) + 1
        weights = [dict() for _ in range(parts)]
        for item_id, idx in assignment.items():
            weights[idx][item_id] = Decimal(1)
        return weights
    if mode == "seats":
        seats = sorted({i.seat_no or 1 for i in items})
        return [{i.id: Decimal(1) for i in items if (i.seat_no or 1) == s} for s in seats]
    raise BusinessRuleError("SPLIT_MODE_INVALID", "Unknown split mode.")


def generate_bills(ctx: Ctx, order: Order, mode: str = "single", parts: int = 1, assignment: dict | None = None) -> list[Bill]:
    """Create bills for the order. Unpaid open bills are replaced; once paying has started, splits are frozen."""
    db = ctx.db
    osvc.recalc(ctx, order)
    items = osvc.live_items(order)
    if not items:
        raise BusinessRuleError("ORDER_EMPTY", "There's nothing to bill on this order.")
    existing = active_bills(db, order.id)
    if any(b.paid_total > 0 for b in existing):
        billed = sum((b.total for b in existing), ZERO)
        if order.grand_total > billed:
            raise Conflict("BILL_TOPUP_NOT_SUPPORTED", "Items were added after payment began. Pay the remaining balance on a new order or refund first.")
        return existing
    for b in existing:
        b.status = "Void"
    weights = [w for w in _weights_for(order, mode, parts, assignment) if w]
    calc = osvc.calculation(db, order)
    line_by_id = {uuid.UUID(r.key): r for r in calc.lines}
    charges = calc.charges
    order_net = sum((r.net for r in calc.lines), ZERO)
    bills: list[Bill] = []
    remaining_charges = {i: c.amount for i, c in enumerate(charges)}
    remaining_total = calc.total
    for idx, w in enumerate(weights):
        last = idx == len(weights) - 1
        bill = Bill(branch_id=order.branch_id, business_date=ctx.business_date(), order_id=order.id, split_index=idx + 1, split_count=len(weights),
                    bill_no=f"B-{ctx.branch.code}-{next_number(db, ctx.branch_id, 'BILL', str(ctx.business_date().year)):06d}")
        db.add(bill)
        db.flush()
        gross = disc = net = ZERO
        for item_id, share in w.items():
            r = line_by_id[item_id]
            lg, ld, ln = q4(r.gross * share), q4((r.item_discount + r.order_discount) * share), q4(r.net * share)
            db.add(BillLine(bill_id=bill.id, order_item_id=item_id, quantity_share=share, amount_gross=lg, amount_discount=ld, amount_net=ln))
            gross, disc, net = gross + lg, disc + ld, net + ln
        fraction = (net / order_net) if order_net else Decimal(1) / len(weights)
        svc = tax = fee = ZERO
        for ci, c in enumerate(charges):
            amount = remaining_charges[ci] if last else q(c.amount * fraction)
            remaining_charges[ci] -= amount
            db.add(BillCharge(bill_id=bill.id, charge_type=c.charge_type, name=c.name, tax_profile_rate_id=c.rule_id, rate=c.rate, base_amount=q(c.base_amount * fraction), amount=amount))
            if c.charge_type == "ServiceCharge":
                svc += amount
            elif c.charge_type == "Tax" and not c.inclusive:
                tax += amount
            elif c.charge_type == "DeliveryFee":
                fee += amount
        total = remaining_total if last else q(net + svc + tax + fee)
        remaining_total -= total
        bill.gross_total, bill.discount_total, bill.subtotal = q(gross), q(disc), q(net)
        bill.service_charge_total, bill.tax_total, bill.delivery_fee = svc, tax, fee
        bill.total, bill.balance = total, total
        bills.append(bill)
    for d in db.scalars(select(OrderDiscount).where(OrderDiscount.order_id == order.id, OrderDiscount.removed_at.is_(None))):
        line_amount = sum((line_by_id[i.id].item_discount for i in items if i.id == d.order_item_id), ZERO) if d.order_item_id else calc.order_discount_total
        db.add(AppliedDiscount(bill_id=bills[0].id, order_discount_id=d.id, order_item_id=d.order_item_id, amount=line_amount))
    db.flush()
    assert sum((b.total for b in bills), ZERO) == calc.total  # BR-032 invariant
    osvc.log_event(ctx, order, "billed", {"mode": mode, "bills": [b.bill_no for b in bills]})
    audit(db, ctx, "bill.generate", "Order", order.id, after={"mode": mode, "bills": [{"bill_no": b.bill_no, "total": b.total} for b in bills]})
    return bills


def print_bill(ctx: Ctx, bill: Bill) -> Bill:
    bill.printed_count += 1
    order = ctx.db.get(Order, bill.order_id)
    if order.table_id:
        table = ctx.db.get(RestaurantTable, order.table_id, with_for_update=True)
        if "AwaitingPayment" in osvc.TABLE_TRANSITIONS.get(table.service_state, set()):
            osvc.set_table_state(ctx, table, "AwaitingPayment")
    osvc.log_event(ctx, order, "bill_printed", {"bill_no": bill.bill_no, "count": bill.printed_count})
    return bill


# ---------------------------------------------------------------- exchange rate and cash (BR-024, BR-033, BR-034)
def current_rate(db: Session, currency: str) -> ExchangeRate | None:
    return db.scalar(select(ExchangeRate).where(ExchangeRate.base_currency == BASE, ExchangeRate.quote_currency == currency, ExchangeRate.effective_from <= utcnow())
                     .order_by(ExchangeRate.effective_from.desc()).limit(1))


@dataclass
class CashResult:
    applied: Decimal  # in tender currency
    amount_base: Decimal
    allocation: Decimal  # USD applied to the bill
    rounding_base: Decimal
    rounding_currency: Decimal  # e.g. 41 KHR
    change: Decimal
    covered: bool


def cash_math(balance: Decimal, currency: str, tendered: Decimal, change_currency: str, rate: Decimal | None, increment: Decimal) -> CashResult:
    if currency == BASE:
        due = balance
        if tendered >= due:
            over = tendered - due
            change = over if change_currency == BASE else round_to_increment(over * rate, increment)
            return CashResult(due, due, due, ZERO, ZERO, change, True)
        return CashResult(tendered, tendered, tendered, ZERO, ZERO, ZERO, False)
    exact = balance * rate
    due = round_to_increment(exact, increment)
    if tendered >= due:
        over = tendered - due
        change = round_to_increment(over, increment) if change_currency == currency else q(over / rate)
        amount_base = q(due / rate)
        return CashResult(due, amount_base, balance, amount_base - balance, due - q(exact, currency), change, True)
    amount_base = q(tendered / rate)
    alloc = min(amount_base, balance)
    return CashResult(tendered, amount_base, alloc, amount_base - alloc, ZERO, ZERO, False)


def open_session_for(db: Session, branch_id: uuid.UUID, user_id: uuid.UUID) -> CashierSession | None:
    return db.scalar(select(CashierSession).where(CashierSession.branch_id == branch_id, CashierSession.user_id == user_id, CashierSession.status == "Open"))


# ---------------------------------------------------------------- payments
def create_payment(ctx: Ctx, data: dict) -> dict:
    db = ctx.db
    osvc.ensure_day_open(ctx)
    bill = get_bill(ctx, data["bill_id"], lock=True)
    if bill.status not in ("Open", "PartiallyPaid"):
        raise Conflict("BILL_NOT_PAYABLE", f"This bill is {bill.status}.")
    method = db.scalar(select(PaymentMethod).where(PaymentMethod.code == data["method"], PaymentMethod.is_active))
    if method is None:
        raise BusinessRuleError("PAYMENT_METHOD_INVALID", "This payment method isn't enabled.")
    currency = data["currency"]
    if currency not in method.currencies:
        raise BusinessRuleError("CURRENCY_NOT_ALLOWED", f"{method.name} doesn't accept {currency}.")
    rate_row = None
    foreign = currency if currency != BASE else (data.get("change_currency") if data.get("change_currency") not in (None, BASE) else None)
    if foreign:
        rate_row = current_rate(db, foreign)
        if rate_row is None:
            raise Conflict("EXCHANGE_RATE_MISSING", f"No exchange rate for {foreign}. A manager must enter today's rate.")  # BR-024
    rate = rate_row.rate if rate_row else None
    increment = Decimal(str(get_setting(db, "billing", ctx.branch_id).get("khr_rounding_increment", "100")))
    balance = bill.balance
    session = None
    if method.kind == "Cash":
        session = open_session_for(db, ctx.branch_id, ctx.user_id)
        if session is None:
            raise Conflict("CASHIER_SESSION_REQUIRED", "Open a cashier session before taking cash.")  # BR-039
        tendered = data["amount_tendered"]
        change_currency = data.get("change_currency") or currency
        r = cash_math(balance, currency, tendered, change_currency, rate, increment)
        applied, amount_base, allocation, rounding_base, rounding_cur, change = r.applied, r.amount_base, r.allocation, r.rounding_base, r.rounding_currency, r.change
    else:
        if data.get("change_currency"):
            raise BusinessRuleError("CHANGE_NOT_ALLOWED", "Change can't be given on non-cash payments.")  # BR-034
        if method.reference_required and not data.get("reference"):
            raise BusinessRuleError("REFERENCE_REQUIRED", f"{method.name} needs a transaction reference.", details=[{"field": "reference", "issue": "required"}])
        tendered = data.get("amount_tendered") or (balance if currency == BASE else round_to_increment(balance * rate, increment))
        amount_base = tendered if currency == BASE else q(tendered / rate)
        if amount_base > balance:
            raise BusinessRuleError("OVERPAYMENT", "Non-cash payments can't exceed the balance.")  # BR-035
        applied, allocation, rounding_base, rounding_cur, change, change_currency = tendered, amount_base, ZERO, ZERO, ZERO, None
    if allocation <= 0:
        raise BusinessRuleError("AMOUNT_INVALID", "The payment amount must be above zero.")
    if allocation < balance and not get_setting(db, "billing", ctx.branch_id).get("partial_payments", True):
        raise BusinessRuleError("PARTIAL_NOT_ALLOWED", "Partial payments are turned off for this branch.")
    payment = Payment(branch_id=ctx.branch_id, business_date=ctx.business_date(), bill_id=bill.id, method_id=method.id, method_code=method.code, currency=currency,
                      amount_tendered=tendered, amount_applied=applied, change_amount=change, change_currency=change_currency if change else None,
                      exchange_rate_id=rate_row.id if rate_row else None, rate=rate, amount_base=amount_base, rounding_base=rounding_base, status="Confirmed",
                      external_ref=data.get("reference"), approval_code=data.get("approval_code"), card_last4=data.get("card_last4"),
                      cashier_session_id=session.id if session else None, idempotency_key=data["idempotency_key"], received_by=ctx.user_id)
    db.add(payment)
    db.flush()
    db.add(PaymentAllocation(payment_id=payment.id, bill_id=bill.id, amount_base=allocation))
    bill.paid_total += allocation
    bill.balance = bill.total - bill.paid_total
    receipt = None
    if bill.balance == 0:
        bill.status, bill.finalised_at = "Paid", utcnow()
        receipt = Receipt(branch_id=ctx.branch_id, series="R", bill_id=bill.id, issued_by=ctx.user_id,
                          receipt_no=f"R-{ctx.branch.code}-{next_number(db, ctx.branch_id, 'RECEIPT', 'R'):06d}")
        db.add(receipt)
    else:
        bill.status = "PartiallyPaid"
    db.flush()
    order = db.scalar(select(Order).where(Order.id == bill.order_id).with_for_update())
    osvc.refresh_statuses(ctx, order)
    osvc.log_event(ctx, order, "payment", {"payment_id": payment.id, "method": method.code, "currency": currency, "amount_base": allocation})
    osvc.maybe_complete(ctx, order)
    audit(db, ctx, "payment.create", "Payment", payment.id, after={"bill": bill.bill_no, "method": method.code, "currency": currency, "tendered": tendered, "applied": applied,
                                                                  "amount_base": amount_base, "change": change, "rate": rate})
    emit(db, f"branch:{ctx.branch_id}", "payment.confirmed", {"order_id": str(order.id), "bill_id": str(bill.id), "balance": str(bill.balance)})
    return payment_out(db, payment, bill, receipt, rounding_cur)


def payment_out(db: Session, p: Payment, bill: Bill, receipt: Receipt | None = None, rounding_currency: Decimal | None = None) -> dict:
    receipt = receipt or db.scalar(select(Receipt).where(Receipt.bill_id == bill.id))
    return {"payment_id": p.id, "status": p.status, "method": p.method_code, "currency": p.currency, "amount_tendered": p.amount_tendered, "amount_applied": p.amount_applied,
            "rate": p.rate, "amount_base": p.amount_base, "rounding_base": p.rounding_base,
            "rounding": {"currency": p.currency, "amount": rounding_currency} if rounding_currency else None,
            "change": {"currency": p.change_currency, "amount": p.change_amount} if p.change_amount else None,
            "bill": {"id": bill.id, "bill_no": bill.bill_no, "total": bill.total, "paid": bill.paid_total, "balance": bill.balance, "status": bill.status},
            "receipt_no": receipt.receipt_no if receipt else None, "created_at": p.created_at}


def void_payment(ctx: Ctx, payment_id: uuid.UUID, reason: str, approval_id: uuid.UUID | None) -> Payment:
    """FR-BILL-015: same session, bill not finalised, supervisor approval, reversal recorded."""
    db = ctx.db
    p = db.scalar(select(Payment).where(Payment.id == payment_id, Payment.branch_id == ctx.branch_id).with_for_update())
    if p is None:
        raise NotFound("Payment")
    bill = get_bill(ctx, p.bill_id, lock=True)
    if p.status != "Confirmed":
        raise Conflict("PAYMENT_NOT_VOIDABLE", f"This payment is {p.status}.")
    if bill.status == "Paid":
        raise Conflict("BILL_FINALISED", "The bill is finalised. Use a refund instead.")
    session = open_session_for(db, ctx.branch_id, ctx.user_id)
    if p.cashier_session_id and (session is None or session.id != p.cashier_session_id):
        raise Conflict("SESSION_MISMATCH", "Cash payments can only be voided in the session that took them.")
    approver = consume_approval(ctx, approval_id, "payment_void", p.amount_base, p.id)
    alloc = db.scalar(select(func.sum(PaymentAllocation.amount_base)).where(PaymentAllocation.payment_id == p.id)) or ZERO
    bill.paid_total -= alloc
    bill.balance = bill.total - bill.paid_total
    bill.status = "PartiallyPaid" if bill.paid_total > 0 else "Open"
    p.status, p.voided_at, p.void_reason, p.voided_by = "Voided", utcnow(), reason, approver
    db.flush()
    order = db.get(Order, bill.order_id)
    osvc.refresh_statuses(ctx, order)
    audit(db, ctx, "payment.void", "Payment", p.id, before={"status": "Confirmed"}, after={"status": "Voided", "approved_by": approver}, reason=reason)
    from app.services import credit

    credit.on_void(ctx, p)
    return p


# ---------------------------------------------------------------- refunds (BR-012)
def request_refund(ctx: Ctx, payment_id: uuid.UUID, amount_base: Decimal, reason: str, idem_key: str | None) -> Refund:
    db = ctx.db
    p = db.scalar(select(Payment).where(Payment.id == payment_id, Payment.branch_id == ctx.branch_id).with_for_update())
    if p is None:
        raise NotFound("Payment")
    if p.status != "Confirmed":
        raise Conflict("PAYMENT_NOT_REFUNDABLE", f"This payment is {p.status}.")
    allocated = db.scalar(select(func.sum(PaymentAllocation.amount_base)).where(PaymentAllocation.payment_id == p.id)) or ZERO
    pending = db.scalar(select(func.coalesce(func.sum(Refund.amount_base), 0)).where(Refund.payment_id == p.id, Refund.status == "Requested")) or ZERO
    unrefunded = allocated - p.refunded_base - pending
    if amount_base > unrefunded:
        raise BusinessRuleError("REFUND_EXCEEDS_PAYMENT", f"The refund exceeds the unrefunded amount of {q(unrefunded)}.", details=[{"field": "amount", "issue": f"max {q(unrefunded)}"}])
    currency = p.currency if p.currency == BASE or not p.rate else p.currency
    amount = amount_base if currency == BASE else round_to_increment(amount_base * p.rate, Decimal("100"))
    r = Refund(branch_id=ctx.branch_id, business_date=ctx.business_date(), refund_no=f"RF-{ctx.branch.code}-{next_number(db, ctx.branch_id, 'REFUND', 'RF'):06d}",
               payment_id=p.id, bill_id=p.bill_id, amount_base=amount_base, currency=currency, amount=amount, method_code=p.method_code, reason=reason,
               requested_by=ctx.user_id, idempotency_key=idem_key)
    db.add(r)
    db.flush()
    audit(db, ctx, "refund.request", "Refund", r.id, after={"payment_id": p.id, "amount_base": amount_base, "reason": reason}, reason=reason)
    from app.services.platform import notify_permission

    notify_permission(db, ctx.branch_id, "refunds.approve", "Approval", "Refund awaiting approval", f"{r.refund_no}: {q(amount_base)} USD — {reason}", "/billing?tab=refunds")
    return r


def decide_refund(ctx: Ctx, refund_id: uuid.UUID, approve: bool, note: str | None) -> Refund:
    db = ctx.db
    ctx.require("refunds.approve")
    r = db.scalar(select(Refund).where(Refund.id == refund_id, Refund.branch_id == ctx.branch_id).with_for_update())
    if r is None:
        raise NotFound("Refund")
    if r.status != "Requested":
        raise Conflict("REFUND_DECIDED", f"This refund is already {r.status}.")
    if r.requested_by == ctx.user_id:
        raise Forbidden("You can't approve your own refund request.", code="SELF_APPROVAL")  # BR-029
    if not approve:
        r.status = "Rejected"
        audit(db, ctx, "refund.reject", "Refund", r.id, reason=note)
        return r
    if r.amount_base > ctx.limit("refund_amount"):
        raise Forbidden(f"This refund exceeds your limit of {ctx.limit('refund_amount')}.", code="APPROVER_LIMIT_EXCEEDED")
    p = db.scalar(select(Payment).where(Payment.id == r.payment_id).with_for_update())
    bill = get_bill(ctx, r.bill_id, lock=True)
    allocated = db.scalar(select(func.sum(PaymentAllocation.amount_base)).where(PaymentAllocation.payment_id == p.id)) or ZERO
    if p.refunded_base + r.amount_base > allocated:
        raise BusinessRuleError("REFUND_EXCEEDS_PAYMENT", "The refund now exceeds the unrefunded amount.")
    method = db.scalar(select(PaymentMethod).where(PaymentMethod.code == r.method_code))
    if method.kind == "Cash":
        session = open_session_for(db, ctx.branch_id, r.requested_by) or open_session_for(db, ctx.branch_id, ctx.user_id)
        if session is None:
            raise Conflict("CASHIER_SESSION_REQUIRED", "A cash refund needs an open cashier session to pay it out.")
        r.cashier_session_id = session.id
    p.refunded_base += r.amount_base
    bill.refunded_total += r.amount_base
    if bill.refunded_total >= bill.paid_total:
        bill.status = "Refunded"
    r.status, r.approved_by, r.completed_at = "Completed", ctx.user_id, utcnow()
    db.flush()
    order = db.get(Order, bill.order_id)
    osvc.refresh_statuses(ctx, order)
    osvc.log_event(ctx, order, "refund", {"refund_no": r.refund_no, "amount_base": r.amount_base})
    from app.services import loyalty

    loyalty.clawback(ctx, order, r)  # points earned on refunded money are taken back
    from app.services import credit

    credit.on_refund(ctx, r)  # a refund of an on-account payment credits the account
    audit(db, ctx, "refund.approve", "Refund", r.id, after={"amount_base": r.amount_base, "approved_by": ctx.user_id, "requested_by": r.requested_by}, reason=note)
    return r


def reprint_receipt(ctx: Ctx, bill: Bill) -> Receipt:
    receipt = ctx.db.scalar(select(Receipt).where(Receipt.bill_id == bill.id).with_for_update())
    if receipt is None:
        raise NotFound("Receipt")
    receipt.reprint_count += 1
    audit(ctx.db, ctx, "receipt.reprint", "Receipt", receipt.id, after={"receipt_no": receipt.receipt_no, "copy": receipt.reprint_count})  # BR-049
    return receipt


_ = AppError
