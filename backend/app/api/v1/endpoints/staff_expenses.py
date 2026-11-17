"""Employees, schedules, attendance (STAFF §6.14) and expenses (EXP §6.13; BR-020, BR-051)."""
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import func, or_, select

from app.core.dependencies import Ctx, require
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.models import (Attendance, CashierSession, CashMovement, Department, Employee, Expense, ExpenseAttachment, ExpenseCategory, OrderDiscount, OrderItem, Payment, Position,
                        ShiftSchedule, User)
from app.schemas.common import ORM, Strict
from app.services import cash as csvc
from app.services.auth import revoke_all
from app.services.billing import current_rate, open_session_for
from app.services.platform import audit, next_number, notify_permission
from app.utils.money import q
from app.utils.timeutil import utcnow

staff = APIRouter(tags=["employees"])
expenses = APIRouter(tags=["expenses"])
EView = Annotated[Ctx, Depends(require("employees.view"))]
EManage = Annotated[Ctx, Depends(require("employees.manage"))]
UPLOAD_DIR = Path(__file__).resolve().parents[4] / "uploads"
ALLOWED_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
MAX_UPLOAD = 10 * 1024 * 1024


# ---------------------------------------------------------------- employees
class NamedIn(Strict):
    name: str = Field(min_length=1, max_length=60)


class EmployeeIn(Strict):
    employee_code: str = Field(min_length=1, max_length=20)
    name_en: str = Field(min_length=1, max_length=120)
    name_km: str | None = None
    department_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    start_date: date
    phone: str | None = None
    user_id: uuid.UUID | None = Field(None, description="Optional link to one user account (BR-051)")


class EmployeePatch(Strict):
    name_en: str | None = None
    name_km: str | None = None
    department_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    phone: str | None = None
    status: Literal["Active", "Inactive"] | None = None
    user_id: uuid.UUID | None = None


class EmployeeOut(ORM):
    id: uuid.UUID
    employee_code: str
    name_en: str
    name_km: str | None
    department_id: uuid.UUID | None
    position_id: uuid.UUID | None
    branch_id: uuid.UUID
    status: str
    start_date: date
    phone: str | None
    user_id: uuid.UUID | None = None


def _employee(ctx: Ctx, eid: uuid.UUID) -> Employee:
    e = ctx.db.get(Employee, eid)
    if e is None or e.branch_id not in {b.id for b in ctx.user.branches}:
        raise NotFound("Employee")
    return e


def _emp_out(ctx: Ctx, e: Employee) -> dict:
    return {**EmployeeOut.model_validate(e).model_dump(), "user_id": ctx.db.scalar(select(User.id).where(User.employee_id == e.id))}


def _link_user(ctx: Ctx, e: Employee, user_id: uuid.UUID | None) -> None:
    for u in ctx.db.scalars(select(User).where(User.employee_id == e.id)):
        u.employee_id = None
    ctx.db.flush()
    if user_id:
        u = ctx.db.get(User, user_id)
        if u is None:
            raise NotFound("User")
        if u.employee_id and u.employee_id != e.id:
            raise Conflict("USER_ALREADY_LINKED", "That user account is linked to another employee.")
        u.employee_id = e.id


@staff.get("/departments")
def departments(ctx: EView):
    return [{"id": d.id, "name": d.name, "is_active": d.is_active} for d in ctx.db.scalars(select(Department).order_by(Department.name))]


@staff.post("/departments", status_code=201)
def add_department(body: NamedIn, ctx: EManage):
    if ctx.db.scalar(select(Department.id).where(Department.name == body.name)):
        raise Conflict("DEPARTMENT_EXISTS", "This department already exists.")
    d = Department(name=body.name)
    ctx.db.add(d)
    ctx.db.flush()
    return {"id": d.id, "name": d.name}


@staff.get("/positions")
def positions(ctx: EView):
    return [{"id": p.id, "name": p.name, "is_active": p.is_active} for p in ctx.db.scalars(select(Position).order_by(Position.name))]


