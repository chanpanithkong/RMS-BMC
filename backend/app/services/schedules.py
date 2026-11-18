"""Recurring expense templates (FR-EXP-008) and scheduled report emails (FR-RPT-027).

Both run from the worker. Recurring templates create Draft expenses only; a person still reviews, submits and the
normal approval rules apply. Scheduled reports run once per recipient with that recipient's own permissions (checked
again at run time), and the email carries a link, never the report data.
"""
import calendar
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Forbidden, NotFound
from app.models import (Branch, Expense, ExpenseCategory, ExpenseTemplate, ExpenseTemplateRun, OutboxEvent, ReportJob, ReportSchedule, User, UserBranch)
from app.services.platform import audit, next_number
from app.utils.money import q
from app.utils.timeutil import utcnow

MAX_CATCH_UP = 12  # a template that was due for a long time generates at most this many drafts in one run


# ---------------------------------------------------------------- dates
def _next_weekly(after: date, dow: int, inclusive: bool) -> date:
    d = after if inclusive else after + timedelta(days=1)
    return d + timedelta(days=(dow - d.weekday()) % 7)


def _next_monthly(after: date, dom: int, inclusive: bool) -> date:
    y, m = after.year, after.month
    for _ in range(3):
        day = min(dom, calendar.monthrange(y, m)[1])
        cand = date(y, m, day)
        if cand > after or (inclusive and cand == after):
            return cand
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    raise AssertionError("unreachable")


def next_date(frequency: str, after: date, day_of_week: int | None, day_of_month: int | None, inclusive: bool = False) -> date:
    if frequency == "Daily":
        return after if inclusive else after + timedelta(days=1)
    if frequency == "Weekly":
        return _next_weekly(after, day_of_week or 0, inclusive)
    return _next_monthly(after, day_of_month or 1, inclusive)


def _check_rule(frequency: str, dow: int | None, dom: int | None) -> None:
    if frequency == "Weekly" and dow is None:
        raise BusinessRuleError("VALIDATION_ERROR", "Choose the day of the week.", details=[{"field": "day_of_week", "issue": "required"}])
    if frequency == "Monthly" and dom is None:
        raise BusinessRuleError("VALIDATION_ERROR", "Choose the day of the month.", details=[{"field": "day_of_month", "issue": "required"}])


def _local_today(db, branch_id: uuid.UUID) -> date:
    return utcnow().astimezone(ZoneInfo(db.get(Branch, branch_id).timezone)).date()


# ---------------------------------------------------------------- recurring expenses (FR-EXP-008)
def template_out(t: ExpenseTemplate) -> dict:
    return {c: getattr(t, c) for c in ("id", "name", "category_id", "description", "payee", "amount", "currency", "frequency", "day_of_week", "day_of_month",
                                       "next_run_date", "is_active", "created_by", "created_at")}


def save_template(ctx: Ctx, data: dict, template_id: uuid.UUID | None = None) -> dict:
    _check_rule(data["frequency"], data.get("day_of_week"), data.get("day_of_month"))
    cat = ctx.db.get(ExpenseCategory, data["category_id"])
    if cat is None or not cat.is_active:
        raise NotFound("Expense category")
    start = data.pop("start_date", None) or ctx.business_date()
    if template_id:
        t = ctx.db.get(ExpenseTemplate, template_id)
        if t is None or t.branch_id != ctx.branch_id:
            raise NotFound("Recurring expense")
        before = template_out(t)
        for k, v in data.items():
            setattr(t, k, v)
        t.next_run_date = next_date(t.frequency, max(start, ctx.business_date()), t.day_of_week, t.day_of_month, inclusive=True)
        audit(ctx.db, ctx, "expense_template.update", "ExpenseTemplate", t.id, before=before, after=data)
    else:
        t = ExpenseTemplate(branch_id=ctx.branch_id, created_by=ctx.user_id, **data,
                            next_run_date=next_date(data["frequency"], start, data.get("day_of_week"), data.get("day_of_month"), inclusive=True))
        ctx.db.add(t)
        ctx.db.flush()
        audit(ctx.db, ctx, "expense_template.create", "ExpenseTemplate", t.id, after=data)
    ctx.db.flush()
    return template_out(t)


def list_templates(ctx: Ctx) -> list[dict]:
    rows = ctx.db.scalars(select(ExpenseTemplate).where(ExpenseTemplate.branch_id == ctx.branch_id).order_by(ExpenseTemplate.name))
    return [template_out(t) for t in rows]


