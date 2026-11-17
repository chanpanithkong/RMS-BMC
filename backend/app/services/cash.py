"""Cashier sessions (SRS §6.14; BR-013, BR-039)."""
import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.models import CashCount, CashierSession, CashMovement, Payment, Refund, SessionFloat, SessionResult
from app.services.billing import current_rate
from app.services.platform import audit, get_setting, notify_permission
from app.utils.money import ZERO, q
from app.utils.timeutil import utcnow

CURRENCIES = ("USD", "KHR")


def get_session(ctx: Ctx, session_id: uuid.UUID, lock: bool = False) -> CashierSession:
    stmt = select(CashierSession).where(CashierSession.id == session_id, CashierSession.branch_id == ctx.branch_id)
    s = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if s is None or (s.user_id != ctx.user_id and not ctx.can("cash.view")):
        raise NotFound("Cashier session")
    return s


def open_session(ctx: Ctx, floats: dict[str, Decimal], witness_id: uuid.UUID | None) -> CashierSession:
    ctx.require("cash.operate")
    s = CashierSession(branch_id=ctx.branch_id, user_id=ctx.user_id, business_date=ctx.business_date(), witness_id=witness_id)
    ctx.db.add(s)
    try:
        with ctx.db.begin_nested():
            ctx.db.flush()
    except IntegrityError:
        raise Conflict("SESSION_ALREADY_OPEN", "You already have an open cashier session in this branch.")  # BR-039
    for cur in CURRENCIES:
        ctx.db.add(SessionFloat(session_id=s.id, currency=cur, amount=floats.get(cur, ZERO)))
    ctx.db.flush()
    ctx.db.refresh(s)
    audit(ctx.db, ctx, "cash.session_open", "CashierSession", s.id, after={"floats": floats, "witness": witness_id})
    return s


def add_movement(ctx: Ctx, session: CashierSession, kind: str, currency: str, amount: Decimal, reason: str) -> CashMovement:
    if session.status != "Open":
        raise Conflict("SESSION_NOT_OPEN", "This session isn't open.")
    if session.user_id != ctx.user_id:
        raise Forbidden("You can only record movements in your own session.", code="NOT_OWN_SESSION")
    if kind in ("PaidOut", "Drop") and amount > expected(ctx, session)[currency]:
        raise BusinessRuleError("INSUFFICIENT_CASH", f"The drawer doesn't hold {amount} {currency}.")
    m = CashMovement(branch_id=ctx.branch_id, session_id=session.id, kind=kind, currency=currency, amount=amount, reason=reason, created_by=ctx.user_id)
    ctx.db.add(m)
    ctx.db.flush()
    audit(ctx.db, ctx, "cash.movement", "CashierSession", session.id, after={"kind": kind, "currency": currency, "amount": amount}, reason=reason)
    return m


def expected(ctx: Ctx, session: CashierSession) -> dict[str, Decimal]:
    """BR-013: float + cash tendered − change given − cash refunds − paid-outs − drops + paid-ins, per currency."""
    db = ctx.db
    exp = defaultdict(lambda: ZERO, {f.currency: f.amount for f in session.floats})
    for p in db.scalars(select(Payment).where(Payment.cashier_session_id == session.id, Payment.status == "Confirmed")):
        exp[p.currency] += p.amount_tendered
        if p.change_amount:
            exp[p.change_currency] -= p.change_amount
    for r in db.scalars(select(Refund).where(Refund.cashier_session_id == session.id, Refund.status == "Completed")):
        exp[r.currency] -= r.amount
    for m in db.scalars(select(CashMovement).where(CashMovement.session_id == session.id)):
        exp[m.currency] += m.amount if m.kind == "PaidIn" else -m.amount
    return {c: exp[c] for c in CURRENCIES}