@staff.post("/positions", status_code=201)
def add_position(body: NamedIn, ctx: EManage):
    if ctx.db.scalar(select(Position.id).where(Position.name == body.name)):
        raise Conflict("POSITION_EXISTS", "This position already exists.")
    p = Position(name=body.name)
    ctx.db.add(p)
    ctx.db.flush()
    return {"id": p.id, "name": p.name}


@staff.get("/employees")
def list_employees(ctx: EView, q: str | None = None, department_id: uuid.UUID | None = None, status: str | None = None):
    stmt = select(Employee).where(Employee.branch_id == ctx.branch_id)
    if q:
        stmt = stmt.where(or_(Employee.name_en.ilike(f"%{q}%"), Employee.name_km.ilike(f"%{q}%"), Employee.employee_code.ilike(f"%{q}%")))
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if status:
        stmt = stmt.where(Employee.status == status)
    return [_emp_out(ctx, e) for e in ctx.db.scalars(stmt.order_by(Employee.employee_code))]


@staff.post("/employees", status_code=201)
def create_employee(body: EmployeeIn, ctx: EManage):
    if ctx.db.scalar(select(Employee.id).where(Employee.employee_code == body.employee_code)):
        raise Conflict("EMPLOYEE_CODE_EXISTS", "An employee with this code already exists.")
    e = Employee(branch_id=ctx.branch_id, **body.model_dump(exclude={"user_id"}))
    ctx.db.add(e)
    ctx.db.flush()
    _link_user(ctx, e, body.user_id)
    audit(ctx.db, ctx, "employee.create", "Employee", e.id, after=body.model_dump())
    return _emp_out(ctx, e)


@staff.patch("/employees/{employee_id}")
def update_employee(employee_id: uuid.UUID, body: EmployeePatch, ctx: EManage):
    e = _employee(ctx, employee_id)
    data = body.model_dump(exclude_unset=True)
    if "user_id" in data:
        _link_user(ctx, e, data.pop("user_id"))
    before = {k: getattr(e, k) for k in data}
    for k, v in data.items():
        setattr(e, k, v)
    if data.get("status") == "Inactive":
        # BR-051: deactivating the employee deactivates the linked user account
        for u in ctx.db.scalars(select(User).where(User.employee_id == e.id)):
            u.status = "Inactive"
            revoke_all(ctx.db, u.id)
    audit(ctx.db, ctx, "employee.update", "Employee", e.id, before=before, after=data)
    return _emp_out(ctx, e)


class ShiftIn(Strict):
    employee_id: uuid.UUID
    shift_date: date
    start_time: time
    end_time: time
    note: str | None = Field(None, max_length=120)


@staff.get("/shift-schedules", summary="Weekly schedule view (FR-STAFF-003)")
def schedules(ctx: EView, week_start: date):
    end = week_start + timedelta(days=7)
    rows = ctx.db.execute(select(ShiftSchedule, Employee.name_en).join(Employee).where(ShiftSchedule.branch_id == ctx.branch_id,
                                                                                      ShiftSchedule.shift_date >= week_start, ShiftSchedule.shift_date < end)
                          .order_by(ShiftSchedule.shift_date, ShiftSchedule.start_time)).all()
    return [{"id": s.id, "employee_id": s.employee_id, "employee": name, "shift_date": s.shift_date, "start_time": s.start_time, "end_time": s.end_time, "note": s.note}
            for s, name in rows]


@staff.post("/shift-schedules", status_code=201)
def add_shift(body: ShiftIn, ctx: EManage):
    e = _employee(ctx, body.employee_id)
    if e.status != "Active":
        raise Conflict("EMPLOYEE_INACTIVE", "This employee is inactive.")
    for s in ctx.db.scalars(select(ShiftSchedule).where(ShiftSchedule.employee_id == e.id, ShiftSchedule.shift_date == body.shift_date)):
        if body.start_time < s.end_time and s.start_time < body.end_time:
            raise Conflict("SHIFT_OVERLAP", "This overlaps another shift for the same employee.")
    s = ShiftSchedule(branch_id=ctx.branch_id, created_by=ctx.user_id, **body.model_dump())
    ctx.db.add(s)
    ctx.db.flush()
    audit(ctx.db, ctx, "schedule.add", "ShiftSchedule", s.id, after=body.model_dump())
    return {"id": s.id}


