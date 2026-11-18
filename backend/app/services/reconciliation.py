"""Payment reconciliation per business day (SRS FR-BILL-018).

The accountant types or imports the bank or provider statement for one day and one electronic payment method. Each
statement line is matched to a recorded payment by its reference (and checked on amount and currency). The view shows
payments with no statement line, statement lines with no payment, and amount differences. Reconciliation never edits
or deletes a payment (BR-011, BR-022); a difference is resolved by the normal void/refund process and noted here.
"""
import csv
import io
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, NotFound
from app.models import Bill, Order, Payment, PaymentMethod, PaymentReconciliation, ReconciliationLine
from app.services.platform import audit
from app.utils.timeutil import utcnow

ELECTRONIC = ("QR", "Bank", "Card")
CENT = Decimal("0.01")


def _norm(ref: str) -> str:
    return "".join(ref.split()).upper()


def electronic_methods(db) -> list[PaymentMethod]:
    return list(db.scalars(select(PaymentMethod).where(PaymentMethod.kind.in_(ELECTRONIC)).order_by(PaymentMethod.name)))


def _method(db, code: str) -> PaymentMethod:
    m = db.scalar(select(PaymentMethod).where(PaymentMethod.code == code))
    if m is None:
        raise NotFound("Payment method")
    if m.kind not in ELECTRONIC:
        raise BusinessRuleError("NOT_ELECTRONIC", f"{m.name} isn't an electronic method; cash is checked by the cash session count.")
    return m


def _payments(ctx: Ctx, business_date: date, method_code: str) -> list[Payment]:
    return list(ctx.db.scalars(select(Payment).where(Payment.branch_id == ctx.branch_id, Payment.business_date == business_date, Payment.method_code == method_code,
                                                     Payment.status == "Confirmed").order_by(Payment.created_at)))


def _rec(ctx: Ctx, business_date: date, method_code: str, create: bool = False) -> PaymentReconciliation | None:
    r = ctx.db.scalar(select(PaymentReconciliation).where(PaymentReconciliation.branch_id == ctx.branch_id, PaymentReconciliation.business_date == business_date,
                                                          PaymentReconciliation.method_code == method_code).with_for_update())
    if r is None and create:
        r = PaymentReconciliation(branch_id=ctx.branch_id, business_date=business_date, method_code=method_code, created_by=ctx.user_id)
        ctx.db.add(r)
        ctx.db.flush()
    return r


def _ensure_open(r: PaymentReconciliation) -> None:
    if r.status == "Closed":
        raise Conflict("RECONCILIATION_CLOSED", "This day is already reconciled and locked.")


def _classify(line: ReconciliationLine, p: Payment | None) -> str:
    if p is None:
        return "NotRecorded"
    return "Matched" if (p.amount_tendered.quantize(CENT) == line.amount.quantize(CENT) and p.currency == line.currency) else "AmountMismatch"


def _auto_match(ctx: Ctx, rec: PaymentReconciliation, line: ReconciliationLine, taken: set[uuid.UUID]) -> None:
    ref = _norm(line.reference)
    for p in _payments(ctx, rec.business_date, rec.method_code):
        if p.id not in taken and p.external_ref and _norm(p.external_ref) == ref:
            line.payment_id = p.id
            taken.add(p.id)
            break
    line.match_status = _classify(line, ctx.db.get(Payment, line.payment_id) if line.payment_id else None)


def view(ctx: Ctx, business_date: date, method_code: str) -> dict:
    m = _method(ctx.db, method_code)
    rec = _rec(ctx, business_date, method_code)
    pays = _payments(ctx, business_date, method_code)
    lines = list(ctx.db.scalars(select(ReconciliationLine).where(ReconciliationLine.reconciliation_id == rec.id).order_by(ReconciliationLine.created_at))) if rec else []
    by_payment = {ln.payment_id: ln for ln in lines if ln.payment_id}
    orders = dict(ctx.db.execute(select(Bill.id, Order.order_no).join(Order, Order.id == Bill.order_id).where(Bill.id.in_([p.bill_id for p in pays] or [uuid.UUID(int=0)]))).all())
    pay_rows = []
    for p in pays:
        ln = by_payment.get(p.id)
        pay_rows.append({"payment_id": p.id, "order_no": orders.get(p.bill_id), "reference": p.external_ref, "amount": p.amount_tendered, "currency": p.currency,
                         "recorded_at": p.created_at, "status": ln.match_status if ln else "NotOnStatement", "line_id": ln.id if ln else None})
    recorded = sum((p.amount_base for p in pays), Decimal("0"))
    statement = {}
    for ln in lines:
        statement[ln.currency] = statement.get(ln.currency, Decimal("0")) + ln.amount
    recorded_by_cur = {}
    for p in pays:
        recorded_by_cur[p.currency] = recorded_by_cur.get(p.currency, Decimal("0")) + p.amount_tendered
    counts = {"matched": sum(1 for ln in lines if ln.match_status == "Matched"), "amount_mismatch": sum(1 for ln in lines if ln.match_status == "AmountMismatch"),
              "not_recorded": sum(1 for ln in lines if ln.match_status == "NotRecorded"), "not_on_statement": sum(1 for r in pay_rows if r["status"] == "NotOnStatement")}
    return {
        "business_date": business_date, "method_code": m.code, "method_name": m.name,
        "reconciliation_id": rec.id if rec else None, "status": rec.status if rec else "NotStarted", "note": rec.note if rec else None,
        "closed_at": rec.closed_at if rec else None,
        "payments": pay_rows,
        "lines": [{"id": ln.id, "reference": ln.reference, "amount": ln.amount, "currency": ln.currency, "received_at": ln.received_at, "payment_id": ln.payment_id,
                   "match_status": ln.match_status, "matched_manually": ln.matched_manually, "note": ln.note} for ln in lines],
        "totals": {"recorded": {k: v for k, v in recorded_by_cur.items()}, "statement": statement, "recorded_base": recorded},
        "counts": counts,
        "balanced": counts["amount_mismatch"] == 0 and counts["not_recorded"] == 0 and counts["not_on_statement"] == 0,
    }