def close_session(ctx: Ctx, session: CashierSession, counts: dict[str, Decimal], denominations: dict | None) -> CashierSession:
    """Blind count: the cashier never sees the expected amount before submitting (FR-STAFF-009)."""
    db = ctx.db
    if session.status != "Open":
        raise Conflict("SESSION_NOT_OPEN", "This session isn't open.")
    if session.user_id != ctx.user_id:
        raise Forbidden("Only the session owner closes the session. A manager can force-close it.", code="NOT_OWN_SESSION")
    if db.scalar(select(Payment.id).where(Payment.cashier_session_id == session.id, Payment.status == "Pending").limit(1)):
        raise Conflict("PENDING_PAYMENTS", "Resolve pending electronic payments before closing.")
    exp = expected(ctx, session)
    tol = get_setting(db, "cash", ctx.branch_id).get("variance_tolerance", {})
    beyond = False
    for cur in CURRENCIES:
        counted = counts.get(cur, ZERO)
        db.add(CashCount(session_id=session.id, currency=cur, counted_amount=counted, denominations=(denominations or {}).get(cur), counted_by=ctx.user_id))
        variance = counted - exp[cur]
        db.add(SessionResult(session_id=session.id, currency=cur, expected=exp[cur], counted=counted, variance=variance))
        beyond |= abs(variance) > Decimal(str(tol.get(cur, "0")))
    session.closed_at, session.closed_by = utcnow(), ctx.user_id
    session.status = "ClosingPendingApproval" if beyond else "Closed"
    db.flush()
    db.refresh(session)
    audit(db, ctx, "cash.session_close", "CashierSession", session.id, after={"status": session.status, "results": result_rows(session)})
    if beyond:
        notify_permission(db, ctx.branch_id, "cash.approve", "Cash", "Cash variance needs approval", f"{ctx.user.full_name}'s session closed outside tolerance.", "/shifts?tab=history")
    return session


def variance_in_base(ctx: Ctx, session: CashierSession) -> Decimal:
    total = ZERO
    for r in session.results:
        if r.currency == "USD":
            total += abs(r.variance)
        else:
            rate = current_rate(ctx.db, r.currency)
            total += abs(r.variance) / rate.rate if rate else ZERO
    return q(total)


def approve_variance(ctx: Ctx, session: CashierSession, reason: str) -> CashierSession:
    ctx.require("cash.approve")
    if session.status != "ClosingPendingApproval":
        raise Conflict("NO_VARIANCE_PENDING", "This session isn't waiting for variance approval.")
    if session.user_id == ctx.user_id:
        raise Forbidden("You can't approve your own cash variance.", code="SELF_APPROVAL")  # BR-029
    amount = variance_in_base(ctx, session)
    if amount > ctx.limit("cash_variance"):
        raise Forbidden(f"This variance exceeds your limit of {ctx.limit('cash_variance')}.", code="APPROVER_LIMIT_EXCEEDED")
    session.status, session.approved_by, session.variance_reason = "Closed", ctx.user_id, reason
    audit(ctx.db, ctx, "cash.variance_approve", "CashierSession", session.id, after={"variance_base": amount}, reason=reason)
    return session


def force_close(ctx: Ctx, session: CashierSession, reason: str) -> CashierSession:
    ctx.require("cash.approve")
    if session.status != "Open":
        raise Conflict("SESSION_NOT_OPEN", "Only open sessions can be force-closed.")
    session.status, session.closed_at, session.closed_by, session.variance_reason = "ForceClosed", utcnow(), ctx.user_id, reason
    audit(ctx.db, ctx, "cash.force_close", "CashierSession", session.id, reason=reason)
    return session


def result_rows(session: CashierSession) -> list[dict]:
    return [{"currency": r.currency, "expected": r.expected, "counted": r.counted, "variance": r.variance} for r in session.results]


def session_report(ctx: Ctx, session: CashierSession) -> dict:
    """X report while open, Z report once closed (FR-STAFF-012)."""
    db = ctx.db
    by_method = defaultdict(lambda: {"count": 0, "tendered": ZERO, "base": ZERO})
    for p in db.scalars(select(Payment).where(Payment.cashier_session_id == session.id, Payment.status == "Confirmed")):
        k = f"{p.method_code}:{p.currency}"
        by_method[k]["count"] += 1
        by_method[k]["tendered"] += p.amount_tendered
        by_method[k]["base"] += p.amount_base
    refunds = list(db.scalars(select(Refund).where(Refund.cashier_session_id == session.id, Refund.status == "Completed")))
    movements = list(db.scalars(select(CashMovement).where(CashMovement.session_id == session.id).order_by(CashMovement.created_at)))
    report = {"kind": "X" if session.status == "Open" else "Z", "session_id": session.id, "status": session.status, "opened_at": session.opened_at, "closed_at": session.closed_at,
              "floats": {f.currency: f.amount for f in session.floats},
              "payments": [{"method_currency": k, **v} for k, v in sorted(by_method.items())],
              "refunds": [{"refund_no": r.refund_no, "currency": r.currency, "amount": r.amount} for r in refunds],
              "movements": [{"kind": m.kind, "currency": m.currency, "amount": m.amount, "reason": m.reason} for m in movements]}
    if session.status == "Open":
        report["expected"] = expected(ctx, session) if ctx.can("cash.view") else None  # blind for the cashier until counted
    else:
        report["results"] = result_rows(session)
    return report


_ = NotFound