def generate_due(db, branch_id: uuid.UUID | None = None, today: date | None = None) -> dict:
    """Create the Draft expenses that are due. Safe to run repeatedly: one draft per template and date (primary key)."""
    from app.services.billing import current_rate

    q_ = select(ExpenseTemplate).where(ExpenseTemplate.is_active).with_for_update(skip_locked=True)
    if branch_id:
        q_ = q_.where(ExpenseTemplate.branch_id == branch_id)
    out = {"created": 0, "skipped": 0, "expense_ids": []}
    for t in db.scalars(q_).all():
        local = today or _local_today(db, t.branch_id)
        n = 0
        while t.next_run_date <= local and n < MAX_CATCH_UP:
            run_date = t.next_run_date
            if db.get(ExpenseTemplateRun, (t.id, run_date)) is None:
                if t.currency == "USD":
                    base = t.amount
                else:
                    rate = current_rate(db, t.currency)
                    if rate is None:
                        out["skipped"] += 1  # stays due; generated once a rate exists
                        break
                    base = q(t.amount / rate.rate)
                e = Expense(branch_id=t.branch_id, expense_no=f"EX-{next_number(db, t.branch_id, 'EXPENSE', 'EX'):06d}", category_id=t.category_id, expense_date=run_date,
                            description=t.description, amount=t.amount, currency=t.currency, amount_base=base, payee=t.payee, status="Draft", submitted_by=t.created_by)
                db.add(e)
                db.flush()
                db.add(ExpenseTemplateRun(template_id=t.id, run_date=run_date, expense_id=e.id))
                audit(db, None, "expense.generate", "Expense", e.id, after={"template_id": t.id, "date": run_date, "amount": t.amount, "currency": t.currency},
                      branch_id=t.branch_id, actor_id=t.created_by)
                out["created"] += 1
                out["expense_ids"].append(e.id)
            t.next_run_date = next_date(t.frequency, run_date, t.day_of_week, t.day_of_month)
            n += 1
    db.flush()
    return out


# ---------------------------------------------------------------- scheduled reports (FR-RPT-027)
def _can_run(db, user: User, branch_id: uuid.UUID, report_id: str) -> bool:
    from app.core.dependencies import load_permissions
    from app.services.reports import _all_reports

    if user.status != "Active" or not user.email:
        return False
    if not db.scalar(select(UserBranch.user_id).where(UserBranch.user_id == user.id, UserBranch.branch_id == branch_id)):
        return False
    perms, _ = load_permissions(db, user)
    return any(p in perms for p in _all_reports()[report_id][1])


def _next_run(db, s: ReportSchedule, after_local: datetime) -> datetime:
    tz = ZoneInfo(db.get(Branch, s.branch_id).timezone)
    d = after_local.date()
    cand_date = next_date(s.frequency, d, s.day_of_week, s.day_of_month, inclusive=True)
    cand = datetime.combine(cand_date, time(s.hour), tz)
    if cand <= after_local:
        cand = datetime.combine(next_date(s.frequency, cand_date, s.day_of_week, s.day_of_month), time(s.hour), tz)
    return cand


def period_for(frequency: str, run_local: date) -> tuple[date, date]:
    """The completed period before the run: yesterday, the last 7 days, or the previous calendar month."""
    end = run_local - timedelta(days=1)
    if frequency == "Daily":
        return end, end
    if frequency == "Weekly":
        return end - timedelta(days=6), end
    first_this = run_local.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return last_prev.replace(day=1), last_prev


def schedule_out(db, s: ReportSchedule) -> dict:
    from app.services.reports import _all_reports

    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_([uuid.UUID(x) for x in s.recipient_ids] or [uuid.UUID(int=0)]))).all())
    return {**{c: getattr(s, c) for c in ("id", "report_id", "name", "frequency", "day_of_week", "day_of_month", "hour", "next_run_at", "last_run_at", "is_active", "created_by")},
            "report_name": _all_reports().get(s.report_id, (s.report_id,))[0],
            "recipients": [{"id": uuid.UUID(x), "name": names.get(uuid.UUID(x), "Unknown")} for x in s.recipient_ids]}