def add_lines(ctx: Ctx, business_date: date, method_code: str, entries: list[dict]) -> dict:
    """Entries already on the statement (same reference) are skipped, so importing the same file twice adds nothing."""
    _method(ctx.db, method_code)
    if business_date > ctx.business_date():
        raise BusinessRuleError("VALIDATION_ERROR", "That business day hasn't happened yet.")
    rec = _rec(ctx, business_date, method_code, create=True)
    _ensure_open(rec)
    existing = {_norm(r) for r in ctx.db.scalars(select(ReconciliationLine.reference).where(ReconciliationLine.reconciliation_id == rec.id))}
    taken = set(ctx.db.scalars(select(ReconciliationLine.payment_id).where(ReconciliationLine.reconciliation_id == rec.id, ReconciliationLine.payment_id.is_not(None))))
    added, skipped = 0, 0
    for e in entries:
        ref = e["reference"].strip()
        if _norm(ref) in existing:
            skipped += 1
            continue
        ln = ReconciliationLine(reconciliation_id=rec.id, reference=ref, amount=Decimal(str(e["amount"])).quantize(CENT), currency=e.get("currency") or "USD",
                                received_at=e.get("received_at"), created_by=ctx.user_id, match_status="NotRecorded")
        ctx.db.add(ln)
        _auto_match(ctx, rec, ln, taken)
        existing.add(_norm(ref))
        added += 1
    ctx.db.flush()
    audit(ctx.db, ctx, "reconciliation.lines_add", "PaymentReconciliation", rec.id, after={"date": business_date, "method": method_code, "added": added, "skipped": skipped})
    return {"added": added, "skipped": skipped, **view(ctx, business_date, method_code)}


def parse_csv(text: str) -> list[dict]:
    """reference,amount[,currency][,received_at] with a header row; amounts like 12.50 (no thousands separators)."""
    rows = list(csv.DictReader(io.StringIO(text.strip())))
    if not rows:
        raise BusinessRuleError("IMPORT_EMPTY", "The file has no rows.")
    head = {k.strip().lower(): k for k in rows[0].keys() if k}
    if "reference" not in head or "amount" not in head:
        raise BusinessRuleError("IMPORT_COLUMNS", "The file needs 'reference' and 'amount' columns.")
    out, errors = [], []
    for n, r in enumerate(rows, start=2):
        ref = (r.get(head["reference"]) or "").strip()
        try:
            amount = Decimal((r.get(head["amount"]) or "").strip())
            if amount <= 0:
                raise InvalidOperation
        except InvalidOperation:
            errors.append({"field": f"row {n}", "issue": "amount must be a positive number"})
            continue
        if not ref:
            errors.append({"field": f"row {n}", "issue": "reference is empty"})
            continue
        cur = (r.get(head["currency"]) or "USD").strip().upper() if "currency" in head else "USD"
        if cur not in ("USD", "KHR"):
            errors.append({"field": f"row {n}", "issue": "currency must be USD or KHR"})
            continue
        received = None
        if "received_at" in head and (r.get(head["received_at"]) or "").strip():
            try:
                received = datetime.fromisoformat(r[head["received_at"]].strip())
            except ValueError:
                errors.append({"field": f"row {n}", "issue": "received_at must be an ISO date and time"})
                continue
        out.append({"reference": ref[:80], "amount": amount, "currency": cur, "received_at": received})
    if errors:
        raise BusinessRuleError("IMPORT_INVALID", f"{len(errors)} row(s) couldn't be read. Nothing was imported.", details=errors[:50])
    return out