@staff.delete("/shift-schedules/{shift_id}")
def delete_shift(shift_id: uuid.UUID, ctx: EManage):
    s = ctx.db.get(ShiftSchedule, shift_id)
    if s is None or s.branch_id != ctx.branch_id:
        raise NotFound("Shift")
    ctx.db.delete(s)
    audit(ctx.db, ctx, "schedule.remove", "ShiftSchedule", shift_id)
    return {"message": "Shift removed."}


@staff.post("/employees/{employee_id}/clock-{action}", summary="Attendance (FR-STAFF-004): clock-in or clock-out")
def clock(employee_id: uuid.UUID, action: Literal["in", "out"], ctx: EView):
    e = _employee(ctx, employee_id)
    own = ctx.db.scalar(select(User.id).where(User.employee_id == e.id)) == ctx.user_id
    if not own and not ctx.can("employees.manage"):
        raise Forbidden("You can only clock yourself in or out.", code="NOT_OWN_EMPLOYEE")
    open_row = ctx.db.scalar(select(Attendance).where(Attendance.employee_id == e.id, Attendance.clock_out.is_(None)).with_for_update())
    if action == "in":
        if open_row:
            raise Conflict("ALREADY_CLOCKED_IN", "Already clocked in.")
        a = Attendance(employee_id=e.id, branch_id=ctx.branch_id)
        ctx.db.add(a)
    else:
        if not open_row:
            raise Conflict("NOT_CLOCKED_IN", "Not clocked in.")
        open_row.clock_out = utcnow()
        a = open_row
    ctx.db.flush()
    return {"employee_id": e.id, "clock_in": a.clock_in, "clock_out": a.clock_out}


@staff.get("/employees/{employee_id}/activity", summary="Sessions, sales, voids, discounts and refunds by the linked user (FR-STAFF-014)")
def activity(employee_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("employees.view", "report.view"))], date_from: date | None = None, date_to: date | None = None):
    e = _employee(ctx, employee_id)
    uid = ctx.db.scalar(select(User.id).where(User.employee_id == e.id))
    if uid is None:
        return {"employee_id": e.id, "linked_user": None}
    start, end = date_from or ctx.business_date() - timedelta(days=30), date_to or ctx.business_date()
    from app.models import CashierSession, Order, Refund

    db = ctx.db
    return {"employee_id": e.id, "linked_user": uid, "from": start, "to": end,
            "cashier_sessions": db.scalar(select(func.count()).select_from(CashierSession).where(CashierSession.user_id == uid, CashierSession.business_date.between(start, end))),
            "orders_served": db.scalar(select(func.count()).select_from(Order).where(Order.server_user_id == uid, Order.business_date.between(start, end), Order.order_status == "Completed")),
            "payments_taken_base": q(db.scalar(select(func.coalesce(func.sum(Payment.amount_base), 0)).where(Payment.received_by == uid, Payment.status == "Confirmed",
                                                                                                             Payment.business_date.between(start, end)))),
            "voids": db.scalar(select(func.count()).select_from(OrderItem).join(Order).where(Order.server_user_id == uid, OrderItem.void_type.is_not(None),
                                                                                              Order.business_date.between(start, end))),
            "discounts": db.scalar(select(func.count()).select_from(OrderDiscount).where(OrderDiscount.requested_by == uid)),
            "refunds_requested": db.scalar(select(func.count()).select_from(Refund).where(Refund.requested_by == uid, Refund.business_date.between(start, end)))}


# ---------------------------------------------------------------- expenses
class CategoryIn(Strict):
    name_en: str = Field(min_length=1, max_length=60)
    name_km: str | None = None
    attachment_required: bool = False


class ExpenseIn(Strict):
    category_id: uuid.UUID
    expense_date: date
    description: str = Field(min_length=2, max_length=500)
    amount: Decimal = Field(gt=0)
    currency: Literal["USD", "KHR"] = "USD"
    payee: str = Field(min_length=1, max_length=120)