def save_schedule(ctx: Ctx, data: dict, schedule_id: uuid.UUID | None = None) -> dict:
    from app.services.reports import _all_reports

    reports = _all_reports()
    if data["report_id"] not in reports:
        raise NotFound("Report")
    if not any(ctx.can(p) for p in reports[data["report_id"]][1]):
        raise Forbidden(f"You don't have access to {reports[data['report_id']][0]}.", code="REPORT_FORBIDDEN")
    _check_rule(data["frequency"], data.get("day_of_week"), data.get("day_of_month"))
    bad = []
    for uid in data["recipient_ids"]:
        u = ctx.db.get(User, uid)
        if u is None or not _can_run(ctx.db, u, ctx.branch_id, data["report_id"]):
            bad.append({"field": "recipient_ids", "issue": u.full_name if u else str(uid)})
    if bad:
        raise BusinessRuleError("RECIPIENT_NOT_PERMITTED", "Some recipients can't receive this report: they need an email address, access to this branch and permission to see the report.",
                                details=bad)
    data["recipient_ids"] = [str(x) for x in dict.fromkeys(data["recipient_ids"])]
    if schedule_id:
        s = ctx.db.get(ReportSchedule, schedule_id)
        if s is None or s.branch_id != ctx.branch_id:
            raise NotFound("Report schedule")
        before = schedule_out(ctx.db, s)
        for k, v in data.items():
            setattr(s, k, v)
        audit(ctx.db, ctx, "report_schedule.update", "ReportSchedule", s.id, before={k: before[k] for k in ("frequency", "hour", "is_active")}, after=data)
    else:
        s = ReportSchedule(branch_id=ctx.branch_id, created_by=ctx.user_id, next_run_at=utcnow(), **data)
        ctx.db.add(s)
        ctx.db.flush()
        audit(ctx.db, ctx, "report_schedule.create", "ReportSchedule", s.id, after=data)
    tz = ZoneInfo(ctx.branch.timezone)
    s.next_run_at = _next_run(ctx.db, s, utcnow().astimezone(tz))
    ctx.db.flush()
    return schedule_out(ctx.db, s)


def list_schedules(ctx: Ctx) -> list[dict]:
    rows = ctx.db.scalars(select(ReportSchedule).where(ReportSchedule.branch_id == ctx.branch_id).order_by(ReportSchedule.name))
    return [schedule_out(ctx.db, s) for s in rows]


def run_due_schedules(db, now: datetime | None = None) -> dict:
    """Queue one background report job per permitted recipient; recipients who lost access are skipped (and noted)."""
    now = now or utcnow()
    out = {"schedules": 0, "jobs": 0, "skipped": 0}
    for s in db.scalars(select(ReportSchedule).where(ReportSchedule.is_active, ReportSchedule.next_run_at <= now).with_for_update(skip_locked=True)).all():
        tz = ZoneInfo(db.get(Branch, s.branch_id).timezone)
        run_local = s.next_run_at.astimezone(tz)
        start, end = period_for(s.frequency, run_local.date())
        for uid in s.recipient_ids:
            u = db.get(User, uuid.UUID(uid))
            if u is None or not _can_run(db, u, s.branch_id, s.report_id):
                out["skipped"] += 1
                continue
            db.add(ReportJob(branch_id=s.branch_id, requested_by=u.id, report_id=s.report_id,
                             params={"date_from": start.isoformat(), "date_to": end.isoformat(), "schedule_id": str(s.id)}))
            out["jobs"] += 1
        s.last_run_at = now
        s.next_run_at = _next_run(db, s, max(run_local, now.astimezone(tz)))
        out["schedules"] += 1
    db.flush()
    return out


def on_job_done(db, job: ReportJob) -> None:
    """Called by the report worker when a scheduled job finishes: email the recipient a link (once per job)."""
    sid = (job.params or {}).get("schedule_id")
    if not sid:
        return
    s = db.get(ReportSchedule, uuid.UUID(sid))
    u = db.get(User, job.requested_by)
    if s is None or u is None or not u.email:
        return
    from app.services.reports import _all_reports

    p = job.params
    period = p["date_from"] if p["date_from"] == p["date_to"] else f"{p['date_from']} to {p['date_to']}"
    db.add(OutboxEvent(branch_id=job.branch_id, event_type="email.scheduled_report", topic=f"report_job:{job.id}",
                       payload={"email": u.email, "report": _all_reports().get(job.report_id, (job.report_id,))[0], "schedule": s.name, "period": period,
                                "job_id": str(job.id)}))
