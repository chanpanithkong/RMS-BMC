"""Customer credit accounts (FR-CUST-011, FR-BILL-017, BR-036; owner's decisions for D-07).

* Owner, GM or Accountant open accounts and set the limit and terms (30 days by default).
* A bill is charged to an account as a payment with the ON_ACCOUNT method, so the bill is settled, the order can
  complete and sales are recognised as usual (SRS §6.1: "fully paid or transferred to an approved credit account").
  The ledger records a Charge due after the account's terms.
* A charge that would exceed the limit, or any charge while the account has an overdue amount, needs a manager's
  approval on the device (approval action credit_override), bound to the bill and amount.
* Settlements reduce the oldest open charges first. Cash settlements go into the cashier's open session as a paid-in.
* Refunds and voids of ON_ACCOUNT payments reduce what the customer owes.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, NotFound
from app.models import Bill, CashMovement, CreditAccount, CreditTransaction, Customer, Order, Payment, Refund
from app.services.platform import audit, consume_approval, get_setting, next_number
from app.utils.money import ZERO, q
from app.utils.timeutil import utcnow

SETTLE_METHODS = ("CASH_USD", "BANK_TRANSFER", "KHQR", "CARD")


def enabled(ctx: Ctx) -> None:
    if not get_setting(ctx.db, "credit", ctx.branch_id).get("enabled"):
        raise BusinessRuleError("CREDIT_DISABLED", "Credit sales aren't enabled at this branch.")


def get_account(ctx: Ctx, account_id: uuid.UUID, lock: bool = False) -> CreditAccount:
    stmt = select(CreditAccount).where(CreditAccount.id == account_id)
    a = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if a is None:
        raise NotFound("Credit account")
    return a


def overdue_amount(ctx: Ctx, a: CreditAccount, on: date | None = None) -> Decimal:
    on = on or ctx.business_date()
    return ctx.db.scalar(select(func.coalesce(func.sum(CreditTransaction.open_amount), 0)).where(
        CreditTransaction.account_id == a.id, CreditTransaction.kind == "Charge", CreditTransaction.open_amount > 0, CreditTransaction.due_date < on)) or ZERO


def account_out(ctx: Ctx, a: CreditAccount) -> dict:
    c = ctx.db.get(Customer, a.customer_id)
    over = overdue_amount(ctx, a)
    return {"id": a.id, "account_no": a.account_no, "customer_id": a.customer_id, "customer_name": c.name if c else None, "company_name": a.company_name,
            "billing_contact": a.billing_contact, "credit_limit": a.credit_limit, "terms_days": a.terms_days, "balance": a.balance,
            "available": max(a.credit_limit - a.balance, ZERO), "overdue": over, "status": a.status, "approved_by": a.approved_by, "notes": a.notes}


def open_account(ctx: Ctx, data: dict) -> CreditAccount:
    ctx.require("credit.manage")
    c = ctx.db.get(Customer, data["customer_id"])
    if c is None or c.merged_into_id or c.anonymised_at:
        raise NotFound("Customer")
    if ctx.db.scalar(select(CreditAccount.id).where(CreditAccount.customer_id == c.id)):
        raise Conflict("CREDIT_ACCOUNT_EXISTS", "This customer already has a credit account.")
    terms = data.get("terms_days")
    a = CreditAccount(account_no=f"CA-{next_number(ctx.db, ctx.branch_id, 'CREDIT', 'CA'):06d}", customer_id=c.id, company_name=data.get("company_name"),
                      billing_contact=data.get("billing_contact"), credit_limit=data["credit_limit"],
                      terms_days=terms if terms is not None else int(get_setting(ctx.db, "credit", ctx.branch_id).get("default_terms_days", 30)),
                      approved_by=ctx.user_id, notes=data.get("notes"))
    ctx.db.add(a)
    ctx.db.flush()
    audit(ctx.db, ctx, "credit.account_open", "CreditAccount", a.id, after={"customer": c.code, "limit": a.credit_limit, "terms": a.terms_days})
    return a


def update_account(ctx: Ctx, a: CreditAccount, data: dict) -> CreditAccount:
    ctx.require("credit.manage")
    if data.get("status") == "Closed" and a.balance != 0:
        raise Conflict("CREDIT_BALANCE_OUTSTANDING", "Settle the balance before closing the account.")
    before = {k: getattr(a, k) for k in data}
    for k, v in data.items():
        setattr(a, k, v)
    audit(ctx.db, ctx, "credit.account_update", "CreditAccount", a.id, before=before, after=data)
    return a


def _txn(ctx: Ctx, a: CreditAccount, kind: str, amount: Decimal, **kw) -> CreditTransaction:
    t = CreditTransaction(account_id=a.id, branch_id=ctx.branch_id, business_date=ctx.business_date(),
                          txn_no=f"CT-{ctx.branch.code}-{next_number(ctx.db, ctx.branch_id, 'CREDITTXN', 'CT'):06d}", kind=kind, amount=amount,
                          created_by=ctx.user_id, **kw)
    ctx.db.add(t)
    a.balance = q(a.balance + amount)
    return t


def _reduce_open(ctx: Ctx, a: CreditAccount, amount: Decimal, first_charge_id=None) -> None:
    """Apply a settlement or credit to open charges, oldest due first (a refund starts with its own charge)."""
    charges = ctx.db.scalars(select(CreditTransaction).where(CreditTransaction.account_id == a.id, CreditTransaction.kind == "Charge",
                                                             CreditTransaction.open_amount > 0)
                             .order_by(CreditTransaction.due_date, CreditTransaction.created_at).with_for_update()).all()
    if first_charge_id:
        charges.sort(key=lambda t: t.id != first_charge_id)
    left = amount
    for ch in charges:
        if left <= 0:
            break
        use = min(ch.open_amount, left)
        ch.open_amount -= use
        left -= use


# ---------------------------------------------------------------- charge a bill (FR-BILL-017)
def charge_bill(ctx: Ctx, bill: Bill, account_id: uuid.UUID, approval_id: uuid.UUID | None) -> dict:
    from app.services import billing

    ctx.require("credit.charge")
    enabled(ctx)
    db = ctx.db
    a = get_account(ctx, account_id, lock=True)
    if a.status != "Active":
        raise Conflict("CREDIT_ACCOUNT_INACTIVE", f"This account is {a.status.lower()}.")
    if bill.status not in ("Open", "PartiallyPaid") or bill.balance <= 0:
        raise Conflict("BILL_NOT_PAYABLE", f"This bill is {bill.status}.")
    order = db.get(Order, bill.order_id, with_for_update=True)
    if order.customer_id and order.customer_id != a.customer_id:
        raise Conflict("CREDIT_ACCOUNT_MISMATCH", "The order belongs to a different customer than this account.")
    amount = bill.balance
    over_limit = a.balance + amount > a.credit_limit
    overdue = overdue_amount(ctx, a)
    approver = None
    if over_limit or overdue > 0:
        # BR-036 over limit, and the owner's rule that overdue accounts take no new charges without a manager
        approver = consume_approval(ctx, approval_id, "credit_override", amount, bill.id)
    if order.customer_id is None:
        order.customer_id = a.customer_id
    out = billing.create_payment(ctx, {"bill_id": bill.id, "method": "ON_ACCOUNT", "currency": "USD", "reference": f"{a.account_no}/{bill.bill_no}"[:80],  # unique per method
                                       "idempotency_key": f"credit:{bill.id}:{bill.paid_total}"})
    t = _txn(ctx, a, "Charge", amount, open_amount=amount, due_date=ctx.business_date() + timedelta(days=a.terms_days), bill_id=bill.id,
             payment_id=out["payment_id"], approved_by=approver, reason=("over limit" if over_limit else "") + (" overdue account" if overdue > 0 else "") or None)
    db.flush()
    audit(db, ctx, "credit.charge", "CreditAccount", a.id, after={"bill": bill.bill_no, "amount": amount, "balance": a.balance, "approved_by": approver,
                                                                    "over_limit": over_limit, "overdue": overdue})
    return {"account": account_out(ctx, a), "transaction_no": t.txn_no, "due_date": t.due_date, "payment": out}


# ---------------------------------------------------------------- settlements, refunds, voids
def settle(ctx: Ctx, a: CreditAccount, amount: Decimal, method: str, reference: str | None) -> CreditTransaction:
    from app.services.billing import open_session_for

    ctx.require("credit.settle")
    if method not in SETTLE_METHODS:
        raise BusinessRuleError("PAYMENT_METHOD_INVALID", f"Settle with one of {', '.join(SETTLE_METHODS)}.")
    if amount <= 0 or amount > a.balance:
        raise BusinessRuleError("SETTLEMENT_EXCEEDS_BALANCE", f"The account owes {a.balance}.")
    if method != "CASH_USD" and not reference:
        raise BusinessRuleError("REFERENCE_REQUIRED", "Enter the transfer or transaction reference.")
    _reduce_open(ctx, a, amount)
    t = _txn(ctx, a, "Settlement", -amount, method_code=method, reference=reference)
    ctx.db.flush()
    if method == "CASH_USD":  # cash taken at the counter goes into the drawer (BR-039)
        session = open_session_for(ctx.db, ctx.branch_id, ctx.user_id)
        if session is None:
            raise Conflict("CASHIER_SESSION_REQUIRED", "Open a cashier session before taking cash.")
        ctx.db.add(CashMovement(branch_id=ctx.branch_id, session_id=session.id, kind="PaidIn", currency="USD", amount=amount,
                                reason=f"Account settlement {a.account_no} {t.txn_no}", created_by=ctx.user_id))
    audit(ctx.db, ctx, "credit.settle", "CreditAccount", a.id, after={"amount": amount, "method": method, "reference": reference, "balance": a.balance})
    return t


def _charge_for_payment(ctx: Ctx, payment_id) -> CreditTransaction | None:
    return ctx.db.scalar(select(CreditTransaction).where(CreditTransaction.payment_id == payment_id, CreditTransaction.kind == "Charge"))


def on_refund(ctx: Ctx, refund: Refund) -> None:
    """A refund of an ON_ACCOUNT payment is a credit to the account, not money out."""
    if refund.method_code != "ON_ACCOUNT":
        return
    ch = _charge_for_payment(ctx, refund.payment_id)
    if ch is None:
        return
    a = get_account(ctx, ch.account_id, lock=True)
    _reduce_open(ctx, a, refund.amount_base, first_charge_id=ch.id)
    _txn(ctx, a, "Credit", -refund.amount_base, refund_id=refund.id, reason=f"Refund {refund.refund_no}")
    audit(ctx.db, ctx, "credit.refund_credit", "CreditAccount", a.id, after={"refund": refund.refund_no, "amount": refund.amount_base, "balance": a.balance})


def on_void(ctx: Ctx, payment: Payment) -> None:
    if payment.method_code != "ON_ACCOUNT":
        return
    ch = _charge_for_payment(ctx, payment.id)
    if ch is None:
        return
    a = get_account(ctx, ch.account_id, lock=True)
    _reduce_open(ctx, a, payment.amount_base, first_charge_id=ch.id)
    _txn(ctx, a, "Reversal", -payment.amount_base, payment_id=payment.id, reason="Payment voided")
    audit(ctx.db, ctx, "credit.charge_void", "CreditAccount", a.id, after={"payment": str(payment.id), "amount": payment.amount_base, "balance": a.balance})


# ---------------------------------------------------------------- statements and ageing
def ageing(ctx: Ctx, a: CreditAccount, on: date | None = None) -> dict:
    on = on or ctx.business_date()
    buckets = {"current": ZERO, "1_30": ZERO, "31_60": ZERO, "61_90": ZERO, "over_90": ZERO}
    for ch in ctx.db.scalars(select(CreditTransaction).where(CreditTransaction.account_id == a.id, CreditTransaction.kind == "Charge", CreditTransaction.open_amount > 0)):
        days = (on - ch.due_date).days
        key = "current" if days <= 0 else "1_30" if days <= 30 else "31_60" if days <= 60 else "61_90" if days <= 90 else "over_90"
        buckets[key] += ch.open_amount
    return buckets


def statement(ctx: Ctx, a: CreditAccount, start: date, end: date) -> dict:
    db = ctx.db
    opening = db.scalar(select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(CreditTransaction.account_id == a.id,
                                                                                           CreditTransaction.business_date < start)) or ZERO
    rows, running = [], opening
    for t in db.scalars(select(CreditTransaction).where(CreditTransaction.account_id == a.id, CreditTransaction.business_date.between(start, end))
                        .order_by(CreditTransaction.business_date, CreditTransaction.created_at)):
        running += t.amount
        bill = db.get(Bill, t.bill_id) if t.bill_id else None
        rows.append({"date": t.business_date, "txn_no": t.txn_no, "kind": t.kind, "bill_no": bill.bill_no if bill else None, "reference": t.reference,
                     "due_date": t.due_date, "charge": t.amount if t.amount > 0 else ZERO, "payment_or_credit": -t.amount if t.amount < 0 else ZERO,
                     "balance": q(running), "reason": t.reason})
    return {"account": account_out(ctx, a), "from": start, "to": end, "opening_balance": q(opening), "closing_balance": q(running), "lines": rows,
            "ageing": ageing(ctx, a, end)}