class DecisionIn(Strict):
    approve: bool
    reason: str | None = Field(None, max_length=300)


class PayIn(Strict):
    method: Literal["CASH_DRAWER", "BANK_TRANSFER", "KHQR", "CARD", "OTHER"]
    reference: str | None = Field(None, max_length=80)
    paid_at: datetime | None = None


class ReverseIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


def _exp(ctx: Ctx, eid: uuid.UUID, lock: bool = False) -> Expense:
    stmt = select(Expense).where(Expense.id == eid, Expense.branch_id == ctx.branch_id)
    e = ctx.db.scalar(stmt.with_for_update() if lock else stmt)
    if e is None:
        raise NotFound("Expense")
    return e


def exp_out(e: Expense) -> dict:
    return {"id": e.id, "expense_no": e.expense_no, "category_id": e.category_id, "expense_date": e.expense_date, "description": e.description, "amount": e.amount,
            "currency": e.currency, "amount_base": e.amount_base, "payee": e.payee, "status": e.status, "submitted_by": e.submitted_by, "approved_by": e.approved_by,
            "decision_reason": e.decision_reason, "payment_method": e.payment_method, "paid_at": e.paid_at, "payment_ref": e.payment_ref,
            "attachments": [{"id": a.id, "filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes} for a in e.attachments], "version": e.version}


@expenses.get("/expense-categories")
def categories(ctx: Annotated[Ctx, Depends(require("expenses.view"))]):
    return [{"id": c.id, "name_en": c.name_en, "name_km": c.name_km, "attachment_required": c.attachment_required, "is_active": c.is_active}
            for c in ctx.db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name_en))]


@expenses.post("/expense-categories", status_code=201)
def add_category(body: CategoryIn, ctx: Annotated[Ctx, Depends(require("settings.manage"))]):
    c = ExpenseCategory(**body.model_dump())
    ctx.db.add(c)
    ctx.db.flush()
    audit(ctx.db, ctx, "expense.category_create", "ExpenseCategory", c.id, after=body.model_dump())
    return {"id": c.id}


@expenses.get("/expenses")
def list_expenses(ctx: Annotated[Ctx, Depends(require("expenses.view"))], status: str | None = None, category_id: uuid.UUID | None = None,
                  date_from: date | None = None, date_to: date | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(Expense).where(Expense.branch_id == ctx.branch_id)
    for col, val in ((Expense.status, status), (Expense.category_id, category_id)):
        if val:
            stmt = stmt.where(col == val)
    if date_from:
        stmt = stmt.where(Expense.expense_date >= date_from)
    if date_to:
        stmt = stmt.where(Expense.expense_date <= date_to)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": [exp_out(e) for e in rows], "total": total, "page": page, "page_size": page_size}


@expenses.post("/expenses", status_code=201, summary="Record a draft expense")
def create_expense(body: ExpenseIn, ctx: Annotated[Ctx, Depends(require("expenses.create"))]):
    cat = ctx.db.get(ExpenseCategory, body.category_id)
    if cat is None or not cat.is_active:
        raise NotFound("Expense category")
    if body.expense_date > ctx.business_date():
        raise BusinessRuleError("EXPENSE_DATE_FUTURE", "The expense date can't be in the future.", details=[{"field": "expense_date", "issue": "future"}])
    if body.currency == "USD":
        base = body.amount
    else:
        rate = current_rate(ctx.db, body.currency)
        if rate is None:
            raise Conflict("EXCHANGE_RATE_MISSING", f"No exchange rate for {body.currency}.")
        base = q(body.amount / rate.rate)
    e = Expense(branch_id=ctx.branch_id, expense_no=f"EX-{next_number(ctx.db, ctx.branch_id, 'EXPENSE', 'EX'):06d}", amount_base=base, submitted_by=ctx.user_id, **body.model_dump())
    ctx.db.add(e)
    ctx.db.flush()
    ctx.db.refresh(e)
    audit(ctx.db, ctx, "expense.create", "Expense", e.id, after=body.model_dump())
    return exp_out(e)


@expenses.post("/expenses/{expense_id}/attachments", status_code=201, summary="PDF, JPG or PNG up to 10 MB")
async def upload(expense_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("expenses.create"))], file: UploadFile = File(...)):
    e = _exp(ctx, expense_id)
    if e.status not in ("Draft", "Submitted"):
        raise Conflict("EXPENSE_LOCKED", "Attachments can only be added before approval.")
    ext = ALLOWED_TYPES.get(file.content_type or "")
    if ext is None:
        raise BusinessRuleError("FILE_TYPE", "Attach a PDF, JPG or PNG file.")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise BusinessRuleError("FILE_TOO_LARGE", "The file is larger than 10 MB.")
    key = f"{uuid.uuid4().hex}{ext}"
    UPLOAD_DIR.mkdir(exist_ok=True)
    (UPLOAD_DIR / key).write_bytes(data)
    a = ExpenseAttachment(expense_id=e.id, filename=(file.filename or key)[:200], content_type=file.content_type, size_bytes=len(data), storage_key=key, uploaded_by=ctx.user_id)
    ctx.db.add(a)
    ctx.db.flush()
    audit(ctx.db, ctx, "expense.attachment", "Expense", e.id, after={"file": a.filename, "bytes": a.size_bytes})
    return {"id": a.id, "filename": a.filename}