def _line(ctx: Ctx, line_id: uuid.UUID) -> tuple[ReconciliationLine, PaymentReconciliation]:
    ln = ctx.db.get(ReconciliationLine, line_id)
    rec = ctx.db.get(PaymentReconciliation, ln.reconciliation_id) if ln else None
    if ln is None or rec.branch_id != ctx.branch_id:
        raise NotFound("Statement line")
    _ensure_open(rec)
    return ln, rec


def match(ctx: Ctx, line_id: uuid.UUID, payment_id: uuid.UUID | None, note: str) -> dict:
    """Link a statement line to a payment by hand (e.g. the bank shortened the reference), or unlink it."""
    ln, rec = _line(ctx, line_id)
    before = {"payment_id": ln.payment_id, "status": ln.match_status}
    p = None
    if payment_id:
        p = ctx.db.get(Payment, payment_id)
        if p is None or p.branch_id != ctx.branch_id or p.method_code != rec.method_code or p.business_date != rec.business_date or p.status != "Confirmed":
            raise BusinessRuleError("PAYMENT_NOT_ELIGIBLE", "Choose a confirmed payment of the same method and business day.")
        other = ctx.db.scalar(select(ReconciliationLine.id).where(ReconciliationLine.reconciliation_id == rec.id, ReconciliationLine.payment_id == p.id,
                                                                  ReconciliationLine.id != ln.id))
        if other:
            raise Conflict("PAYMENT_ALREADY_MATCHED", "That payment is already matched to another statement line.")
    ln.payment_id, ln.matched_manually, ln.note = (p.id if p else None), True, note
    ln.match_status = _classify(ln, p)
    audit(ctx.db, ctx, "reconciliation.match", "ReconciliationLine", ln.id, before=before, after={"payment_id": ln.payment_id, "status": ln.match_status}, reason=note)
    return view(ctx, rec.business_date, rec.method_code)


def remove_line(ctx: Ctx, line_id: uuid.UUID, reason: str) -> dict:
    """Removes a mistyped statement line (accountant's entry, not a financial transaction) while the day is open."""
    ln, rec = _line(ctx, line_id)
    audit(ctx.db, ctx, "reconciliation.line_remove", "ReconciliationLine", ln.id,
          before={"reference": ln.reference, "amount": ln.amount, "currency": ln.currency, "payment_id": ln.payment_id}, reason=reason)
    ctx.db.delete(ln)
    ctx.db.flush()
    return view(ctx, rec.business_date, rec.method_code)


def close(ctx: Ctx, business_date: date, method_code: str, note: str | None) -> dict:
    v = view(ctx, business_date, method_code)
    rec = _rec(ctx, business_date, method_code, create=True)
    _ensure_open(rec)
    if not v["balanced"] and not (note and note.strip()):
        raise BusinessRuleError("RECONCILIATION_DIFFERENCES", "There are unmatched items or amount differences. Explain them in a note to lock the day anyway.",
                                details=[{"field": "note", "issue": "required when not balanced"}])
    rec.status, rec.note, rec.closed_by, rec.closed_at = "Closed", note, ctx.user_id, utcnow()
    audit(ctx.db, ctx, "reconciliation.close", "PaymentReconciliation", rec.id, after={"date": business_date, "method": method_code, "counts": v["counts"]}, reason=note)
    return view(ctx, business_date, method_code)


def summary(ctx: Ctx, date_from: date, date_to: date) -> list[dict]:
    """Days with electronic payments or a reconciliation, with their state, for the overview list."""
    codes = [m.code for m in electronic_methods(ctx.db)]
    pays = ctx.db.execute(select(Payment.business_date, Payment.method_code, func.count(), func.sum(Payment.amount_base))
                          .where(Payment.branch_id == ctx.branch_id, Payment.business_date.between(date_from, date_to), Payment.method_code.in_(codes),
                                 Payment.status == "Confirmed").group_by(Payment.business_date, Payment.method_code)).all()
    recs = {(r.business_date, r.method_code): r for r in ctx.db.scalars(select(PaymentReconciliation).where(
        PaymentReconciliation.branch_id == ctx.branch_id, PaymentReconciliation.business_date.between(date_from, date_to)))}
    keys = {(d, m) for d, m, *_ in pays} | set(recs)
    agg = {(d, m): (n, total) for d, m, n, total in pays}
    out = []
    for d, m in sorted(keys, reverse=True):
        n, total = agg.get((d, m), (0, Decimal("0")))
        r = recs.get((d, m))
        out.append({"business_date": d, "method_code": m, "payments": n, "recorded_base": total or Decimal("0"), "status": r.status if r else "NotStarted",
                    "closed_at": r.closed_at if r else None})
    return out