@expenses.get("/expenses/{expense_id}/attachments/{attachment_id}", summary="Download; only roles with expenses.view (FR-EXP-009)")
def download(expense_id: uuid.UUID, attachment_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("expenses.view"))]):
    e = _exp(ctx, expense_id)
    a = next((x for x in e.attachments if x.id == attachment_id), None)
    if a is None:
        raise NotFound("Attachment")
    return FileResponse(UPLOAD_DIR / a.storage_key, media_type=a.content_type, filename=a.filename)


@expenses.post("/expenses/{expense_id}/submit", summary="Within your limit it is approved at once; above it, a different user must approve (BR-020)")
def submit(expense_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("expenses.create"))]):
    e = _exp(ctx, expense_id, lock=True)
    if e.status != "Draft":
        raise Conflict("EXPENSE_NOT_DRAFT", f"This expense is {e.status}.")
    if ctx.db.get(ExpenseCategory, e.category_id).attachment_required and not e.attachments:
        raise BusinessRuleError("ATTACHMENT_REQUIRED", "This category needs a supporting document. Attach a file first.", details=[{"field": "attachments", "issue": "required"}])
    e.submitted_at = utcnow()
    if e.amount_base <= ctx.limit("expense_amount"):
        e.status, e.decided_at, e.decision_reason = "Approved", utcnow(), "Within the submitter's limit"
    else:
        e.status = "Submitted"
        notify_permission(ctx.db, ctx.branch_id, "expenses.approve", "Approval", "Expense awaiting approval", f"{e.expense_no}: {e.amount_base} USD, {e.description}", "/expenses?tab=approvals")
    audit(ctx.db, ctx, "expense.submit", "Expense", e.id, after={"status": e.status, "amount_base": e.amount_base})
    return exp_out(e)


@expenses.post("/expenses/{expense_id}/decision")
def decide(expense_id: uuid.UUID, body: DecisionIn, ctx: Annotated[Ctx, Depends(require("expenses.approve"))]):
    e = _exp(ctx, expense_id, lock=True)
    if e.status != "Submitted":
        raise Conflict("EXPENSE_NOT_SUBMITTED", f"This expense is {e.status}.")
    if e.submitted_by == ctx.user_id:
        raise Forbidden("You can't approve your own expense.", code="SELF_APPROVAL")
    if body.approve and e.amount_base > ctx.limit("expense_amount"):
        raise Forbidden(f"This exceeds your approval limit of {ctx.limit('expense_amount')}.", code="APPROVER_LIMIT_EXCEEDED")
    if not body.approve and not body.reason:
        raise BusinessRuleError("REASON_REQUIRED", "Give a reason for rejecting.")
    e.status, e.approved_by, e.decided_at, e.decision_reason = ("Approved" if body.approve else "Rejected"), ctx.user_id, utcnow(), body.reason
    audit(ctx.db, ctx, f"expense.{'approve' if body.approve else 'reject'}", "Expense", e.id, reason=body.reason)
    return exp_out(e)


@expenses.post("/expenses/{expense_id}/pay", summary="CASH_DRAWER records a paid-out in your open cashier session (FR-EXP-005)")
def pay(expense_id: uuid.UUID, body: PayIn, ctx: Annotated[Ctx, Depends(require("expenses.pay"))]):
    e = _exp(ctx, expense_id, lock=True)
    if e.status != "Approved":
        raise Conflict("EXPENSE_NOT_APPROVED", f"Only approved expenses can be paid; this one is {e.status}.")
    if body.method == "CASH_DRAWER":
        session = open_session_for(ctx.db, ctx.branch_id, ctx.user_id)
        if session is None:
            raise Conflict("CASHIER_SESSION_REQUIRED", "Open a cashier session to pay out cash.")
        m = csvc.add_movement(ctx, session, "PaidOut", e.currency, e.amount, f"Expense {e.expense_no}: {e.description}")
        m.expense_id = e.id
    elif not body.reference:
        raise BusinessRuleError("REFERENCE_REQUIRED", "Enter the payment reference.")
    e.status, e.payment_method, e.payment_ref, e.paid_at, e.paid_by = "Paid", body.method, body.reference, body.paid_at or utcnow(), ctx.user_id
    audit(ctx.db, ctx, "expense.pay", "Expense", e.id, after={"method": body.method, "reference": body.reference})
    return exp_out(e)


@expenses.post("/expenses/{expense_id}/reverse", summary="Reverse a paid expense; the original stays on record (FR-EXP-006)")
def reverse(expense_id: uuid.UUID, body: ReverseIn, ctx: Annotated[Ctx, Depends(require("expenses.approve"))]):
    e = _exp(ctx, expense_id, lock=True)
    if e.status != "Paid":
        raise Conflict("EXPENSE_NOT_PAID", "Only paid expenses can be reversed.")
    if ctx.user_id in (e.submitted_by, e.paid_by):
        raise Forbidden("A different user must reverse this expense.", code="SELF_APPROVAL")
    if e.payment_method == "CASH_DRAWER":
        # Cash returned to a still-open drawer is recorded as a paid-in; a closed session is never edited.
        m = ctx.db.scalar(select(CashMovement).where(CashMovement.expense_id == e.id, CashMovement.kind == "PaidOut"))
        s = ctx.db.get(CashierSession, m.session_id)
        if s.status == "Open":
            ctx.db.add(CashMovement(branch_id=ctx.branch_id, session_id=s.id, kind="PaidIn", currency=m.currency, amount=m.amount, reason=f"Reversal of {e.expense_no}",
                                    expense_id=e.id, created_by=ctx.user_id, approved_by=ctx.user_id))
    e.status, e.reversed_by = "Reversed", ctx.user_id
    audit(ctx.db, ctx, "expense.reverse", "Expense", e.id, reason=body.reason)
    return exp_out(e)


@expenses.get("/expenses/summary", summary="Daily or monthly totals by category and payment method (FR-EXP-007)")
def summary(ctx: Annotated[Ctx, Depends(require("expenses.view"))], date_from: date, date_to: date, period: Literal["day", "month"] = "month"):
    bucket = func.date_trunc(period, Expense.expense_date)
    rows = ctx.db.execute(select(bucket, ExpenseCategory.name_en, Expense.payment_method, func.sum(Expense.amount_base), func.count())
                          .join(ExpenseCategory).where(Expense.branch_id == ctx.branch_id, Expense.status.in_(("Approved", "Paid")),
                                                       Expense.expense_date.between(date_from, date_to))
                          .group_by(bucket, ExpenseCategory.name_en, Expense.payment_method).order_by(bucket)).all()
    return [{"period": p.date().isoformat() if hasattr(p, "date") else str(p), "category": c, "payment_method": m, "total_base": q(t), "count": n} for p, c, m, t, n in rows]
